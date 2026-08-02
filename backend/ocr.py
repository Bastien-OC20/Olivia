"""
Reconnaissance de caractères (OCR) locale pour les documents sans couche texte.

Pourquoi : une circulaire passée au scanner ou un courrier reçu par fax est un
PDF fait d'IMAGES. `documents.extract_text()` en tire une chaîne vide, et le
document reste donc introuvable — un angle mort réel pour un secrétariat.

Ce module lit ces documents en trois temps :
  1. le PDF est rasterisé page par page avec `pypdfium2` (moteur de rendu
     embarqué dans le paquet Python : AUCUN binaire externe à installer, c'est
     la raison du choix face à `pdf2image`, qui exigerait Poppler) ;
  2. chaque page est envoyée à Tesseract en SOUS-PROCESSUS, sur son entrée
     standard, avec la langue française ;
  3. le texte reconnu est mis en cache SUR DISQUE (à côté des conversations),
     car l'OCR coûte une à trois secondes par page : sans cache, chaque
     recherche repaierait ce prix.

Dégradation propre, garantie : si Tesseract est absent, si `pypdfium2` n'est
pas installé, ou si quoi que ce soit échoue, les fonctions renvoient None et
l'application se comporte exactement comme avant. Aucune exception ne remonte.

Rien ne sort de la machine : Tesseract est un binaire local, appelé sans shell,
avec des arguments passés en liste. Aucun appel réseau n'est fait ici.

CLOISONNEMENT : le cache disque reste COMMUN à toutes les organisations, à la
différence des conversations, des réglages et de l'index sémantique. Ce n'est pas
un oubli : une entrée est adressée par le hash (chemin + date + taille) du
fichier source, donc deux organisations n'y partagent quelque chose que si elles
ont accès au MÊME fichier, sur le même disque, ce qu'aucune entrée de cache ne
leur permet d'obtenir de plus. Le partager économise un OCR complet sur un
dossier commun, sans rien révéler qui ne soit déjà lisible.
Ce qui est bien cloisonné, en revanche : les réglages lus (`ocr_enabled`,
`ocr_tesseract_path`) le sont pour le profil appelant, et la purge RGPD
(`vider_cache`) ne retire que les entrées issues des dossiers de ce profil.
"""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, NamedTuple, Optional

from .settings import reglages_lus

LANGUE = "fra"
NOM_EXE = "tesseract.exe" if sys.platform.startswith("win") else "tesseract"
SOUS_DOSSIER_MOTEUR = "tesseract"

# ---------- Bornes ----------
# Un PDF de 300 pages ne doit JAMAIS bloquer une recherche. Les valeurs sont
# calibrées sur la mesure faite en développement (environ 1,5 à 2,5 s par page
# A4 à 200 ppp) et sur le budget global d'une recherche (12 s, voir docsearch) :
#   - 8 pages couvrent la quasi-totalité des courriers et circulaires reçus ;
#   - 20 s par document bornent le pire cas, même sur un poste lent ;
#   - 2 OCR simultanés au plus : au-delà, on saturerait le processeur de la
#     machine de l'utilisatrice pendant qu'elle discute avec l'assistante.
# Quand une borne coupe, le texte déjà reconnu est conservé et une notice
# explicite remonte jusqu'à l'interface.
MAX_PAGES = 8
BUDGET_DOCUMENT = 20.0
TIMEOUT_PAGE = 25.0
DPI_RENDU = 200                    # compromis vitesse/qualité pour du texte de bureau
COTE_MAX_PIXELS = 2600             # borne la taille d'image envoyée au moteur
TAILLE_MAX_IMAGE = 15 * 1024 * 1024
MAX_CONCURRENCE = 2

_verrou_moteur = threading.BoundedSemaphore(MAX_CONCURRENCE)

# ---------- Cache disque ----------
# Volontairement placé dans backend/, à côté des conversations : sur le disque
# portable, le cache voyage donc avec l'application — c'est voulu, il survit au
# redémarrage et au débranchement de la clé.
DOSSIER_CACHE = Path(__file__).resolve().parent / "ocr_cache"
VERSION_CACHE = 1                  # à incrémenter si le format du texte produit change
MAX_FICHIERS_CACHE = 400
_verrou_cache = threading.Lock()

# Mémo très court du réglage, PAR ORGANISATION : `est_active()` est interrogée une
# fois par fichier candidat pendant une recherche (jusqu'à des milliers).
# 2 secondes suffisent pour qu'une modification faite dans les Paramètres soit
# prise en compte tout de suite, sans relire les réglages à chaque fichier. Keyé
# par profil : un mémo unique servirait à une organisation le choix d'une autre.
_TTL_REGLAGE = 2.0
_reglage_memo: dict[str, tuple[float, bool]] = {}


class Resultat(NamedTuple):
    """Texte reconnu, nombre de pages traitées, et notice si une borne a coupé."""
    texte: str
    pages: int
    notice: str


# ---------- Réglage ----------
def est_active(profile_id: str) -> bool:
    """Vrai si cette organisation a laissé la reconnaissance activée."""
    maintenant = time.monotonic()
    memo = _reglage_memo.get(profile_id or "")
    if memo is not None and maintenant - memo[0] < _TTL_REGLAGE:
        return memo[1]
    try:
        valeur = bool(reglages_lus(profile_id).get("ocr_enabled", True))
    except Exception:
        valeur = False
    _reglage_memo[profile_id or ""] = (maintenant, valeur)
    return valeur


# ---------- Localisation du moteur ----------
def _dossier_application() -> Path:
    """Dossier de l'application : celui de l'exécutable en mode gelé.

    Même calcul que `APP_DIR` dans launch.py. `sys._MEIPASS` NE convient PAS :
    c'est un dossier temporaire recréé à chaque lancement, alors que le moteur
    portable vit à côté de l'.exe, sur la clé USB.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def chemin_moteur(profile_id: str) -> Optional[Path]:
    """Tesseract portable livré avec l'application, sinon le PATH, sinon réglage.

    Le réglage `ocr_tesseract_path` est celui de l'organisation appelante : le
    moteur est un binaire de la machine, mais son emplacement se règle par profil
    comme le reste (mêmes Paramètres).

    Volontairement non mémorisé : la recherche coûte quelques appels système,
    négligeables devant une seconde d'OCR, et l'application détecte ainsi
    immédiatement un moteur ajouté (ou retiré) sans redémarrage.
    """
    local = _dossier_application() / SOUS_DOSSIER_MOTEUR / NOM_EXE
    if local.is_file():
        return local
    trouve = shutil.which("tesseract")
    if trouve:
        return Path(trouve)
    try:
        regle = str(reglages_lus(profile_id).get("ocr_tesseract_path") or "").strip()
    except Exception:
        regle = ""
    if regle:
        candidat = Path(regle)
        if candidat.is_dir():
            candidat = candidat / NOM_EXE
        if candidat.is_file():
            return candidat
    return None


def langues_disponibles(exe: Path) -> list[str]:
    """Langues installées à côté du moteur (lecture du dossier tessdata)."""
    dossier = exe.parent / "tessdata"
    if not dossier.is_dir():
        return []
    try:
        return sorted(p.stem for p in dossier.glob("*.traineddata"))
    except OSError:
        return []


def _moteur_pdf_disponible() -> bool:
    try:
        import pypdfium2  # noqa: F401
    except Exception:
        return False
    return True


def etat(profile_id: str) -> dict:
    """État de la reconnaissance, pour l'affichage dans les Paramètres."""
    exe = chemin_moteur(profile_id)
    if exe is None:
        return {
            "actif": est_active(profile_id),
            "disponible": False,
            "chemin": "",
            "langues": [],
            "pdf": False,
            "message": "Moteur de reconnaissance introuvable. Les documents scannés "
                       "restent consultables à l'écran, mais leur texte ne sortira pas "
                       "dans la recherche.",
        }
    langues = langues_disponibles(exe)
    pdf_ok = _moteur_pdf_disponible()
    if LANGUE not in langues and langues:
        message = (f"Moteur détecté, mais le français n'est pas installé "
                   f"(langues présentes : {', '.join(langues)}).")
    elif not pdf_ok:
        message = ("Moteur détecté, mais le module de rendu des PDF (pypdfium2) "
                   "est absent : seules les images seront reconnues.")
    else:
        message = "Moteur de reconnaissance opérationnel (français)."
    return {
        "actif": est_active(profile_id),
        "disponible": True,
        "chemin": str(exe),
        "langues": langues,
        "pdf": pdf_ok,
        "message": message,
    }


# ---------- Appel du moteur ----------
def _langue_utilisable(exe: Path) -> str:
    langues = langues_disponibles(exe)
    if not langues or LANGUE in langues:
        return LANGUE
    return "eng" if "eng" in langues else langues[0]


def _tesseract(exe: Path, image: bytes, timeout: float) -> str:
    """Envoie une image au moteur sur son entrée standard et rend le texte.

    Jamais `shell=True` : le binaire et ses arguments sont passés en liste, donc
    aucun contenu de fichier ne peut être interprété par un interpréteur de
    commandes. La sortie est de l'UTF-8, décodé explicitement (ne jamais se fier
    à l'encodage de la console Windows, qui transformerait « élève » en bouillie).
    """
    env = os.environ.copy()
    tessdata = exe.parent / "tessdata"
    if (tessdata / "fra.traineddata").is_file() or (tessdata / "eng.traineddata").is_file():
        env["TESSDATA_PREFIX"] = str(tessdata)
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0
    proc = subprocess.run(
        [str(exe), "-", "stdout", "-l", _langue_utilisable(exe)],
        input=image, capture_output=True, timeout=timeout, env=env,
        creationflags=flags,
    )
    if proc.returncode != 0:
        return ""
    return proc.stdout.decode("utf-8", errors="replace")


# ---------- Rasterisation d'une page PDF ----------
def _bmp(buffer: memoryview, largeur: int, hauteur: int, stride: int,
         canaux: int, mode: str) -> Optional[bytes]:
    """Assemble un BMP 24 bits à partir du tampon brut rendu par pdfium.

    Écrire le BMP à la main évite d'ajouter Pillow ou numpy aux dépendances :
    pypdfium2 reste le SEUL paquet nécessaire. Le format BMP se prête bien à
    l'exercice — pas de compression, et l'ordre des octets (BGR, lignes du bas
    vers le haut) est exactement celui du tampon de pdfium.
    """
    if canaux not in (3, 4):
        return None
    octets_ligne = largeur * 3
    remplissage = b"\x00" * (-octets_ligne % 4)
    lignes = []
    for y in range(hauteur - 1, -1, -1):
        ligne = bytearray(buffer[y * stride:y * stride + largeur * canaux])
        if canaux == 4:
            del ligne[3::4]                      # retire la couche alpha (rapide, en C)
        if mode.startswith("RGB"):               # sécurité : pdfium rend du BGR(A)
            bleu = ligne[2::3]
            ligne[2::3] = ligne[0::3]
            ligne[0::3] = bleu
        lignes.append(bytes(ligne) + remplissage)
    donnees = b"".join(lignes)
    entete = b"BM" + struct.pack("<IHHI", 14 + 40 + len(donnees), 0, 0, 14 + 40)
    dib = struct.pack("<IiiHHIIiiII", 40, largeur, hauteur, 1, 24, 0,
                      len(donnees), 2835, 2835, 0, 0)
    return entete + dib + donnees


def _echelle(largeur_pt: float, hauteur_pt: float) -> float:
    """Facteur de rendu : viser DPI_RENDU sans dépasser COTE_MAX_PIXELS."""
    cible = DPI_RENDU / 72.0
    cote = max(largeur_pt, hauteur_pt) or 1.0
    return max(0.5, min(cible, COTE_MAX_PIXELS / cote))


# ---------- Reconnaissance ----------
def _ocr_pdf(profile_id: str, chemin: Path) -> Optional[Resultat]:
    exe = chemin_moteur(profile_id)
    if exe is None:
        return None
    try:
        import pypdfium2 as pdfium
    except Exception:
        return None

    debut = time.monotonic()
    morceaux: list[str] = []
    notice = ""
    pages_faites = 0
    try:
        document = pdfium.PdfDocument(str(chemin))
    except Exception:
        return None
    try:
        total = len(document)
        limite = min(total, MAX_PAGES)
        for i in range(limite):
            if time.monotonic() - debut > BUDGET_DOCUMENT:
                notice = (f"Reconnaissance interrompue après {int(BUDGET_DOCUMENT)} secondes : "
                          f"{pages_faites} page(s) sur {total} analysée(s).")
                break
            try:
                page = document[i]
                largeur_pt, hauteur_pt = page.get_size()
                bitmap = page.render(scale=_echelle(largeur_pt, hauteur_pt))
                image = _bmp(memoryview(bitmap.buffer), bitmap.width, bitmap.height,
                             bitmap.stride, bitmap.n_channels, str(bitmap.mode))
            except Exception:
                continue                     # une page illisible n'arrête pas le document
            if image is None:
                continue
            try:
                morceaux.append(_tesseract(exe, image, TIMEOUT_PAGE))
            except subprocess.TimeoutExpired:
                notice = "Une page trop complexe a été abandonnée par la reconnaissance."
                continue
            except Exception:
                continue
            pages_faites += 1
        else:
            if total > MAX_PAGES and not notice:
                notice = (f"Document scanné volumineux : seules les {MAX_PAGES} premières "
                          f"pages sur {total} ont été reconnues.")
    finally:
        try:
            document.close()
        except Exception:
            pass
    return Resultat("\n".join(morceaux), pages_faites, notice)


def _ocr_image(profile_id: str, chemin: Path) -> Optional[Resultat]:
    exe = chemin_moteur(profile_id)
    if exe is None:
        return None
    try:
        if chemin.stat().st_size > TAILLE_MAX_IMAGE:
            return Resultat("", 0, "Image trop volumineuse pour la reconnaissance de texte.")
        donnees = chemin.read_bytes()
    except OSError:
        return None
    try:
        return Resultat(_tesseract(exe, donnees, TIMEOUT_PAGE), 1, "")
    except subprocess.TimeoutExpired:
        return Resultat("", 0, "Reconnaissance abandonnée : image trop longue à analyser.")
    except Exception:
        return None


# ---------- Cache disque ----------
def _cle(chemin: Path) -> Optional[str]:
    """Clé (chemin, date de modification, taille) : un fichier modifié est réOCRisé."""
    try:
        st = chemin.stat()
    except OSError:
        return None
    brut = f"{VERSION_CACHE}|{chemin.resolve()}|{st.st_mtime_ns}|{st.st_size}"
    return hashlib.sha256(brut.encode("utf-8", "replace")).hexdigest()[:40]


def _lire_cache(cle: str) -> Optional[Resultat]:
    fichier = DOSSIER_CACHE / f"{cle}.json"
    try:
        with open(fichier, encoding="utf-8") as f:
            donnees = json.load(f)
        return Resultat(str(donnees.get("texte", "")), int(donnees.get("pages", 0)),
                        str(donnees.get("notice", "")))
    except Exception:
        return None


def _ecrire_cache(cle: str, resultat: Resultat, chemin: Path) -> None:
    fichier = DOSSIER_CACHE / f"{cle}.json"
    try:
        source_absolue = str(chemin.resolve())
    except OSError:
        source_absolue = str(chemin)
    # `source_path` est indispensable à la purge RGPD ciblée : la clé du cache
    # est un hash non réversible, donc sans ce champ il serait impossible de
    # savoir de quel dossier — et donc de quelle organisation — vient une entrée.
    charge = {"texte": resultat.texte, "pages": resultat.pages,
              "notice": resultat.notice, "source": chemin.name,
              "source_path": source_absolue}
    try:
        with _verrou_cache:
            DOSSIER_CACHE.mkdir(parents=True, exist_ok=True)
            tmp = fichier.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(charge, f, ensure_ascii=False)
            tmp.replace(fichier)
            _purger()
    except Exception:
        pass                                  # un cache indisponible ne casse rien


def _purger() -> None:
    """Garde le cache borné : les entrées les plus anciennes sont supprimées."""
    try:
        entrees = sorted(DOSSIER_CACHE.glob("*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for vieux in entrees[:max(0, len(entrees) - MAX_FICHIERS_CACHE)]:
        try:
            vieux.unlink()
        except OSError:
            pass


def _sous_une_racine(source: str, racines: list[Path]) -> bool:
    """Le fichier d'origine tombe-t-il sous l'un des dossiers fournis ?"""
    if not source:
        return False
    try:
        chemin = Path(source)
    except (OSError, ValueError):
        return False
    for racine in racines:
        try:
            if chemin == racine or chemin.is_relative_to(racine):
                return True
        except (OSError, ValueError):
            continue
    return False


def vider_cache(racines: list[Path]) -> int:
    """RGPD : supprime les entrées de cache issues des dossiers `racines`
    (les `fs_roots` de l'organisation demandeuse). Renvoie le nombre effacé.

    Le cache étant COMMUN à toutes les organisations (voir l'en-tête du module),
    tout vider sur une demande d'effacement détruirait le travail des autres — et,
    plus grave, ferait passer pour une purge ciblée ce qui n'en est pas une. On ne
    retire donc que ce qui provient des dossiers du demandeur.

    Cas particulier assumé : une entrée écrite par une version antérieure ne porte
    pas de `source_path` et n'est donc rattachable à aucun dossier. Elle est
    supprimée. Le mauvais choix serait l'inverse : laisser en place, après une
    demande d'effacement, un texte reconnu qui appartient très probablement au
    demandeur. Ce que ça coûte aux autres organisations est un simple OCR à
    repayer, le cache étant reconstructible par construction.
    """
    efface = 0
    with _verrou_cache:
        for fichier in DOSSIER_CACHE.glob("*.json"):
            try:
                with open(fichier, encoding="utf-8") as f:
                    source = str((json.load(f) or {}).get("source_path") or "")
            except Exception:
                source = ""          # entrée illisible : traitée comme non rattachable
            if source and not _sous_une_racine(source, racines):
                continue
            try:
                fichier.unlink()
                efface += 1
            except OSError:
                pass
    return efface


def _avec_cache(chemin: Path, calcul: Callable[[Path], Optional[Resultat]]) -> Optional[Resultat]:
    cle = _cle(chemin)
    if cle is not None:
        depuis_cache = _lire_cache(cle)
        if depuis_cache is not None:
            return depuis_cache
    with _verrou_moteur:
        resultat = calcul(chemin)
    if resultat is not None and cle is not None:
        _ecrire_cache(cle, resultat, chemin)
    return resultat


# ---------- API publique ----------
def texte_pdf(profile_id: str, chemin: Path) -> Optional[Resultat]:
    """Texte reconnu d'un PDF scanné, ou None si la reconnaissance est impossible."""
    return _avec_cache(chemin, lambda p: _ocr_pdf(profile_id, p))


def texte_image(profile_id: str, chemin: Path) -> Optional[Resultat]:
    """Texte reconnu d'une image, ou None si la reconnaissance est impossible."""
    return _avec_cache(chemin, lambda p: _ocr_image(profile_id, p))
