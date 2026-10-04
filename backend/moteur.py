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
"""
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


def modeles_attendus(peripherique: str) -> list[dict]:
    """Modèles utiles à Olivia, selon le périphérique (« gpu » / « cpu ») choisi."""
    actuel = peripherique if peripherique in DEVICE_MODELS else "gpu"
    autre = "cpu" if actuel == "gpu" else "gpu"
    libelles = {"gpu": "mode ⚡ Rapide (GPU)", "cpu": "mode 🧩 Standard (CPU)"}
    attendus = [
        {"nom": DEVICE_MODELS[actuel][0], "niveau": INDISPENSABLE,
         "role": f"conversation — {libelles[actuel]}, réglage actuel"},
        {"nom": docindex.EMBED_MODEL, "niveau": CONSEILLE,
         "role": "recherche dans les documents par le sens"},
        {"nom": DEVICE_MODELS[autre][0], "niveau": FACULTATIF,
         "role": f"conversation — {libelles[autre]}, si l'on change de mode"},
    ]
    # Une configuration où les deux périphériques partagent le même modèle ne
    # doit pas le demander deux fois.
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
    """Interroge Ollama (`GET /api/tags`) et renvoie l'état du moteur."""
    try:
        async with httpx.AsyncClient(timeout=DELAI_REPONSE_S) as client:
            r = await client.get(f"{ollama_url}/api/tags")
            r.raise_for_status()
            installes = {m.get("name", "") for m in r.json().get("models", [])}
    except (httpx.HTTPError, ValueError, AttributeError):
        installes = None
    return analyser(peripherique, installes)
