"""
Recherche documentaire PAR LE SENS dans les fichiers de l'utilisatrice.

À ne pas confondre avec `docsearch.py`, qui cherche des MOTS : là-bas, un
document ne ressort que s'il contient littéralement les termes tapés. Ici on
compare des SIGNIFICATIONS — « lettre aux parents pour la sortie scolaire »
retrouve une « autorisation de sortie pédagogique » qui ne partage pas un seul
mot avec la requête. Les deux modes sont complémentaires et coexistent : les
mots-clés restent imbattables pour un nom propre ou un numéro de circulaire.

Comment :
  1. chaque document est découpé en extraits d'environ 1200 caractères qui se
     chevauchent (une phrase coupée en deux reste lisible dans l'un des deux) ;
  2. chaque extrait est transformé en vecteur par le modèle `bge-m3`, servi par
     Ollama, déjà présent sur le poste — RIEN ne sort de la machine. Ce modèle a
     été retenu pour sa qualité en français : la plupart des modèles
     d'embeddings sont entraînés sur de l'anglais et se dégradent nettement sur
     du courrier administratif francophone ;
  3. les vecteurs sont rangés dans un index FAISS local. FAISS parce qu'il est
     léger, purement CPU, sans entraînement ni serveur à faire tourner : à
     l'échelle d'un secrétariat (quelques milliers d'extraits), un index plat
     répond en quelques millisecondes.

Les métadonnées (chemins, textes des extraits) sont écrites en JSON et NON en
pickle : un pickle est du code exécutable au chargement, et ce fichier décrit
des documents personnels — le format doit rester inerte et relisible à l'œil.

Dégradation propre, garantie : si `faiss` n'est pas installé, si le modèle
`bge-m3` n'a pas été tiré, si Ollama est éteint ou si l'index n'existe pas
encore, les fonctions publiques renvoient un état « indisponible » assorti d'un
message clair. Aucune exception ne remonte jamais jusqu'à la couche HTTP.
"""
import json
import os
import re
import shutil
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import httpx

from . import documents

# `faiss` (et `numpy`, qui vient avec) est une dépendance obligatoire de CE
# module. Mais `main.py` importe `docindex` au démarrage : sans ce garde-fou,
# un environnement où `pip install -r requirements.txt` n'a pas encore été
# rejoué empêcherait l'application ENTIÈRE de démarrer, pour une fonction
# secondaire. Le drapeau permet aux fonctions publiques de répondre
# « indisponible » exactement comme le fait `ocr.py` sans son moteur.
try:
    import faiss
    import numpy as np
    FAISS_DISPONIBLE = True
except Exception:                      # pragma: no cover - dépend de l'install
    faiss = None
    np = None
    FAISS_DISPONIBLE = False

# ---------- Modèle d'embeddings ----------
# Dupliqué depuis main.py DÉLIBÉRÉMENT : comme ocr.py, ce module ne dépend
# jamais de main.py, qui l'importe — l'inverse créerait un import circulaire.
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
EMBED_MODEL = "bge-m3"
EMBED_DIM = 1024                       # dimension des vecteurs produits par bge-m3

# ---------- Découpage des documents ----------
# 1200 caractères ≈ un paragraphe long : assez pour porter une idée complète,
# assez court pour que le vecteur reste précis. Le chevauchement évite qu'une
# phrase coupée par une frontière d'extrait ne devienne introuvable.
CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
CHUNK_MIN_CHARS = 20                   # en deçà, l'extrait ne porte aucun sens
MAX_CHUNKS_PAR_FICHIER = 40            # borne le coût d'un document fleuve

# ---------- Bornes (un dossier de secrétariat peut contenir des milliers de fichiers) ----------
MAX_FILE_SIZE = 10 * 1024 * 1024       # au-delà, le fichier n'est pas ouvert
MAX_FILES = 3000                       # nombre de fichiers réellement examinés
EMBED_BATCH_SIZE = 16                  # extraits envoyés en un seul appel à Ollama
EMBED_TIMEOUT = 60.0
# Le tout premier appel doit charger bge-m3 en mémoire (plusieurs dizaines de
# secondes sur un poste sans carte graphique) : lui laisser le délai habituel
# ferait échouer la construction dès le premier fichier.
EMBED_TIMEOUT_PREMIER_APPEL = 180.0

# ---------- Index sur disque ----------
# Volontairement placé dans backend/, à côté des conversations et du cache OCR :
# sur le disque portable, l'index voyage donc avec l'application.
DOSSIER_INDEX = Path(__file__).resolve().parent / "docindex"
FICHIER_INDEX = DOSSIER_INDEX / "index.faiss"
FICHIER_META = DOSSIER_INDEX / "meta.json"
VERSION_META = 1                       # à incrémenter si le format des métadonnées change

# Sauvegardes intermédiaires : indexer plusieurs milliers de documents prend des
# minutes. Sans point de reprise, une coupure de courant (clé USB débranchée,
# poste éteint) perdrait tout le travail déjà payé.
CHECKPOINT_FICHIERS = 25
CHECKPOINT_SECONDES = 10.0

# ---------- Restitution des résultats ----------
MAX_EXTRAITS_PAR_DOC = 3
MAX_CAR_EXTRAIT = 250                  # longueur d'un extrait affiché à l'écran

# Mémo très court de la présence du modèle : `etat()` est interrogée à chaque
# rafraîchissement de l'interface pendant une construction (plusieurs fois par
# seconde). 3 secondes suffisent pour qu'un `ollama pull bge-m3` terminé soit
# détecté tout de suite, sans interroger Ollama à chaque sondage.
_TTL_MODELE = 3.0
_modele_memo: tuple[float, bool] = (0.0, False)

# ---------- Cache mémoire de l'index chargé ----------
# Invalidé sur la date de modification de meta.json : une construction qui
# vient de se terminer est donc vue immédiatement par la recherche.
_verrou_cache = threading.Lock()
_cache_index: Optional[tuple] = None   # (mtime_ns, index, meta)

# ---------- Construction en tâche de fond ----------
_verrou_construction = threading.Lock()
_verrou_progres = threading.Lock()
_progres = {"en_cours": False, "fait": 0, "total": 0, "fichier": "", "erreur": ""}
_evenement_annulation = threading.Event()


# ---------- Découpage en extraits ----------
def _queue(texte: str) -> str:
    """Fin d'un extrait, reprise en tête du suivant, rognée au mot entier.

    Couper au milieu d'un mot produirait un fragment que le modèle
    d'embeddings interpréterait de travers ; on avance donc jusqu'à la
    première coupure d'espace.
    """
    if len(texte) <= CHUNK_OVERLAP:
        return texte
    bout = texte[-CHUNK_OVERLAP:]
    trouve = re.search(r"\s", bout)
    if trouve is not None:
        bout = bout[trouve.end():]
    return bout.strip()


def _blocs(para: str) -> list[str]:
    """Un paragraphe ramené à des blocs qui tiennent dans CHUNK_SIZE.

    Un paragraphe trop long est repris phrase par phrase ; une phrase encore
    trop longue (tableau recopié, ligne d'export sans ponctuation) est coupée
    brutalement — mieux vaut un extrait imparfait qu'un document ignoré.
    """
    if len(para) <= CHUNK_SIZE:
        return [para]
    sortie: list[str] = []
    for phrase in re.split(r"(?<=[.!?])\s+", para):
        phrase = phrase.strip()
        if not phrase:
            continue
        if len(phrase) <= CHUNK_SIZE:
            sortie.append(phrase)
            continue
        for i in range(0, len(phrase), CHUNK_SIZE):
            sortie.append(phrase[i:i + CHUNK_SIZE])
    return sortie


def _decouper(texte: str) -> list[str]:
    """Découpe un document en extraits chevauchants, prêts à être vectorisés."""
    extraits: list[str] = []
    tampon = ""
    for para in re.split(r"\n{2,}", texte or ""):
        para = para.strip()
        if not para:
            continue
        for bloc in _blocs(para):
            if tampon and len(tampon) + 1 + len(bloc) > CHUNK_SIZE:
                extraits.append(tampon)
                if len(extraits) >= MAX_CHUNKS_PAR_FICHIER:
                    return extraits
                tampon = _queue(tampon)
            tampon = f"{tampon}\n{bloc}" if tampon else bloc
    if tampon:
        extraits.append(tampon)
    retenus = [e for e in extraits if len(e.strip()) >= CHUNK_MIN_CHARS]
    return retenus[:MAX_CHUNKS_PAR_FICHIER]


# ---------- Appel du modèle d'embeddings ----------
def _embed(textes: list[str], client: httpx.Client,
           premier_appel: bool = False) -> Optional[list[list[float]]]:
    """Vecteurs des textes fournis, ou None si le modèle n'a pas répondu.

    Client SYNCHRONE volontairement : ce module s'exécute dans un thread (pool
    de FastAPI ou thread de construction), jamais dans une coroutine — un
    `AsyncClient` y serait inutilisable.

    Renvoie None sur la moindre anomalie (Ollama éteint, modèle absent, nombre
    de vecteurs incohérent) plutôt que de lever : l'appelant décide alors
    d'abandonner ce fichier, sans jamais interrompre la construction entière.
    """
    if not textes:
        return []
    delai = EMBED_TIMEOUT_PREMIER_APPEL if premier_appel else EMBED_TIMEOUT
    try:
        reponse = client.post(
            f"{OLLAMA_URL}/api/embed",
            json={"model": EMBED_MODEL, "input": textes},
            timeout=delai,
        )
        reponse.raise_for_status()
        donnees = reponse.json()
    except Exception:
        return None
    if not isinstance(donnees, dict):
        return None
    vecteurs = donnees.get("embeddings")
    if not isinstance(vecteurs, list) or len(vecteurs) != len(textes):
        return None
    for v in vecteurs:
        if not isinstance(v, list) or len(v) != EMBED_DIM:
            return None
    return vecteurs


def _modele_disponible() -> bool:
    """Le modèle d'embeddings est-il tiré sur ce poste ?

    Comparaison par préfixe : Ollama nomme le modèle « bge-m3:latest » alors
    que l'utilisatrice a tapé « ollama pull bge-m3 ».
    """
    global _modele_memo
    maintenant = time.monotonic()
    if maintenant - _modele_memo[0] < _TTL_MODELE:
        return _modele_memo[1]
    valeur = False
    try:
        with httpx.Client(timeout=5.0) as client:
            reponse = client.get(f"{OLLAMA_URL}/api/tags")
            reponse.raise_for_status()
            for modele in (reponse.json() or {}).get("models") or []:
                nom = str((modele or {}).get("name") or "")
                if nom == EMBED_MODEL or nom.startswith(f"{EMBED_MODEL}:"):
                    valeur = True
                    break
    except Exception:
        valeur = False
    _modele_memo = (maintenant, valeur)
    return valeur


# ---------- Index FAISS et métadonnées ----------
def _index_vide():
    """Index plat à produit scalaire, indexé par identifiants explicites.

    Les vecteurs étant normalisés avant tout ajout comme avant toute recherche,
    le produit scalaire EST la similarité cosinus — pas de conversion à faire.
    L'enveloppe `IndexIDMap` permet de retirer les extraits d'un fichier modifié
    sans reconstruire l'index entier.
    """
    return faiss.IndexIDMap(faiss.IndexFlatIP(EMBED_DIM))


def _meta_vide() -> dict:
    return {
        "version": VERSION_META,
        "model": EMBED_MODEL,
        "dim": EMBED_DIM,
        "built_at": "",
        "next_id": 1,
        "files": {},
        "chunks": {},
    }


def _charger(depuis_disque: bool = False) -> tuple:
    """(index, métadonnées) lus sur disque, ou (None, None).

    `depuis_disque` court-circuite le cache mémoire : la construction MODIFIE
    l'index qu'elle reçoit, elle ne doit donc jamais travailler sur l'objet
    partagé avec les recherches en cours.

    Toute incohérence — modèle ou dimension différents, nombre de vecteurs qui
    ne correspond plus aux métadonnées — est traitée comme une absence d'index :
    il sera simplement reconstruit. Jamais d'exception, jamais de résultat faux.
    """
    global _cache_index
    if not FAISS_DISPONIBLE:
        return None, None
    try:
        mtime = FICHIER_META.stat().st_mtime_ns
    except OSError:
        return None, None
    if not depuis_disque:
        with _verrou_cache:
            if _cache_index is not None and _cache_index[0] == mtime:
                return _cache_index[1], _cache_index[2]
    try:
        with open(FICHIER_META, encoding="utf-8") as f:
            meta = json.load(f)
        index = faiss.read_index(str(FICHIER_INDEX))
    except Exception:
        return None, None
    if not isinstance(meta, dict):
        return None, None
    if meta.get("version") != VERSION_META or meta.get("model") != EMBED_MODEL:
        return None, None
    fichiers = meta.get("files")
    extraits = meta.get("chunks")
    if not isinstance(fichiers, dict) or not isinstance(extraits, dict):
        return None, None
    try:
        if int(meta.get("dim") or 0) != EMBED_DIM or index.ntotal != len(extraits):
            return None, None
    except (TypeError, ValueError):
        return None, None
    if not depuis_disque:
        with _verrou_cache:
            _cache_index = (mtime, index, meta)
    return index, meta


def _sauver(index, meta: dict) -> bool:
    """Écrit l'index puis les métadonnées, chacun de façon atomique.

    L'ORDRE compte : l'index d'abord, les métadonnées ensuite. Si la machine
    s'arrête entre les deux, le meta.json encore en place décrit un index plus
    ancien mais parfaitement valide — jamais l'inverse, qui pointerait vers des
    extraits inexistants.
    """
    try:
        DOSSIER_INDEX.mkdir(parents=True, exist_ok=True)
        meta["built_at"] = datetime.now().isoformat(timespec="seconds")
        tmp_index = FICHIER_INDEX.with_suffix(".tmp")
        faiss.write_index(index, str(tmp_index))
        tmp_index.replace(FICHIER_INDEX)
        tmp_meta = FICHIER_META.with_suffix(".tmp")
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        tmp_meta.replace(FICHIER_META)
        return True
    except Exception:
        return False                   # un index non sauvé n'empêche rien d'autre


def _retirer(index, meta: dict, cle: str) -> None:
    """Efface de l'index et des métadonnées tous les extraits d'un fichier."""
    ancien = meta["files"].pop(cle, None)
    if not isinstance(ancien, dict):
        return
    identifiants = []
    for i in ancien.get("chunk_ids") or []:
        try:
            identifiants.append(int(i))
        except (TypeError, ValueError):
            continue
        meta["chunks"].pop(str(i), None)
    if not identifiants:
        return
    try:
        index.remove_ids(np.asarray(identifiants, dtype="int64"))
    except Exception:
        pass                           # l'incohérence est rattrapée par _charger()


# ---------- Construction de l'index ----------
def construire_index(fichiers, on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Construit ou met à jour l'index. BLOQUANTE : à appeler dans un thread.

    `fichiers` : itérable de tuples (chemin absolu, chemin virtuel affiché) —
    même contrat que `main._iter_searchable_files`.

    Incrémentale : un fichier dont la date de modification et la taille n'ont
    pas bougé n'est pas revectorisé. Réindexer un dossier entier après l'ajout
    d'un seul document ne coûte donc que ce document.

    Ne lève JAMAIS : un fichier illisible ou un lot d'embeddings en échec est
    compté comme erreur, et le balayage continue.
    """
    resume = {"documents": 0, "extraits": 0, "erreurs": 0, "annule": False,
              "tronque": False}
    if not FAISS_DISPONIBLE:
        return resume

    index, meta = _charger(depuis_disque=True)
    if index is None or meta is None:
        index, meta = _index_vide(), _meta_vide()

    liste = list(fichiers)
    total = len(liste)
    vus: set[str] = set()
    examines = 0
    fait = 0
    modifie = False
    premier_appel = True
    dernier_point = time.monotonic()
    depuis_point = 0

    with httpx.Client(timeout=EMBED_TIMEOUT) as client:
        for chemin, _virtuel in liste:
            if _evenement_annulation.is_set():
                resume["annule"] = True
                break
            fait += 1
            if on_progress is not None:
                try:
                    on_progress({"fait": fait, "total": total, "fichier": chemin.name})
                except Exception:
                    pass               # l'affichage ne doit pas casser la construction
            if not documents.est_cherchable(chemin.suffix):
                continue
            try:
                st = chemin.stat()
                cle = str(chemin.resolve())
            except OSError:
                continue
            if st.st_size > MAX_FILE_SIZE:
                continue
            if examines >= MAX_FILES:
                resume["tronque"] = True
                break
            examines += 1
            vus.add(cle)
            ancien = meta["files"].get(cle)
            if isinstance(ancien, dict) and ancien.get("mtime_ns") == st.st_mtime_ns \
                    and ancien.get("size") == st.st_size:
                continue
            traite, premier_appel = _indexer_fichier(index, meta, chemin, cle, st,
                                                     client, premier_appel)
            if traite is None:
                resume["erreurs"] += 1
                continue
            modifie = True
            if traite:
                resume["documents"] += 1
                resume["extraits"] += traite
            depuis_point += 1
            if depuis_point >= CHECKPOINT_FICHIERS \
                    or time.monotonic() - dernier_point >= CHECKPOINT_SECONDES:
                _sauver(index, meta)
                depuis_point = 0
                dernier_point = time.monotonic()

    # Purge des fichiers disparus — UNIQUEMENT si le balayage est allé au bout.
    # Interrompu (annulation ou borne atteinte), il n'a pas vu tout le corpus :
    # purger sur cette base effacerait des documents parfaitement présents.
    if not resume["annule"] and not resume["tronque"]:
        for cle in [c for c in meta["files"] if c not in vus]:
            _retirer(index, meta, cle)
            modifie = True

    # Rien de nouveau (corpus inchangé, ou aucun fichier vectorisé faute de
    # modèle) : on ne réécrit pas l'index, ce qui laisse aussi la date de
    # dernière construction affichée à l'écran refléter un vrai contenu.
    if modifie:
        _sauver(index, meta)
    return resume


def _indexer_fichier(index, meta: dict, chemin: Path, cle: str, st,
                     client: httpx.Client, premier_appel: bool) -> tuple:
    """Vectorise UN fichier et remplace ses extraits dans l'index.

    Renvoie (nombre d'extraits, premier_appel), ou (None, premier_appel) en cas
    d'échec. Un fichier n'est jamais indexé À MOITIÉ : si un seul lot
    d'embeddings échoue, ses anciennes entrées sont laissées intactes et il sera
    retenté à la prochaine construction.
    """
    try:
        texte, provenance = documents.extract_text_meta(chemin)
    except Exception:
        return None, premier_appel
    extraits = _decouper(texte)
    if not extraits:
        # Document vide ou illisible : on retire une éventuelle version
        # précédente, sans quoi l'index garderait un contenu périmé.
        _retirer(index, meta, cle)
        return 0, premier_appel

    vecteurs: list[list[float]] = []
    for debut in range(0, len(extraits), EMBED_BATCH_SIZE):
        lot = _embed(extraits[debut:debut + EMBED_BATCH_SIZE], client, premier_appel)
        premier_appel = False
        if lot is None:
            return None, premier_appel
        vecteurs.extend(lot)

    try:
        # Normalisation AVANT l'ajout : c'est ce qui fait du produit scalaire
        # de l'index une similarité cosinus.
        matrice = np.asarray(vecteurs, dtype="float32")
        faiss.normalize_L2(matrice)
        identifiants = list(range(int(meta["next_id"]),
                                  int(meta["next_id"]) + len(extraits)))
        _retirer(index, meta, cle)
        index.add_with_ids(matrice, np.asarray(identifiants, dtype="int64"))
    except Exception:
        return None, premier_appel

    meta["next_id"] = identifiants[-1] + 1     # jamais réutilisé : pas de collision
    meta["files"][cle] = {
        "mtime_ns": st.st_mtime_ns,
        "size": st.st_size,
        "ocr": bool((provenance or {}).get("ocr")),
        "chunk_ids": identifiants,
    }
    for ordre, (identifiant, extrait) in enumerate(zip(identifiants, extraits)):
        meta["chunks"][str(identifiant)] = {"path": cle, "text": extrait, "ord": ordre}
    return len(extraits), premier_appel


# ---------- Pilotage de la construction en tâche de fond ----------
def _noter_progres(etape: dict) -> None:
    with _verrou_progres:
        _progres["fait"] = int(etape.get("fait") or 0)
        _progres["total"] = int(etape.get("total") or 0)
        _progres["fichier"] = str(etape.get("fichier") or "")


def _construire_en_thread(fichiers) -> None:
    """Corps du thread de construction.

    `fichiers` est encore un GÉNÉRATEUR : le matérialiser coûte quelques
    centaines de millisecondes sur un gros dossier, et c'est précisément
    pourquoi ce travail est fait ici et non dans la requête HTTP.

    Le `finally` est vital : sans lui, une erreur inattendue laisserait le
    verrou pris et interdirait toute construction ultérieure jusqu'au
    redémarrage de l'application.
    """
    try:
        construire_index(fichiers, on_progress=_noter_progres)
    except Exception as e:
        with _verrou_progres:
            _progres["erreur"] = f"{type(e).__name__} : {e}"
    finally:
        with _verrou_progres:
            _progres["en_cours"] = False
            _progres["fichier"] = ""
        _verrou_construction.release()


def lancer_construction(fichiers) -> bool:
    """Démarre un thread démon si aucune construction n'est en cours.

    Renvoie False sans rien faire si une construction tourne déjà : deux
    constructions simultanées écriraient le même index.
    """
    if not FAISS_DISPONIBLE:
        return False
    if not _verrou_construction.acquire(blocking=False):
        return False
    _evenement_annulation.clear()
    with _verrou_progres:
        _progres.update(en_cours=True, fait=0, total=0, fichier="", erreur="")
    try:
        threading.Thread(target=_construire_en_thread, args=(fichiers,),
                         daemon=True).start()
    except Exception as e:
        with _verrou_progres:
            _progres["en_cours"] = False
            _progres["erreur"] = f"{type(e).__name__} : {e}"
        _verrou_construction.release()
        return False
    return True


def annuler_construction() -> None:
    """Demande l'arrêt de la construction en cours (effectif entre deux fichiers)."""
    _evenement_annulation.set()


# ---------- État, pour l'interface ----------
def etat() -> dict:
    """État de la recherche par le sens, affiché dans les Paramètres."""
    with _verrou_progres:
        instantane = dict(_progres)
    en_cours = bool(instantane.get("en_cours"))
    reponse = {
        "modele": EMBED_MODEL,
        "modele_disponible": False,
        "index_construit": False,
        "construit_le": "",
        "documents": 0,
        "extraits": 0,
        "en_cours": en_cours,
        "progression": {
            "fait": int(instantane.get("fait") or 0),
            "total": int(instantane.get("total") or 0),
            "fichier": str(instantane.get("fichier") or ""),
        } if en_cours else None,
        "derniere_erreur": str(instantane.get("erreur") or ""),
        "message": "",
    }
    if not FAISS_DISPONIBLE:
        reponse["message"] = "Le module de recherche par le sens n'est pas installé."
        return reponse

    reponse["modele_disponible"] = _modele_disponible()
    index, meta = _charger()
    if index is not None and meta is not None and index.ntotal > 0:
        reponse["index_construit"] = True
        reponse["construit_le"] = str(meta.get("built_at") or "")
        reponse["documents"] = len(meta.get("files") or {})
        reponse["extraits"] = len(meta.get("chunks") or {})

    if not reponse["modele_disponible"]:
        reponse["message"] = (f"Modèle {EMBED_MODEL} non installé. "
                              f"Lancez : ollama pull {EMBED_MODEL}")
    elif not reponse["index_construit"]:
        reponse["message"] = "Aucun index construit pour l'instant."
    else:
        reponse["message"] = (f"Index à jour : {reponse['documents']} documents, "
                              f"{reponse['extraits']} extraits.")
    return reponse


# ---------- Recherche ----------
def _abreger(texte: str) -> str:
    """Extrait ramené à une longueur lisible, coupé sur un mot entier."""
    propre = re.sub(r"\s+", " ", texte or "").strip()
    if len(propre) <= MAX_CAR_EXTRAIT:
        return propre
    coupe = propre.rfind(" ", 0, MAX_CAR_EXTRAIT)
    if coupe < MAX_CAR_EXTRAIT // 2:
        coupe = MAX_CAR_EXTRAIT
    return propre[:coupe].rstrip(" ,;:.") + "…"


def _reponse_vide(requete: str, notice: str) -> dict:
    """Réponse de même forme que `docsearch.search()`, sans résultat.

    `terms` et `files_scanned` n'ont pas de sens en recherche par le sens (il
    n'y a ni mots exigés, ni fichiers ouverts à la volée) mais restent présents :
    l'interface lit la même structure pour les deux modes de recherche.
    """
    return {"query": requete, "terms": [], "results": [], "files_scanned": 0,
            "truncated": False, "notice": notice}


def rechercher(requete: str, k: int = 10, dossier: Optional[Path] = None) -> dict:
    """Documents les plus proches du SENS de la requête.

    `dossier`, s'il est fourni, est un chemin absolu déjà résolu par l'appelant :
    seuls les documents situés dessous sont renvoyés.

    Ne lève jamais : toute indisponibilité (module, modèle, index, Ollama) se
    traduit par une liste vide accompagnée d'une notice explicite.
    """
    demande = (requete or "").strip()
    if not FAISS_DISPONIBLE:
        return _reponse_vide(requete, "La recherche par le sens n'est pas "
                                      "disponible sur cette installation.")
    if not demande:
        return _reponse_vide(requete, "Saisissez au moins un mot à chercher.")

    index, meta = _charger()
    if index is None or meta is None or index.ntotal == 0:
        return _reponse_vide(requete, "Aucun index n'a encore été construit. "
                                      "Lancez la construction depuis les Paramètres.")
    if not _modele_disponible():
        return _reponse_vide(requete, f"Modèle {EMBED_MODEL} indisponible : la "
                                      "recherche par le sens ne peut pas répondre.")

    try:
        with httpx.Client(timeout=EMBED_TIMEOUT) as client:
            vecteurs = _embed([demande], client)
    except Exception:
        vecteurs = None
    if not vecteurs:
        return _reponse_vide(requete, "Le moteur de recherche par le sens n'a pas "
                                      "répondu. Vérifiez qu'Ollama est démarré.")

    try:
        question = np.asarray(vecteurs, dtype="float32")
        faiss.normalize_L2(question)
        # On demande large : plusieurs extraits d'un même document occupent
        # sinon toutes les places, et il ne resterait que deux ou trois
        # documents distincts à afficher.
        scores, identifiants = index.search(question, max(k * 4, 40))
    except Exception:
        return _reponse_vide(requete, "La recherche par le sens a échoué sur cet "
                                      "index. Reconstruisez-le depuis les Paramètres.")

    extraits = meta.get("chunks") or {}
    infos_fichiers = meta.get("files") or {}
    par_document: dict[str, dict] = {}
    for score, identifiant in zip(scores[0].tolist(), identifiants[0].tolist()):
        if identifiant < 0:
            continue
        extrait = extraits.get(str(identifiant))
        if not isinstance(extrait, dict):
            continue
        chemin = str(extrait.get("path") or "")
        if not chemin:
            continue
        p = Path(chemin)
        if dossier is not None:
            try:
                if not p.is_relative_to(dossier):
                    continue
            except (OSError, ValueError):
                continue
        document = par_document.get(chemin)
        if document is None:
            infos = infos_fichiers.get(chemin) or {}
            ocr = bool(infos.get("ocr"))
            document = {
                "name": p.name,
                "path": chemin,
                "ext": p.suffix.lower(),
                # FAISS renvoie les extraits du plus proche au plus lointain :
                # le premier vu pour un document porte donc son meilleur score.
                "score": float(score),
                "snippets": [],
                # Texte issu d'une transcription automatique : l'interface le
                # signale, la reconnaissance n'étant jamais parfaite.
                "ocr": ocr,
                "ocr_notice": ("Texte obtenu par reconnaissance automatique "
                               "sur un document scanné.") if ocr else "",
            }
            par_document[chemin] = document
        if len(document["snippets"]) < MAX_EXTRAITS_PAR_DOC:
            document["snippets"].append(_abreger(str(extrait.get("text") or "")))

    resultats = sorted(par_document.values(),
                       key=lambda r: (-r["score"], r["name"].lower()))
    tronque = len(resultats) > k
    reponse = _reponse_vide(requete, "")
    reponse["results"] = resultats[:k]
    reponse["truncated"] = tronque
    if not reponse["results"]:
        reponse["notice"] = ("Aucun document de l'index ne se rapproche de cette "
                             "demande.")
    return reponse


# ---------- Effacement (RGPD) ----------
def purger_index() -> bool:
    """Supprime l'index et ses métadonnées. Vrai si quelque chose existait.

    L'annulation est posée d'abord : une construction en cours réécrirait
    sinon, quelques secondes plus tard, les fichiers qu'on vient d'effacer.
    """
    global _cache_index
    _evenement_annulation.set()
    with _verrou_cache:
        _cache_index = None
        existait = DOSSIER_INDEX.exists()
        if existait:
            shutil.rmtree(DOSSIER_INDEX, ignore_errors=True)
    return existait
