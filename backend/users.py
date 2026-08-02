"""
Comptes utilisateurs dans backend/profiles/users.json.

Un compte appartient à exactement UN profil (cadrage v1 : ni compte
multi-organisation, ni rôles internes — « connecté et rattaché à un profil »
suffit). Mêmes garanties d'écriture que conversations.py : verrou RLock et
atomic-write, mutualisés via profiles.py.

Le mot de passe n'est jamais stocké ni journalisé en clair : seul un dérivé
PBKDF2-HMAC-SHA256 salé est conservé, sous la forme « <sel_hex>$<dérivé_hex> ».
Choix du stdlib (hashlib + secrets) plutôt que bcrypt/passlib : cohérent avec la
politique de dépendances minimales du projet (voir requirements.txt), et PBKDF2
est un dérivé de mot de passe légitime dès lors que le coût est suffisant.
"""
import hashlib
import secrets
import time
from uuid import uuid4

from .profiles import (
    PROFILES_DIR, get_profile, is_valid_id, read_store, store_lock, write_store,
)

USERS_PATH = PROFILES_DIR / "users.json"

# Coût du dérivé. Le nombre d'itérations n'est délibérément PAS stocké dans
# password_hash (format « sel$dérivé » volontairement minimal) : le changer
# invaliderait donc les mots de passe existants, qu'il faudrait redéfinir via
# manage_users.py. 200 000 itérations restent imperceptibles à la connexion sur
# le matériel visé (poste bureautique) tout en rendant une attaque par
# dictionnaire sur le fichier volé coûteuse.
PBKDF2_ITERATIONS = 200_000
SEL_OCTETS = 16

USERNAME_MAX_LEN = 60
PASSWORD_MIN_LEN = 4


def _hacher(password: str, sel: str) -> str:
    derive = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(sel), PBKDF2_ITERATIONS,
    )
    return derive.hex()


def _cle_username(username: str) -> str:
    """Forme normalisée servant à comparer deux identifiants de connexion.

    La casse est ignorée : une utilisatrice non technique qui tape « Marie » au
    lieu de « marie » doit se connecter, pas se voir refuser — et deux comptes
    ne différant que par la casse seraient un piège, pas une fonctionnalité.
    Le username reste stocké tel qu'il a été saisi, pour l'affichage.
    """
    return (username or "").strip().casefold()


def _lire() -> dict:
    return read_store(USERS_PATH, "users")


def get_user(user_id: str) -> dict | None:
    """Compte correspondant à l'identifiant, ou None s'il est invalide/inconnu."""
    if not is_valid_id(user_id):
        return None
    with store_lock:
        for u in _lire()["users"]:
            if u.get("id") == user_id:
                return dict(u)
        return None


def get_user_by_username(username: str) -> dict | None:
    """Compte correspondant à un identifiant de connexion (casse ignorée)."""
    cle = _cle_username(username)
    if not cle:
        return None
    with store_lock:
        for u in _lire()["users"]:
            if _cle_username(u.get("username", "")) == cle:
                return dict(u)
        return None


def create_user(username: str, password: str, profile_id: str) -> dict:
    """Crée un compte rattaché à un profil existant et le persiste.

    Lève ValueError si le nom est déjà pris, si le profil est inconnu, ou si les
    valeurs fournies sont vides. Le profil est vérifié ici et pas seulement à la
    connexion : un compte orphelin ne pourrait accéder à aucun stockage, autant
    refuser tout de suite plutôt que de livrer un identifiant qui ne marche pas.
    """
    nom = (username or "").strip()
    if not nom:
        raise ValueError("Le nom d'utilisateur est obligatoire")
    if len(nom) > USERNAME_MAX_LEN:
        raise ValueError(f"Le nom d'utilisateur dépasse {USERNAME_MAX_LEN} caractères")
    if not password or len(password) < PASSWORD_MIN_LEN:
        raise ValueError(f"Le mot de passe doit faire au moins {PASSWORD_MIN_LEN} caractères")
    if get_profile(profile_id) is None:
        raise ValueError(f"Profil inconnu : {profile_id}")
    with store_lock:
        if get_user_by_username(nom) is not None:
            raise ValueError(f"Le nom d'utilisateur « {nom} » est déjà pris")
        data = _lire()
        sel = secrets.token_hex(SEL_OCTETS)
        user = {
            "id": uuid4().hex,
            "username": nom,
            "password_hash": f"{sel}${_hacher(password, sel)}",
            "profile_id": profile_id,
            "created_at": time.time(),
        }
        data["users"].append(user)
        write_store(USERS_PATH, data)
        return dict(user)


def verify_credentials(username: str, password: str) -> dict | None:
    """Renvoie le compte si le mot de passe correspond, None sinon.

    Aucune distinction n'est faite entre « compte inconnu » et « mot de passe
    faux » : l'appelant ne doit pas pouvoir énumérer les comptes existants.
    """
    user = get_user_by_username(username)
    if user is None or not password:
        return None
    stocke = user.get("password_hash") or ""
    sel, _, attendu = stocke.partition("$")
    if not sel or not attendu:
        return None
    try:
        calcule = _hacher(password, sel)
    except ValueError:
        # Sel non hexadécimal : fichier bricolé à la main, compte inutilisable.
        return None
    if not secrets.compare_digest(calcule, attendu):
        return None
    return user
