"""
Tableaux blancs (Excalidraw), CLOISONNÉS PAR ORGANISATION :
profiles/<profile_id>/tableaux/<id>.json, un fichier par tableau.

Même modèle que conversations.py : dossier par profil, identifiants uuid4 hex
validés contre le path-traversal, écritures mutexées et atomiques (fichier .tmp
puis remplacement), `profile_id` toujours en premier paramètre, résolu par
`main.get_current_profile()` — jamais fourni par le client.

La scène est enregistrée telle qu'Excalidraw la sérialise (format
`.excalidraw` : `elements`, `appState`, `files`). Oliv'IA ne l'interprète pas :
elle vérifie seulement sa forme et sa taille. Les images collées dans un
tableau y sont incluses en base64 (`files`), d'où la limite MAX_OCTETS : sans
elle, un tableau rempli de photos ferait enfler sans fin le dossier des
données, et chaque sauvegarde automatique avec.

Ce sont des données de l'organisation : incluses dans l'export RGPD et
supprimées par l'effacement (voir main.privacy_export / privacy_delete).
"""
import json
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

from . import profiles

SOUS_DOSSIER = "tableaux"
TITRE_PAR_DEFAUT = "Tableau sans titre"
TITRE_MAX = 80
# Scène sérialisée, images comprises. Assez pour des schémas et quelques
# captures d'écran ; au-delà, mieux vaut un document dans le dossier de travail.
MAX_OCTETS = 25 * 1024 * 1024

_lock = RLock()
_est_id_valide = profiles.is_valid_id


class TableauInvalide(ValueError):
    """Scène refusée : forme inattendue ou taille excessive (message lisible)."""


def _dossier(profile_id: str) -> Path:
    return profiles.profile_dir(profile_id) / SOUS_DOSSIER


def _chemin(profile_id: str, tableau_id: str) -> Path:
    return _dossier(profile_id) / f"{tableau_id}.json"


def _titre(titre) -> str:
    texte = " ".join(str(titre or "").split())[:TITRE_MAX]
    return texte or TITRE_PAR_DEFAUT


def _scene_valide(scene) -> dict:
    """Vérifie la forme d'une scène Excalidraw et sa taille sérialisée."""
    if scene is None:
        return {"type": "excalidraw", "version": 2, "elements": [], "appState": {}, "files": {}}
    if not isinstance(scene, dict):
        raise TableauInvalide("La scène doit être un objet JSON.")
    if not isinstance(scene.get("elements", []), list):
        raise TableauInvalide("La scène est mal formée (« elements » doit être une liste).")
    for cle in ("appState", "files"):
        if not isinstance(scene.get(cle, {}), dict):
            raise TableauInvalide(f"La scène est mal formée (« {cle} » doit être un objet).")
    taille = len(json.dumps(scene, ensure_ascii=False).encode("utf-8"))
    if taille > MAX_OCTETS:
        raise TableauInvalide(
            f"Tableau trop volumineux ({taille / 1e6:.1f} Mo, {MAX_OCTETS // (1024 * 1024)} Mo "
            "au plus) : retirez ou réduisez des images."
        )
    return scene


def _enregistrer(profile_id: str, donnees: dict) -> None:
    dossier = _dossier(profile_id)
    dossier.mkdir(parents=True, exist_ok=True)
    chemin = dossier / f"{donnees['id']}.json"
    tmp = chemin.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(donnees, f, ensure_ascii=False)
    tmp.replace(chemin)


def lister(profile_id: str) -> list[dict]:
    """Métadonnées des tableaux de CETTE organisation, du plus récent au plus
    ancien. Un fichier illisible est ignoré."""
    dossier = _dossier(profile_id)
    with _lock:
        if not dossier.exists():
            return []
        resultats = []
        for f in dossier.glob("*.json"):
            if not _est_id_valide(f.stem):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    d = json.load(fh)
                elements = d.get("scene", {}).get("elements", [])
                resultats.append({
                    "id": d["id"],
                    "titre": d.get("titre", TITRE_PAR_DEFAUT),
                    "modifie_le": d.get("modifie_le", 0),
                    "elements": sum(1 for e in elements
                                    if isinstance(e, dict) and not e.get("isDeleted")),
                })
            except Exception:
                continue
        resultats.sort(key=lambda t: t["modifie_le"], reverse=True)
        return resultats


def lire(profile_id: str, tableau_id: str) -> dict | None:
    """Tableau complet, ou None (absent, invalide, ou d'une autre organisation)."""
    if not _est_id_valide(tableau_id):
        return None
    with _lock:
        chemin = _chemin(profile_id, tableau_id)
        if not chemin.exists():
            return None
        try:
            with open(chemin, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def creer(profile_id: str, titre=None, scene=None) -> dict:
    scene = _scene_valide(scene)
    with _lock:
        maintenant = time.time()
        donnees = {
            "id": uuid4().hex,
            "titre": _titre(titre),
            "cree_le": maintenant,
            "modifie_le": maintenant,
            "scene": scene,
        }
        _enregistrer(profile_id, donnees)
        return donnees


def modifier(profile_id: str, tableau_id: str, titre=None, scene=None) -> dict | None:
    """Met à jour le titre et/ou la scène. None si le tableau n'existe pas."""
    if scene is not None:
        scene = _scene_valide(scene)
    with _lock:
        donnees = lire(profile_id, tableau_id)
        if donnees is None:
            return None
        if titre is not None:
            donnees["titre"] = _titre(titre)
        if scene is not None:
            donnees["scene"] = scene
        donnees["modifie_le"] = time.time()
        _enregistrer(profile_id, donnees)
        return donnees


def supprimer(profile_id: str, tableau_id: str) -> bool:
    if not _est_id_valide(tableau_id):
        return False
    with _lock:
        chemin = _chemin(profile_id, tableau_id)
        if not chemin.exists():
            return False
        chemin.unlink()
        return True


def supprimer_tout(profile_id: str) -> int:
    """RGPD : supprime les tableaux de CETTE organisation seulement."""
    dossier = _dossier(profile_id)
    with _lock:
        if not dossier.exists():
            return 0
        n = 0
        for f in dossier.glob("*.json"):
            try:
                f.unlink()
                n += 1
            except OSError:
                pass
        return n


def exporter_tout(profile_id: str) -> list[dict]:
    """RGPD : tableaux complets de CETTE organisation, pour l'export."""
    with _lock:
        return [d for d in (lire(profile_id, t["id"]) for t in lister(profile_id)) if d]
