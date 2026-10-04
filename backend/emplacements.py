"""
Emplacement des DONNÉES d'Olivia (comptes, sessions, réglages, conversations,
index, cache OCR) — distinct de celui de l'APPLICATION.

Pourquoi : l'installeur Windows (installer Olivia/olivia.iss) place
l'application dans Program Files, qu'un utilisateur standard ne peut pas
modifier. Tant que les données vivaient dans `backend/` à côté du code, la
moindre écriture (ouvrir une session à la connexion, enregistrer un réglage)
échouait sur un poste installé — sauf à lancer Olivia en administrateur.

Trois cas, par ordre de priorité (voir `dossier_donnees`) :
  1. variable d'environnement OLIVIA_DATA_DIR : choix explicite de l'exploitant ;
  2. fichier `olivia.ini` à côté de l'application, section [donnees], clé
     `dossier` : écrit par l'installeur, qui y désigne C:\\ProgramData\\Olivia
     (dossier commun au poste, ouvert en écriture aux utilisateurs) ;
  3. sinon le paquet `backend/` lui-même, comme avant : c'est le cas du
     disque portable (les données voyagent avec la clé) et du développement.
     Aucune installation existante ne change donc d'emplacement sans l'avoir
     demandé.

Ce module ne dépend d'aucun autre module du backend : profiles.py et ocr.py
l'importent pour calculer leurs chemins au chargement.
"""
import configparser
import os
import shutil
import sys
from pathlib import Path

DOSSIER_BACKEND = Path(__file__).resolve().parent
VARIABLE_ENV = "OLIVIA_DATA_DIR"
NOM_INI = "olivia.ini"
SECTION_INI = "donnees"
CLE_INI = "dossier"

ORIGINE_ENV = "variable d'environnement"
ORIGINE_INI = "installation"
ORIGINE_DEFAUT = "application"


def dossier_application() -> Path:
    """Dossier de l'application : celui de l'exécutable en mode gelé.

    Même calcul que `APP_DIR` dans launch.py : en mode gelé, `sys._MEIPASS`
    (le dossier `_internal/`) ne convient pas, `olivia.ini` et les moteurs
    vivent à côté de l'.exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return DOSSIER_BACKEND.parent


def _lire_ini(chemin: Path) -> str:
    """Valeur de [donnees] dossier dans `chemin`, ou "" si absente/illisible.

    Un fichier présent mais illisible ne doit pas empêcher Olivia de démarrer :
    on retombe alors sur l'emplacement par défaut, et le lanceur affiche
    l'emplacement réellement retenu (voir `description`).
    """
    if not chemin.is_file():
        return ""
    lecteur = configparser.ConfigParser(interpolation=None)
    try:
        # utf-8-sig : l'installeur ou un éditeur Windows peut poser un BOM.
        lecteur.read(chemin, encoding="utf-8-sig")
    except (configparser.Error, OSError, UnicodeDecodeError):
        return ""
    return lecteur.get(SECTION_INI, CLE_INI, fallback="").strip()


def _resoudre() -> tuple[Path, str]:
    """(dossier des données, origine du choix)."""
    brut = os.environ.get(VARIABLE_ENV, "").strip()
    if brut:
        return Path(os.path.expandvars(brut)).expanduser(), ORIGINE_ENV
    brut = _lire_ini(dossier_application() / NOM_INI)
    if brut:
        return Path(os.path.expandvars(brut)).expanduser(), ORIGINE_INI
    return DOSSIER_BACKEND, ORIGINE_DEFAUT


def dossier_donnees() -> Path:
    """Dossier racine des données d'Olivia (voir l'en-tête du module).

    Les modules qui en dépendent (profiles.py, ocr.py) le lisent UNE fois, au
    chargement : changer la variable d'environnement ou `olivia.ini` demande
    donc un redémarrage, comme tout réglage d'installation.
    """
    return _resoudre()[0]


def description() -> str:
    """Ligne lisible pour le lanceur : où sont les données, et pourquoi là."""
    chemin, origine = _resoudre()
    return f"{chemin}  ({origine})"


def migrer_ancien_dossier(ancien: Path, nouveau: Path) -> bool:
    """Recopie les profils restés à l'ancien emplacement vers le nouveau.

    Cas visé : un poste installé avec une version antérieure de l'installeur,
    dont les comptes et conversations ont été écrits dans Program Files (si
    Olivia y a tourné en administrateur). Sans cette recopie, la mise à jour
    ferait disparaître comptes et conversations.

    COPIE et non déplacement : l'ancien dossier reste en place comme
    sauvegarde, et Program Files n'est de toute façon pas modifiable par un
    utilisateur standard. N'agit que si le nouveau dossier n'existe pas encore —
    une donnée déjà présente au nouvel emplacement n'est jamais écrasée. La copie
    passe par un dossier temporaire renommé à la fin : une interruption ne
    laisse pas un dossier à moitié rempli qui bloquerait la migration suivante.

    Renvoie True si une copie a eu lieu. Ne lève jamais : un échec laisse
    simplement Olivia démarrer sur un dossier neuf.
    """
    try:
        if nouveau.exists() or not (ancien / "registry.json").is_file():
            return False
        if ancien.resolve() == nouveau.resolve():
            return False
        temporaire = nouveau.with_name(nouveau.name + ".migration")
        if temporaire.exists():
            shutil.rmtree(temporaire)
        nouveau.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ancien, temporaire)
        temporaire.replace(nouveau)
        return True
    except OSError:
        return False


def preparer() -> Path:
    """Calcule le dossier des profils et, en mode installé, migre l'ancien.

    Appelée une seule fois, par profiles.py au chargement. La migration n'est
    tentée que lorsque l'emplacement vient de `olivia.ini` (installeur) : c'est
    le seul cas où des données peuvent être restées dans l'ancien dossier de
    l'application. Un OLIVIA_DATA_DIR posé à la main n'emporte rien avec lui.
    """
    racine, origine = _resoudre()
    dossier_profils = racine / "profiles"
    if origine == ORIGINE_INI:
        migrer_ancien_dossier(DOSSIER_BACKEND / "profiles", dossier_profils)
    return dossier_profils
