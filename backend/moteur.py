"""
État du moteur d'IA (Ollama) sur ce poste : est-il joignable, et les modèles
dont Olivia a besoin sont-ils installés ?

Sert le panneau « Olivia n'est pas encore prête » de l'interface. Sans lui, un
poste neuf (application de bureau installée, Ollama absent ou modèles non
tirés) ne s'en apercevait qu'au premier message, qui échouait : l'utilisatrice
découvrait la panne au lieu d'être guidée vers son remède.

Les modèles attendus ne sont PAS une liste de plus à maintenir : le modèle de
conversation vient de `settings.DEVICE_MODELS` (selon le périphérique de
l'organisation connectée), celui des embeddings de `docindex.EMBED_MODEL`.

Téléchargement depuis Oliv'IA : l'application de bureau embarque le moteur
mais pas les modèles (plusieurs Go). `lancer_telechargement` les fait tirer par
Ollama (`POST /api/pull`, réponse en flux) dans un fil d'arrière-plan, et
`etat()` en rapporte la progression. Seuls les modèles attendus peuvent être
téléchargés : jamais un nom fourni librement par le client.
"""
import json
import threading

import httpx

from . import docindex
from .settings import DEVICE_MODELS

# Court : la question est « Ollama répond-il ? », pas « termine-t-il un calcul ».
# Un moteur sain répond à /api/tags en quelques millisecondes ; attendre plus
# ne ferait que geler le panneau quand il est éteint.
DELAI_REPONSE_S = 3.0

# Niveau d'exigence de chaque modèle, du plus au moins bloquant.
INDISPENSABLE = "indispensable"   # sans lui, pas de conversation
CONSEILLE = "conseille"           # une fonction secondaire en dépend
FACULTATIF = "facultatif"         # utile seulement si l'on change de réglage

# Noms des modes tels qu'affichés dans la barre du haut (App.vue).
LIBELLES_MODES = {
    "gpu": "mode ⚡ Rapide (GPU)",
    "cpu": "mode 🧩 Standard (CPU)",
    "leger": "mode 🪶 Léger (petits postes)",
}


def modeles_attendus(peripherique: str) -> list[dict]:
    """Modèles utiles à Olivia, selon le mode de calcul (« gpu », « cpu »,
    « leger ») choisi."""
    actuel = peripherique if peripherique in DEVICE_MODELS else "gpu"
    attendus = [
        {"nom": DEVICE_MODELS[actuel][0], "niveau": INDISPENSABLE,
         "role": f"conversation — {LIBELLES_MODES[actuel]}, réglage actuel"},
        {"nom": docindex.EMBED_MODEL, "niveau": CONSEILLE,
         "role": "recherche dans les documents par le sens"},
    ] + [
        {"nom": DEVICE_MODELS[autre][0], "niveau": FACULTATIF,
         "role": f"conversation — {LIBELLES_MODES[autre]}, si l'on change de mode"}
        for autre in DEVICE_MODELS if autre != actuel
    ]
    # Une configuration où deux modes partagent le même modèle ne doit pas le
    # demander deux fois.
    vus, uniques = set(), []
    for m in attendus:
        if m["nom"] not in vus:
            vus.add(m["nom"])
            uniques.append(m)
    return uniques


def est_installe(nom: str, installes: set[str]) -> bool:
    """Ollama nomme « bge-m3:latest » un modèle tiré sous le nom « bge-m3 »."""
    if nom in installes:
        return True
    return ":" not in nom and f"{nom}:latest" in installes


def analyser(peripherique: str, installes: set[str] | None) -> dict:
    """Assemble l'état à partir de la liste des modèles installés.

    `installes` vaut None quand Ollama n'a pas répondu : on ne sait alors rien
    des modèles, et on ne prétend pas qu'ils manquent.
    """
    joignable = installes is not None
    modeles = []
    for m in modeles_attendus(peripherique):
        present = est_installe(m["nom"], installes) if joignable else None
        modeles.append({**m, "installe": present})
    pret = joignable and all(
        m["installe"] for m in modeles if m["niveau"] == INDISPENSABLE)
    complet = joignable and all(
        m["installe"] for m in modeles if m["niveau"] != FACULTATIF)
    return {"joignable": joignable, "pret": pret, "complet": complet, "modeles": modeles}


async def etat(ollama_url: str, peripherique: str) -> dict:
    """Interroge Ollama (`GET /api/tags`) et renvoie l'état du moteur, avec la
    progression des téléchargements lancés depuis Oliv'IA."""
    try:
        async with httpx.AsyncClient(timeout=DELAI_REPONSE_S) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            r.raise_for_status()
            installes = {m.get("name", "") for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError, AttributeError):
        installes = None
    resultat = analyser(peripherique, installes)
    suivis = etat_telechargements()
    for m in resultat["modeles"]:
        m["telechargement"] = suivis.get(m["nom"])
    return resultat


# ---------- Téléchargement des modèles ----------
# Un suivi par modèle, partagé par toutes les organisations : les modèles sont
# un bien de la machine, pas d'une organisation. Mémoire seulement : après un
# redémarrage, Ollama reprend un téléchargement interrompu là où il s'était
# arrêté (couches déjà reçues conservées), il suffit de le relancer.
EN_COURS, TERMINE, ERREUR = "en_cours", "termine", "erreur"
_suivis: dict[str, dict] = {}
_verrou = threading.Lock()

# Connexion courte, lecture longue : entre deux lignes de progression, Ollama
# peut se taire le temps de vérifier une couche de plusieurs Go.
DELAIS_PULL = httpx.Timeout(10.0, read=600.0)


def etat_telechargements() -> dict[str, dict]:
    with _verrou:
        return {nom: dict(suivi) for nom, suivi in _suivis.items()}


def lancer_telechargement(ollama_url: str, nom: str) -> bool:
    """Démarre le téléchargement de `nom` en arrière-plan.

    Renvoie False s'il est déjà en cours (deux clics, deux postes connectés) :
    un second `pull` du même modèle ne ferait que doubler le trafic.
    """
    with _verrou:
        if _suivis.get(nom, {}).get("etat") == EN_COURS:
            return False
        _suivis[nom] = {"etat": EN_COURS, "fait": 0, "total": 0, "message": "Démarrage…"}
    threading.Thread(target=_telecharger, args=(ollama_url, nom), daemon=True,
                     name=f"pull-{nom}").start()
    return True


def _maj(nom: str, **champs) -> None:
    with _verrou:
        _suivis[nom].update(champs)


def _telecharger(ollama_url: str, nom: str) -> None:
    couches: dict[str, tuple[int, int]] = {}      # condensat -> (reçu, total)
    try:
        with httpx.Client(timeout=DELAIS_PULL) as client, \
                client.stream("POST", f"{ollama_url}/api/pull",
                              json={"model": nom, "stream": True}) as r:
            if r.status_code >= 400:
                r.read()
                raise RuntimeError(_message_erreur(r.status_code, r.text))
            for ligne in r.iter_lines():
                if not ligne.strip():
                    continue
                evt = json.loads(ligne)
                if evt.get("error"):
                    raise RuntimeError(str(evt["error"]))
                statut = str(evt.get("status", ""))
                if evt.get("digest") and evt.get("total"):
                    couches[evt["digest"]] = (int(evt.get("completed") or 0), int(evt["total"]))
                fait = sum(c for c, _ in couches.values())
                total = sum(t for _, t in couches.values())
                if statut == "success":
                    _maj(nom, etat=TERMINE, fait=total, total=total, message="Installé")
                    return
                _maj(nom, fait=fait, total=total, message=statut)
        raise RuntimeError("Le téléchargement s'est interrompu avant la fin.")
    except (httpx.HTTPError, ValueError, RuntimeError) as e:
        if isinstance(e, httpx.ConnectError):
            message = "Le moteur d'IA ne répond pas : impossible de télécharger le modèle."
        elif isinstance(e, httpx.HTTPError):
            message = (f"Téléchargement interrompu ({e.__class__.__name__}). "
                       "Réessayez : il reprendra où il s'était arrêté.")
        else:
            message = str(e)
        _maj(nom, etat=ERREUR, message=message)


def _message_erreur(statut: int, corps: str) -> str:
    try:
        detail = json.loads(corps).get("error") or corps
    except (ValueError, AttributeError):
        detail = corps
    return f"Le moteur d'IA a refusé le téléchargement (erreur {statut}) : {str(detail)[:200]}"
