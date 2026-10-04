"""
Paquet backend d'Olivia.

Seul rôle de ce fichier : charger `backend/.env` AVANT tout autre module. Le
README demande d'y régler FS_ROOT, OLLAMA_URL… mais le fichier n'était lu par
personne (python-dotenv figurait dans requirements.txt sans être appelé), et
ces réglages restaient sans effet. Plusieurs modules lisent l'environnement dès
leur chargement (main.py, docindex.py, emplacements.py) : le faire ici garantit
qu'ils voient les valeurs du fichier.

Une variable déjà définie dans l'environnement l'emporte sur le fichier
(override=False) : un réglage passé explicitement au lancement n'est jamais
écrasé par un .env oublié. Sans python-dotenv installé, ou sans fichier, rien
ne change.
"""
from pathlib import Path

FICHIER_ENV = Path(__file__).resolve().parent / ".env"


def charger_env(chemin: Path = FICHIER_ENV) -> bool:
    """Charge `chemin` dans l'environnement (sans écraser l'existant).
    Renvoie True si un fichier a été lu."""
    if not chemin.is_file():
        return False
    try:
        from dotenv import load_dotenv
    except ImportError:
        return False
    return bool(load_dotenv(chemin, override=False))


charger_env()
