"""
Dossiers RÉSERVÉS à Olivia : jamais lisibles ni modifiables par l'interface.

Pourquoi ce module existe : les dossiers documentaires (`fs_roots`) sont un
réglage d'organisation, choisi depuis l'interface. Sans garde-fou, une
organisation pouvait désigner comme « dossier de travail » le dossier interne
d'Olivia — ou un dossier qui le contient, comme la racine du disque — et lire
par les routes /api/fs/* les fichiers des AUTRES organisations : jetons de
session vivants (sessions.json), dérivés de mots de passe (users.json), réglages
avec les identifiants IMAP en clair (profiles/<id>/settings.json),
conversations. Le cloisonnement par dossier de profiles.py était alors
contournable en deux requêtes.

La règle est volontairement simple, et appliquée là où un chemin devient un
accès disque (`main.safe_path`, listages, balayages de recherche) plutôt qu'au
seul enregistrement des réglages : un chemin situé DANS un dossier réservé est
refusé, quelle que soit la racine par laquelle on y arrive (racine trop large,
lien symbolique, réglage enregistré par une version antérieure). Une racine qui
CONTIENT un dossier réservé reste autorisée — désigner `D:\\` ou le dossier de
la clé USB est un usage légitime — mais le dossier réservé y est invisible et
inaccessible.

Ce qui est réservé, et pourquoi :
  - le paquet `backend/` : comptes, sessions, réglages et conversations de
    toutes les organisations (`profiles/`), cache OCR commun, code ;
  - `modeles/` : modèle Word commun déposé par le service informatique, qui
    sert de repli à toutes les organisations — aucune ne doit pouvoir le
    remplacer ;
  - `tesseract/` et `ollama/` : moteurs exécutés par Olivia ;
  - en mode gelé (PyInstaller), `_internal/` : environnement Python embarqué.

Les sous-dossiers de travail placés à côté de l'application (`documents/` dans
le dépôt de développement, par exemple) ne sont PAS réservés : c'est
précisément là que l'on range souvent ses documents.
"""
import sys
from functools import lru_cache
from pathlib import Path

from . import docmodele, ocr, profiles

DOSSIER_BACKEND = Path(__file__).resolve().parent
SOUS_DOSSIER_OLLAMA = "ollama"


def dossier_application() -> Path:
    """Dossier de l'application : celui de l'exécutable en mode gelé.

    Même calcul que `APP_DIR` dans launch.py et que `_dossier_application()`
    dans ocr.py et docmodele.py (le moteur OCR, Ollama et le modèle Word vivent
    à côté de l'.exe, pas dans le dossier temporaire `_MEIPASS`).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return DOSSIER_BACKEND.parent


@lru_cache(maxsize=1)
def dossiers_reserves() -> tuple[Path, ...]:
    """Dossiers réservés, résolus. Fixes pendant toute la vie du process."""
    app = dossier_application()
    candidats = [
        DOSSIER_BACKEND,
        profiles.PROFILES_DIR,
        ocr.DOSSIER_CACHE,
        app / docmodele.SOUS_DOSSIER_MODELES,
        app / ocr.SOUS_DOSSIER_MOTEUR,
        app / SOUS_DOSSIER_OLLAMA,
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        candidats.append(Path(meipass))
    reserves: list[Path] = []
    for c in candidats:
        try:
            r = Path(c).resolve()
        except OSError:
            continue
        if r not in reserves:
            reserves.append(r)
    return tuple(reserves)


def est_reserve(chemin: Path, deja_resolu: bool = False) -> bool:
    """Vrai si `chemin` est un dossier réservé ou se trouve dessous.

    Le chemin est résolu ici (liens symboliques compris) : un lien posé dans un
    dossier de travail et pointant vers `backend/profiles/` est donc refusé au
    même titre que le chemin direct. Un chemin impossible à résoudre est traité
    comme réservé : dans le doute, on refuse.

    `deja_resolu` évite une seconde résolution quand l'appelant vient de la
    faire (balayage de milliers de fichiers pendant une recherche).
    """
    try:
        reel = Path(chemin) if deja_resolu else Path(chemin).resolve()
    except (OSError, ValueError):
        return True
    return any(reel == r or reel.is_relative_to(r) for r in dossiers_reserves())
