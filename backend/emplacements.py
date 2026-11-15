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
     `dossier` : écrit par l'installeur, qui y désigne %LOCALAPPDATA%\\Olivia,
     dossier PROPRE AU COMPTE WINDOWS de la personne qui lance Olivia ;
  3. sinon le paquet `backend/` lui-même, comme avant : c'est le cas du
     disque portable (les données voyagent avec la clé) et du développement.
     Aucune installation existante ne change donc d'emplacement sans l'avoir
     demandé.

POURQUOI UN DOSSIER PAR COMPTE WINDOWS (audit du 15/11/2026) : les versions
précédentes rangeaient les données dans C:\\ProgramData\\Olivia, commun au poste
et rendu modifiable par tous ses utilisateurs. Sur un poste partagé, n'importe
quel autre compte Windows pouvait donc y lire les conversations, copier un
jeton de session ou remplacer un mot de passe. Olivia tourne sous la session
Windows de la personne : seul un dossier de SON profil Windows est protégé des
autres comptes par le système. Les données de l'ancien dossier commun sont
REPRISES au premier démarrage (voir `reprendre_dossier_commun`).

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
# Ancien dossier COMMUN au poste, à reprendre au premier démarrage : désigné par
# l'application de bureau (variable d'environnement) ou par l'installeur (clé
# `reprise` de olivia.ini). Absent sur un disque portable et en développement.
VARIABLE_REPRISE = "OLIVIA_DATA_REPRISE"
CLE_INI_REPRISE = "reprise"
# Dossier des modèles d'IA désigné par l'installeur (clé `modeles` de
# olivia.ini) : commun au poste et inscriptible, hors de Program Files.
CLE_INI_MODELES = "modeles"

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


def _lire_ini(chemin: Path, cle: str = CLE_INI) -> str:
    """Valeur de [donnees] `cle` dans `chemin`, ou "" si absente/illisible.

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
    return lecteur.get(SECTION_INI, cle, fallback="").strip()


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


def origine_donnees() -> str:
    """Origine du choix du dossier des données (ORIGINE_ENV, ORIGINE_INI ou
    ORIGINE_DEFAUT).

    Lue par backend/coffre.py : les secrets ne sont chiffrés que sur un poste
    installé (olivia.ini ou OLIVIA_DATA_DIR), jamais sur la clé portable, dont
    les données doivent rester lisibles d'un ordinateur à l'autre.
    """
    return _resoudre()[1]


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


def dossier_modeles_ini() -> Path | None:
    """Dossier des modèles d'IA désigné par olivia.ini (installeur), ou None.

    L'installeur Inno Setup y range les modèles livrés, dans
    C:\\ProgramData\\Olivia\\modeles-ia : Program Files n'est pas modifiable par
    un utilisateur standard, et un modèle téléchargé plus tard (changement de
    mode de calcul) n'aurait pas pu s'y écrire.
    """
    brut = _lire_ini(dossier_application() / NOM_INI, CLE_INI_MODELES)
    return Path(os.path.expandvars(brut)).expanduser() if brut else None


def ancien_dossier_commun() -> Path | None:
    """Ancien dossier commun au poste désigné pour une reprise, ou None."""
    brut = os.environ.get(VARIABLE_REPRISE, "").strip()
    if not brut:
        brut = _lire_ini(dossier_application() / NOM_INI, CLE_INI_REPRISE)
    return Path(os.path.expandvars(brut)).expanduser() if brut else None


def reprendre_dossier_commun(ancien: Path, nouveau: Path) -> bool:
    """Reprend les données de l'ancien dossier commun au poste (`ancien`) dans
    le dossier du compte Windows (`nouveau`), puis les RETIRE de l'ancien.

    Retrait et non simple copie, contrairement à `migrer_ancien_dossier` : le
    but est précisément que les comptes, sessions et conversations cessent
    d'être lisibles par les autres comptes Windows du poste. Le cache OCR
    commun (texte recopié de documents personnels) est retiré lui aussi : il se
    reconstruit.

    C'est le PREMIER compte Windows à lancer Olivia après la mise à jour qui
    reprend les données ; les suivants démarrent sur un dossier neuf. La copie
    est complète (dossier temporaire renommé) avant tout retrait, et un retrait
    impossible (droits) laisse simplement l'ancien dossier en place.

    Renvoie True si une reprise a eu lieu. Ne lève jamais.
    """
    if not migrer_ancien_dossier(ancien / "profiles", nouveau / "profiles"):
        return False
    for reste in (ancien / "profiles", ancien / "ocr_cache"):
        shutil.rmtree(reste, ignore_errors=True)
    return True


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
    # Ancien dossier commun au poste (C:\ProgramData\Olivia) : repris dans le
    # dossier du compte Windows, une seule fois (voir l'en-tête du module).
    commun = ancien_dossier_commun()
    if commun is not None:
        reprendre_dossier_commun(commun, racine)
    return dossier_profils
