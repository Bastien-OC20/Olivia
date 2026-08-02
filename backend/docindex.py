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

CLOISONNEMENT : un index par organisation, dans
backend/profiles/<profile_id>/docindex/. Toutes les fonctions publiques prennent
le `profile_id` en PREMIER paramètre, résolu par `main.get_current_profile()` —
jamais fourni par le client. L'état vivant du module (verrou de construction,
progression, annulation, cache mémoire de l'index) est lui aussi keyé par
organisation : voir la section « État par organisation » plus bas.
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
from . import profiles

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
# Volontairement placé sous backend/profiles/<profile_id>/, à côté des
# conversations et des réglages de la même organisation : sur le disque portable,
# l'index voyage donc avec l'application, et il disparaît avec le profil auquel
# il appartient (droit à l'effacement).
SOUS_DOSSIER_INDEX = "docindex"
NOM_INDEX = "index.faiss"
NOM_META = "meta.json"
VERSION_META = 1                       # à incrémenter si le format des métadonnées change


def dossier_index(profile_id: str) -> Path:
    """Dossier d'index d'une organisation (valide l'identifiant, voir profiles.py)."""
    return profiles.profile_dir(profile_id) / SOUS_DOSSIER_INDEX


def _fichier_index(profile_id: str) -> Path:
    return dossier_index(profile_id) / NOM_INDEX


def _fichier_meta(profile_id: str) -> Path:
    return dossier_index(profile_id) / NOM_META


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

# ---------- État par organisation ----------
# TOUT l'état vivant de ce module est keyé par profile_id, et ce n'est pas une
# précaution théorique. Avec un verrou de construction et un dict de progression
# uniques pour le process :
#   - deux organisations qui indexent en même temps se bloquent (la seconde est
#     refusée sans raison visible à l'écran) ;
#   - la progression affichée à l'une décrit les fichiers de l'autre ;
#   - le cache mémoire de l'index, chargé sans savoir de qui il vient, peut
#     répondre à une organisation avec les extraits de sa voisine.
# `_verrou_etats` ne protège QUE ces tables (accès très courts) ; le contenu d'un
# index reste protégé par le verrou de construction de son propre profil.
_verrou_etats = threading.Lock()
_verrous_construction: dict[str, threading.Lock] = {}
_evenements_annulation: dict[str, threading.Event] = {}
_progres: dict[str, dict] = {}

# Cache mémoire de l'index chargé, un par organisation. Invalidé sur la date de
# modification de meta.json : une construction qui vient de se terminer est donc
# vue immédiatement par la recherche.
_verrou_cache = threading.Lock()
_cache_index: dict[str, tuple] = {}    # profile_id -> (mtime_ns, index, meta)


def _progres_vide() -> dict:
    return {"en_cours": False, "fait": 0, "total": 0, "fichier": "", "erreur": ""}


def _verrou_construction(profile_id: str) -> threading.Lock:
    """Verrou de construction propre à une organisation (créé à la demande)."""
    with _verrou_etats:
        verrou = _verrous_construction.get(profile_id)
        if verrou is None:
            verrou = threading.Lock()
            _verrous_construction[profile_id] = verrou
        return verrou


def _annulation(profile_id: str) -> threading.Event:
    """Drapeau d'annulation propre à une organisation (créé à la demande)."""
    with _verrou_etats:
        evenement = _evenements_annulation.get(profile_id)
        if evenement is None:
            evenement = threading.Event()
            _evenements_annulation[profile_id] = evenement
        return evenement


def _lire_progres(profile_id: str) -> dict:
    with _verrou_etats:
        return dict(_progres.get(profile_id) or _progres_vide())


def _maj_progres(profile_id: str, **champs) -> None:
    with _verrou_etats:
        etat_profil = _progres.get(profile_id)
        if etat_profil is None:
            etat_profil = _progres_vide()
            _progres[profile_id] = etat_profil
        etat_profil.update(champs)


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
            # keep_alive=-1 : évite de repayer le chargement de bge-m3
            # (dizaines de secondes sans GPU) après chaque pause > 5 min.
            json={"model": EMBED_MODEL, "input": textes, "keep_alive": -1},
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


def _charger(profile_id: str, depuis_disque: bool = False) -> tuple:
    """(index, métadonnées) de CETTE organisation lus sur disque, ou (None, None).

    `depuis_disque` court-circuite le cache mémoire : la construction MODIFIE
    l'index qu'elle reçoit, elle ne doit donc jamais travailler sur l'objet
    partagé avec les recherches en cours.

    Toute incohérence — modèle ou dimension différents, nombre de vecteurs qui
    ne correspond plus aux métadonnées — est traitée comme une absence d'index :
    il sera simplement reconstruit. Jamais d'exception, jamais de résultat faux.
    """
    if not FAISS_DISPONIBLE:
        return None, None
    chemin_meta = _fichier_meta(profile_id)
    try:
        mtime = chemin_meta.stat().st_mtime_ns
    except OSError:
        return None, None
    if not depuis_disque:
        with _verrou_cache:
            en_cache = _cache_index.get(profile_id)
            if en_cache is not None and en_cache[0] == mtime:
                return en_cache[1], en_cache[2]
    try:
        with open(chemin_meta, encoding="utf-8") as f:
            meta = json.load(f)
        index = faiss.read_index(str(_fichier_index(profile_id)))
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
            _cache_index[profile_id] = (mtime, index, meta)
    return index, meta


def _sauver(profile_id: str, index, meta: dict) -> bool:
    """Écrit l'index puis les métadonnées de cette organisation, chacun de façon
    atomique.

    L'ORDRE compte : l'index d'abord, les métadonnées ensuite. Si la machine
    s'arrête entre les deux, le meta.json encore en place décrit un index plus
    ancien mais parfaitement valide — jamais l'inverse, qui pointerait vers des
    extraits inexistants.
    """
    try:
        chemin_index = _fichier_index(profile_id)
        chemin_meta = _fichier_meta(profile_id)
        chemin_index.parent.mkdir(parents=True, exist_ok=True)
        meta["built_at"] = datetime.now().isoformat(timespec="seconds")
        tmp_index = chemin_index.with_suffix(".tmp")
        faiss.write_index(index, str(tmp_index))
        tmp_index.replace(chemin_index)
        tmp_meta = chemin_meta.with_suffix(".tmp")
        with open(tmp_meta, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        tmp_meta.replace(chemin_meta)
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
def construire_index(profile_id: str, fichiers,
                     on_progress: Optional[Callable[[dict], None]] = None) -> dict:
    """Construit ou met à jour l'index de CETTE organisation. BLOQUANTE : à
    appeler dans un thread.

    `fichiers` : itérable de tuples (chemin absolu, chemin virtuel affiché) —
    même contrat que `main._iter_searchable_files`. C'est l'appelant qui l'a
    construit à partir des `fs_roots` du même profil : ce module ne voit donc
    jamais les documents d'une autre organisation.

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

    index, meta = _charger(profile_id, depuis_disque=True)
    if index is None or meta is None:
        index, meta = _index_vide(), _meta_vide()

    annulation = _annulation(profile_id)
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
            if annulation.is_set():
                resume["annule"] = True
                break
            fait += 1
            if on_progress is not None:
                try:
                    on_progress({"fait": fait, "total": total, "fichier": chemin.name})
                except Exception:
                    pass               # l'affichage ne doit pas casser la construction
            if not documents.est_cherchable(profile_id, chemin.suffix):
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
            traite, premier_appel = _indexer_fichier(profile_id, index, meta, chemin,
                                                     cle, st, client, premier_appel)
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
                _sauver(profile_id, index, meta)
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
        _sauver(profile_id, index, meta)
    return resume


def _indexer_fichier(profile_id: str, index, meta: dict, chemin: Path, cle: str, st,
                     client: httpx.Client, premier_appel: bool) -> tuple:
    """Vectorise UN fichier et remplace ses extraits dans l'index.

    Renvoie (nombre d'extraits, premier_appel), ou (None, premier_appel) en cas
    d'échec. Un fichier n'est jamais indexé À MOITIÉ : si un seul lot
    d'embeddings échoue, ses anciennes entrées sont laissées intactes et il sera
    retenté à la prochaine construction.
    """
    try:
        texte, provenance = documents.extract_text_meta(profile_id, chemin)
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
def _construire_en_thread(profile_id: str, fichiers) -> None:
    """Corps du thread de construction d'UNE organisation.

    `fichiers` est encore un GÉNÉRATEUR : le matérialiser coûte quelques
    centaines de millisecondes sur un gros dossier, et c'est précisément
    pourquoi ce travail est fait ici et non dans la requête HTTP.

    Le `finally` est vital : sans lui, une erreur inattendue laisserait le
    verrou de ce profil pris et interdirait toute construction ultérieure
    jusqu'au redémarrage de l'application.
    """
    def noter(etape: dict) -> None:
        _maj_progres(profile_id,
                     fait=int(etape.get("fait") or 0),
                     total=int(etape.get("total") or 0),
                     fichier=str(etape.get("fichier") or ""))

    try:
        construire_index(profile_id, fichiers, on_progress=noter)
    except Exception as e:
        _maj_progres(profile_id, erreur=f"{type(e).__name__} : {e}")
    finally:
        _maj_progres(profile_id, en_cours=False, fichier="")
        _verrou_construction(profile_id).release()


def lancer_construction(profile_id: str, fichiers) -> bool:
    """Démarre un thread démon si aucune construction n'est en cours POUR CETTE
    organisation.

    Renvoie False sans rien faire si une construction tourne déjà pour elle :
    deux constructions simultanées écriraient le même index. Une autre
    organisation, elle, n'est pas bloquée — elle a son propre verrou.
    """
    if not FAISS_DISPONIBLE:
        return False
    verrou = _verrou_construction(profile_id)
    if not verrou.acquire(blocking=False):
        return False
    _annulation(profile_id).clear()
    _maj_progres(profile_id, en_cours=True, fait=0, total=0, fichier="", erreur="")
    try:
        threading.Thread(target=_construire_en_thread, args=(profile_id, fichiers),
                         daemon=True).start()
    except Exception as e:
        _maj_progres(profile_id, en_cours=False, erreur=f"{type(e).__name__} : {e}")
        verrou.release()
        return False
    return True


def annuler_construction(profile_id: str) -> None:
    """Demande l'arrêt de la construction de cette organisation (effectif entre
    deux fichiers)."""
    _annulation(profile_id).set()


# ---------- État, pour l'interface ----------
def etat(profile_id: str) -> dict:
    """État de la recherche par le sens de cette organisation (Paramètres)."""
    instantane = _lire_progres(profile_id)
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
    index, meta = _charger(profile_id)
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


def rechercher(profile_id: str, requete: str, k: int = 10,
               dossier: Optional[Path] = None) -> dict:
    """Documents de CETTE organisation les plus proches du SENS de la requête.

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

    index, meta = _charger(profile_id)
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
def purger_index(profile_id: str) -> bool:
    """Supprime l'index et les métadonnées de CETTE organisation, et d'elle seule.
    Vrai si quelque chose existait.

    L'annulation est posée d'abord : une construction en cours réécrirait
    sinon, quelques secondes plus tard, les fichiers qu'on vient d'effacer.
    """
    _annulation(profile_id).set()
    dossier = dossier_index(profile_id)
    with _verrou_cache:
        _cache_index.pop(profile_id, None)
        existait = dossier.exists()
        if existait:
            shutil.rmtree(dossier, ignore_errors=True)
    return existait
