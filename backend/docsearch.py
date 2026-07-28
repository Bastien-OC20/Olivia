"""
Recherche documentaire en langage courant dans les fichiers de l'utilisatrice.

À ne pas confondre avec `search.py`, qui interroge un moteur de recherche WEB.
Ici on fouille le contenu réel des documents locaux (Word, Excel, PDF, texte),
y compris les PDF scannés et les images quand la reconnaissance de caractères
est active — l'extraction est centralisée dans `documents.extract_text_meta()`.

Principes :
  - la requête est une phrase ordinaire, jamais une expression régulière : les
    mots sont cherchés LITTÉRALEMENT, et tout métacaractère est échappé avant
    la moindre compilation de motif. Taper « convocation (conseil) » ou « 12*3 »
    ne peut donc plus produire d'erreur ;
  - comparaison insensible à la casse ET aux accents — indispensable en
    français : « eleve » trouve « élève », et « ÉLÈVE » trouve « eleve » ;
  - un document ne ressort que s'il contient TOUS les mots retenus ;
  - résultats groupés par document et classés par pertinence, avec des extraits
    lisibles ;
  - aucun index : l'extraction se fait à la volée, bornée en taille de fichier,
    en nombre de fichiers et en durée, avec un cache mémoire borné pour que deux
    recherches consécutives ne réextraient pas tout.
"""
import re
import threading
import time
import unicodedata
from collections import OrderedDict
from pathlib import Path

from . import documents

# ---------- Bornes (un dossier de secrétariat peut contenir des milliers de fichiers) ----------
MAX_FILE_SIZE = 10 * 1024 * 1024   # au-delà, le fichier n'est pas ouvert
MAX_FILES = 1200                   # nombre de fichiers réellement examinés
MAX_SECONDS = 12.0                 # durée maximale d'une recherche
MAX_RESULTS = 50                   # documents renvoyés

# ---------- Cache mémoire, clé (chemin, mtime, taille) ----------
_CACHE_MAX_FILES = 400
_CACHE_MAX_CHARS = 6_000_000
_cache: "OrderedDict[tuple, tuple[str, str, dict]]" = OrderedDict()
_cache_chars = 0
_cache_lock = threading.Lock()

# Dossiers techniques sans intérêt documentaire : élagués pour ne pas gaspiller
# le budget de fichiers examinés.
IGNORED_DIRS = {"node_modules", "__pycache__", ".git", ".venv", "venv",
                "dist", "build", "$recycle.bin", "system volume information"}


# ---------- Normalisation : minuscules + suppression des accents ----------
class _FoldMap(dict):
    """Table de repli pour `str.translate`, calculée à la demande et mémorisée.

    Garantie importante : la longueur du texte est PRÉSERVÉE (un caractère pour
    un caractère). Les positions trouvées dans le texte normalisé désignent donc
    directement les mêmes positions dans le texte d'origine, ce qui permet de
    produire des extraits lisibles, accentués, sans table de correspondance.
    Une transformation qui changerait la longueur (ligature « œ » → « oe ») est
    donc volontairement écartée.
    """

    def __missing__(self, code: int) -> str:
        ch = chr(code)
        bas = ch.lower()
        if len(bas) == 1:
            ch = bas
        sans_accent = "".join(c for c in unicodedata.normalize("NFD", ch)
                              if not unicodedata.combining(c))
        val = sans_accent if len(sans_accent) == 1 else ch
        self[code] = val
        return val


_FOLD = _FoldMap()


def fold(text: str) -> str:
    """Texte en minuscules, sans accents, de même longueur qu'à l'origine."""
    return text.translate(_FOLD)


# ---------- Analyse de la requête ----------
_MOT_RE = re.compile(r"[^\W_]+", re.UNICODE)

# Mots outils : exigés dans un document, ils ne feraient que du bruit. Ils ne
# sont écartés que s'il reste au moins un mot porteur de sens.
MOTS_VIDES = {
    "le", "la", "les", "un", "une", "des", "du", "de", "et", "ou", "a", "au",
    "aux", "en", "dans", "sur", "sous", "pour", "par", "avec", "sans", "ce",
    "cet", "cette", "ces", "est", "sont", "que", "qui", "quoi", "dont", "ne",
    "pas", "plus", "mon", "ma", "mes", "son", "sa", "ses", "nos", "vos", "leur",
}


def analyse_query(q: str) -> list[str]:
    """Découpe la requête en mots normalisés, dédupliqués, sans mots outils."""
    mots = [m for m in _MOT_RE.findall(fold(q or "")) if len(m) >= 2]
    if not mots:
        mots = _MOT_RE.findall(fold(q or ""))
    porteurs = [m for m in mots if m not in MOTS_VIDES]
    retenus = porteurs or mots
    vus: list[str] = []
    for m in retenus:
        if m not in vus:
            vus.append(m)
    return vus[:12]


def motif_litteral(mot: str) -> re.Pattern:
    """Motif compilé cherchant `mot` à la lettre : re.escape neutralise tout
    métacaractère, de sorte qu'aucune saisie ne peut être interprétée."""
    return re.compile(re.escape(mot))


# ---------- Cache d'extraction ----------
def _texte_indexe(path: Path, mtime_ns: int, size: int) -> tuple[str, str, dict]:
    """(texte d'origine, texte normalisé, provenance) — extrait une fois par version.

    La provenance ({"ocr": bool, "notice": str}) vient de `documents` : elle dit
    si le texte a été reconnu automatiquement sur un document scanné, ce que
    l'interface doit signaler.
    """
    cle = (str(path), mtime_ns, size)
    with _cache_lock:
        hit = _cache.get(cle)
        if hit is not None:
            _cache.move_to_end(cle)
            return hit
    brut, meta = documents.extract_text_meta(path)
    valeur = (brut, fold(brut), meta)
    _ranger_en_cache(cle, valeur)
    return valeur


def _ranger_en_cache(cle: tuple, valeur: tuple[str, str, dict]) -> None:
    global _cache_chars
    with _cache_lock:
        if cle in _cache:
            return
        _cache[cle] = valeur
        _cache_chars += len(valeur[0])
        while _cache and (len(_cache) > _CACHE_MAX_FILES or _cache_chars > _CACHE_MAX_CHARS):
            _, vieux = _cache.popitem(last=False)
            _cache_chars -= len(vieux[0])


def vider_cache() -> None:
    """Utile aux tests ; l'application n'a pas besoin de l'appeler."""
    global _cache_chars
    with _cache_lock:
        _cache.clear()
        _cache_chars = 0


# ---------- Extraits de contexte ----------
LARGEUR_EXTRAIT = 200
MAX_EXTRAITS = 3


def _extraits(orig: str, plie: str, termes: list[str]) -> list[str]:
    """1 à 3 passages lisibles du document, choisis sur les lignes qui
    rassemblent le plus de mots de la requête."""
    candidats = []
    pos = 0
    for ligne in orig.splitlines(keepends=True):
        debut, pos = pos, pos + len(ligne)
        zone = plie[debut:pos]
        if not zone.strip():
            continue
        distincts = 0
        total = 0
        premier = -1
        for t in termes:
            n = zone.count(t)
            if n:
                distincts += 1
                total += n
                i = zone.find(t)
                if premier < 0 or i < premier:
                    premier = i
        if distincts:
            candidats.append((-distincts, -total, debut, premier, ligne))
    candidats.sort()

    sortie: list[str] = []
    vus: set[str] = set()
    for _, _, _, premier, ligne in candidats:
        texte = _fenetre(ligne, premier)
        cle = texte.lower()
        if texte and cle not in vus:
            vus.add(cle)
            sortie.append(texte)
        if len(sortie) >= MAX_EXTRAITS:
            break
    return sortie


def _fenetre(ligne: str, premier: int) -> str:
    """Fenêtre de texte centrée sur la première occurrence, espaces resserrés."""
    marge = max(0, (LARGEUR_EXTRAIT - 40) // 2)
    debut = max(0, premier - marge)
    fin = min(len(ligne), debut + LARGEUR_EXTRAIT)
    morceau = re.sub(r"\s+", " ", ligne[debut:fin]).strip()
    if debut > 0:
        morceau = "…" + morceau
    if fin < len(ligne.rstrip()):
        morceau = morceau + "…"
    return morceau


# ---------- Recherche ----------
def _analyser_document(path: Path, nom: str, termes: list[str], phrase: str,
                       mtime_ns: int, size: int) -> tuple[int, list[str], dict] | None:
    """Score, extraits et provenance d'un document, ou None s'il ne contient pas
    tous les mots."""
    nom_plie = fold(nom)
    orig, plie, meta = _texte_indexe(path, mtime_ns, size)
    score = 0
    for t in termes:
        dans_nom = nom_plie.count(t)
        dans_texte = plie.count(t)
        if not dans_nom and not dans_texte:
            return None
        # Un mot présent dans le NOM du fichier pèse plus lourd : « convocation
        # conseil de classe.docx » doit sortir avant un document qui la cite.
        score += dans_texte + 3 * dans_nom
    if phrase and len(termes) > 1 and (phrase in plie or phrase in nom_plie):
        score += 10          # la phrase entière, telle quelle : très pertinent
    return score, _extraits(orig, plie, termes), meta


def search(fichiers, requete: str) -> dict:
    """Fouille les fichiers fournis et renvoie les documents pertinents.

    `fichiers` : itérable de tuples (chemin absolu, chemin virtuel affiché).
    Les bornes atteintes sont signalées dans la réponse : l'utilisatrice doit
    savoir qu'un résultat est partiel.
    """
    termes = analyse_query(requete)
    if not termes:
        return {"query": requete, "terms": [], "results": [], "files_scanned": 0,
                "truncated": False, "notice": "Saisissez au moins un mot à chercher."}

    phrase = " ".join(termes)
    debut = time.monotonic()
    examines = 0
    ignores_taille = 0
    tronque = False
    raison = ""
    resultats: list[dict] = []

    for path, virtuel in fichiers:
        if examines >= MAX_FILES:
            tronque = True
            raison = f"plus de {MAX_FILES} fichiers à examiner"
            break
        if time.monotonic() - debut > MAX_SECONDS:
            tronque = True
            raison = f"recherche interrompue après {int(MAX_SECONDS)} secondes"
            break
        if not documents.est_cherchable(path.suffix):
            continue
        try:
            st = path.stat()
        except OSError:
            continue
        if st.st_size > MAX_FILE_SIZE:
            ignores_taille += 1
            continue
        examines += 1
        try:
            trouve = _analyser_document(path, path.name, termes, phrase,
                                        st.st_mtime_ns, st.st_size)
        except Exception:
            continue                      # un document abîmé n'arrête pas la recherche
        if trouve is None:
            continue
        score, extraits, meta = trouve
        resultats.append({
            "name": path.name,
            "path": virtuel,
            "ext": path.suffix.lower(),
            "score": score,
            "snippets": extraits,
            # Texte issu d'une transcription automatique : l'interface le
            # signale, la reconnaissance n'étant jamais parfaite.
            "ocr": bool(meta.get("ocr")),
            "ocr_notice": str(meta.get("notice") or ""),
        })

    resultats.sort(key=lambda r: (-r["score"], r["name"].lower()))
    if len(resultats) > MAX_RESULTS:
        resultats = resultats[:MAX_RESULTS]
        tronque = True
        raison = raison or f"plus de {MAX_RESULTS} documents correspondent"

    notice = ""
    if tronque:
        notice = f"Résultats partiels : {raison}. Précisez votre recherche ou " \
                 "placez-vous dans un sous-dossier."
    elif ignores_taille:
        notice = f"{ignores_taille} fichier(s) trop volumineux n'ont pas été ouverts."

    return {
        "query": requete,
        "terms": termes,
        "results": resultats,
        "files_scanned": examines,
        "truncated": tronque,
        "notice": notice,
    }
