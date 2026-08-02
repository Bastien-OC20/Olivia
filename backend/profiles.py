"""
Registre des profils (organisations) dans backend/profiles/registry.json.

Un « profil » est une organisation cliente d'Olivia : mairie, association, PME.
Le dossier backend/profiles/ est aussi la racine du stockage cloisonné par
organisation (un sous-dossier par profil) — d'où la validation stricte des
identifiants avant toute utilisation dans un chemin disque.

Le fichier est créé au premier écrit. Toutes les écritures sont mutexées et
atomic-write sur disque (fichier .tmp puis remplacement), comme conversations.py
et settings.py.
"""
import json
import re
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

_ID_RE = re.compile(r"^[0-9a-f]{32}$")

PROFILES_DIR = Path(__file__).parent / "profiles"
REGISTRY_PATH = PROFILES_DIR / "registry.json"

# Verrou unique pour les trois fichiers de ce dossier (profils, comptes,
# sessions) : ils sont petits, écrits rarement (provisionnement, connexion), et
# un seul verrou réentrant évite d'avoir à raisonner sur un ordre de prise entre
# plusieurs verrous — par exemple quand créer un compte vérifie un profil.
store_lock = RLock()
_lock = store_lock  # alias local, pour rester lisible dans ce module

NAME_MAX_LEN = 120


def is_valid_id(profile_id: str) -> bool:
    """Valide un identifiant de profil avant toute utilisation dans un chemin
    disque : refuse tout ce qui ne ressemble pas à un uuid4().hex, ce qui exclut
    d'office les tentatives de path traversal.

    Volontairement public (contrairement à _is_valid_id de conversations.py) :
    users.py et sessions.py manipulent le même identifiant et doivent appliquer
    exactement le même filtre, sans le redéfinir chacun de leur côté.
    """
    return bool(_ID_RE.match(profile_id or ""))


def profile_dir(profile_id: str) -> Path:
    """Dossier de stockage cloisonné d'un profil : backend/profiles/<profile_id>/.

    C'est le SEUL endroit où un identifiant de profil devient un chemin disque
    (settings.json, conversations/, docindex/ y sont rangés) — donc le seul
    endroit où la validation anti-traversal doit être garantie. Lève ValueError
    sur un identifiant invalide plutôt que de renvoyer un chemin de repli : un
    profile_id arrive toujours de `get_current_profile()`, jamais du client, donc
    un identifiant douteux signale un bug à faire remonter, pas une entrée à
    corriger silencieusement.

    Ne crée pas le dossier : chaque module le fait au moment d'écrire, comme
    aujourd'hui pour conversations/ et l'index.
    """
    if not is_valid_id(profile_id):
        raise ValueError(f"Identifiant de profil invalide : {profile_id!r}")
    return PROFILES_DIR / profile_id


def read_store(path: Path, cle: str, vide: list | dict | None = None) -> dict:
    """Lit un fichier du registre, ou renvoie une structure vide (`vide`) s'il
    n'existe pas encore (premier démarrage).

    Un fichier présent mais illisible fait remonter une erreur au lieu d'être
    ignoré : contrairement à une conversation ou à un réglage, un profil ou un
    compte ne se reconstruit pas — repartir silencieusement d'une structure vide
    ferait effacer les comptes existants au prochain enregistrement.

    Mutualisé avec users.py et sessions.py, qui persistent le même genre de
    fichier au même endroit.
    """
    if not path.exists():
        return {cle: [] if vide is None else vide}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        raise RuntimeError(f"{path.name} est illisible ou corrompu : {exc}") from exc
    if not isinstance(data, dict) or cle not in data:
        raise RuntimeError(f"{path.name} n'a pas la structure attendue (clé « {cle} » absente)")
    return data


def write_store(path: Path, data: dict):
    """Écriture atomique : .tmp puis remplacement (mutualisé, voir read_store)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def list_profiles() -> list[dict]:
    """Tous les profils connus, triés par date de création croissante."""
    with _lock:
        profils = read_store(REGISTRY_PATH, "profiles")["profiles"]
        return sorted(profils, key=lambda p: p.get("created_at", 0))


def get_profile(profile_id: str) -> dict | None:
    """Profil correspondant à l'identifiant, ou None s'il est invalide/inconnu."""
    if not is_valid_id(profile_id):
        return None
    with _lock:
        for p in read_store(REGISTRY_PATH, "profiles")["profiles"]:
            if p.get("id") == profile_id:
                return dict(p)
        return None


def create_profile(name: str) -> dict:
    """Crée un profil et le persiste. Lève ValueError si le nom est vide.

    Les homonymes ne sont pas refusés : le nom est un libellé d'affichage, c'est
    l'identifiant qui compte — et deux organisations peuvent légitimement porter
    le même nom d'usage.
    """
    libelle = (name or "").strip()
    if not libelle:
        raise ValueError("Le nom du profil est obligatoire")
    if len(libelle) > NAME_MAX_LEN:
        raise ValueError(f"Le nom du profil dépasse {NAME_MAX_LEN} caractères")
    with _lock:
        data = read_store(REGISTRY_PATH, "profiles")
        profil = {"id": uuid4().hex, "name": libelle, "created_at": time.time()}
        data["profiles"].append(profil)
        write_store(REGISTRY_PATH, data)
        return dict(profil)
