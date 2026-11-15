"""
Comptes utilisateurs dans backend/profiles/users.json.

Un compte appartient à exactement UN profil (pas de compte multi-organisation)
et y tient un RÔLE (audit du 15/11/2026, lot 4) :
  - « responsable » : règle les réglages de l'organisation (dossiers,
    connecteurs, recherche, OCR, prompt, formules des documents), gère ses
    comptes et peut demander l'effacement RGPD ;
  - « membre » : utilise Olivia (conversations, documents, tableaux) et ne
    touche qu'aux réglages de confort.
Mêmes garanties d'écriture que conversations.py : verrou RLock et
atomic-write, mutualisés via profiles.py.

Migration : un compte enregistré avant les rôles n'a pas de champ `role`. Il est
lu comme « responsable » (voir `role_de`) : avant les rôles, tout compte avait
tous les droits, et en retirer d'office à des comptes existants bloquerait des
organisations entières. users.json n'est PAS réécrit pour autant : le champ
n'apparaît que lorsqu'un rôle est explicitement fixé.

Garde-fou commun à l'API et à la ligne de commande : une organisation qui a
des comptes garde toujours au moins un responsable (`OperationRefusee`). Sans
responsable, plus personne ne pourrait régler ses dossiers ni gérer ses
comptes ; et une organisation vidée de ses comptes se rejoindrait sans
confirmation par `manage_users init`.

Le mot de passe n'est jamais stocké ni journalisé en clair : seul un dérivé
PBKDF2-HMAC-SHA256 salé est conservé, sous la forme
« pbkdf2_sha256$<itérations>$<sel_hex>$<dérivé_hex> ». L'ancien format
« <sel_hex>$<dérivé_hex> » (200 000 itérations implicites) reste accepté, et un
compte qui l'utilise est remis à niveau à sa prochaine connexion réussie.
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

# Coût du dérivé : 600 000 itérations, valeur recommandée par l'OWASP pour
# PBKDF2-HMAC-SHA256 (Password Storage Cheat Sheet). Environ 0,2 s par
# vérification sur un poste récent : imperceptible à la connexion, mais une
# attaque par dictionnaire sur un users.json volé devient trois fois plus chère
# qu'avec l'ancien réglage (200 000). Le nombre d'itérations est désormais
# STOCKÉ dans chaque dérivé : le relever plus tard n'invalidera aucun compte.
PBKDF2_ITERATIONS = 600_000
ITERATIONS_ANCIEN_FORMAT = 200_000
PREFIXE_HASH = "pbkdf2_sha256"
SEL_OCTETS = 16

USERNAME_MAX_LEN = 60

ROLE_RESPONSABLE = "responsable"
ROLE_MEMBRE = "membre"
ROLES = (ROLE_RESPONSABLE, ROLE_MEMBRE)


class OperationRefusee(ValueError):
    """Opération sur un compte refusée par un garde-fou (dernier responsable…).

    Sous-classe de ValueError : la ligne de commande l'affiche comme toute
    erreur métier ; l'API la distingue pour répondre 409 au lieu de 400.
    """


def role_de(user: dict | None) -> str:
    """Rôle effectif d'un compte.

    Champ absent (compte d'avant les rôles) : « responsable », voir la docstring
    du module. Champ présent mais inconnu (users.json retouché à la main,
    faute de frappe) : « membre », le rôle le moins puissant — une valeur
    illisible ne doit jamais donner plus de droits.
    """
    if not isinstance(user, dict) or "role" not in user:
        return ROLE_RESPONSABLE
    return user["role"] if user["role"] in ROLES else ROLE_MEMBRE


def _vue(u: dict) -> dict:
    """Copie d'un compte lu sur disque, rôle effectif renseigné."""
    return dict(u, role=role_de(u))


# Politique de mot de passe : cas « mot de passe + restriction d'accès » de la
# recommandation CNIL n° 2022-100 du 21 juillet 2022 — au moins 8 caractères
# mêlant 3 des 4 types (minuscules, majuscules, chiffres, caractères spéciaux),
# ASSOCIÉ à la temporisation des échecs de connexion de tentatives.py. Ne
# s'applique qu'aux mots de passe créés ou changés : un compte existant au mot
# de passe plus faible continue de se connecter.
PASSWORD_MIN_LEN = 8
PASSWORD_MIN_CATEGORIES = 3


def probleme_mot_de_passe(password: str) -> str | None:
    """Raison pour laquelle un NOUVEAU mot de passe est refusé, ou None s'il convient."""
    if not password or len(password) < PASSWORD_MIN_LEN:
        return f"Le mot de passe doit faire au moins {PASSWORD_MIN_LEN} caractères."
    categories = sum((
        any(c.islower() for c in password),
        any(c.isupper() for c in password),
        any(c.isdigit() for c in password),
        any(not c.isalnum() for c in password),
    ))
    if categories < PASSWORD_MIN_CATEGORIES:
        return ("Le mot de passe doit mêler au moins 3 types de caractères parmi : "
                "minuscules, majuscules, chiffres, caractères spéciaux.")
    return None


def _deriver(password: str, sel: str, iterations: int) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(sel), iterations,
    ).hex()


def _nouveau_hash(password: str) -> str:
    sel = secrets.token_hex(SEL_OCTETS)
    return f"{PREFIXE_HASH}${PBKDF2_ITERATIONS}${sel}${_deriver(password, sel, PBKDF2_ITERATIONS)}"


def _decoder_hash(stocke: str) -> tuple[int, str, str] | None:
    """(itérations, sel, dérivé attendu), ou None si le format est inconnu."""
    morceaux = (stocke or "").split("$")
    if len(morceaux) == 4 and morceaux[0] == PREFIXE_HASH:
        try:
            iterations = int(morceaux[1])
        except ValueError:
            return None
        return (iterations, morceaux[2], morceaux[3]) if iterations > 0 else None
    if len(morceaux) == 2 and all(morceaux):
        return ITERATIONS_ANCIEN_FORMAT, morceaux[0], morceaux[1]
    return None


# Sel fixe servant aux vérifications « à blanc » (voir verify_credentials).
_SEL_LEURRE = "00" * SEL_OCTETS


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
                return _vue(u)
        return None


def existe_un_compte() -> bool:
    """Au moins un compte est-il provisionné sur ce poste ?

    Sert uniquement à l'écran de connexion d'une installation neuve, pour dire
    COMMENT créer le premier compte au lieu de laisser un formulaire qui ne peut
    pas aboutir (voir GET /api/auth/etat).
    """
    with store_lock:
        return bool(_lire()["users"])


def get_user_by_username(username: str) -> dict | None:
    """Compte correspondant à un identifiant de connexion (casse ignorée)."""
    cle = _cle_username(username)
    if not cle:
        return None
    with store_lock:
        for u in _lire()["users"]:
            if _cle_username(u.get("username", "")) == cle:
                return _vue(u)
        return None


def lister_comptes(profile_id: str) -> list[dict]:
    """Comptes d'une organisation (rôle effectif renseigné), par date de création."""
    with store_lock:
        trouves = [_vue(u) for u in _lire()["users"] if u.get("profile_id") == profile_id]
    trouves.sort(key=lambda u: u.get("created_at", 0))
    return trouves


def create_user(username: str, password: str, profile_id: str,
                role: str | None = None) -> dict:
    """Crée un compte rattaché à un profil existant et le persiste.

    `role` absent : « responsable » pour le PREMIER compte de l'organisation
    (quelqu'un doit pouvoir la régler), « membre » pour les suivants (le moins
    de droits possible par défaut).

    Lève ValueError si le nom est déjà pris, si le profil est inconnu, si le rôle
    est inconnu, ou si les valeurs fournies sont vides. Le profil est vérifié ici
    et pas seulement à la connexion : un compte orphelin ne pourrait accéder à
    aucun stockage, autant refuser tout de suite plutôt que de livrer un
    identifiant qui ne marche pas.
    """
    if role is not None and role not in ROLES:
        raise ValueError(f"Rôle inconnu : {role} (responsable ou membre)")
    nom = (username or "").strip()
    if not nom:
        raise ValueError("Le nom d'utilisateur est obligatoire")
    if len(nom) > USERNAME_MAX_LEN:
        raise ValueError(f"Le nom d'utilisateur dépasse {USERNAME_MAX_LEN} caractères")
    probleme = probleme_mot_de_passe(password)
    if probleme:
        raise ValueError(probleme)
    if get_profile(profile_id) is None:
        raise ValueError(f"Profil inconnu : {profile_id}")
    with store_lock:
        if get_user_by_username(nom) is not None:
            raise ValueError(f"Le nom d'utilisateur « {nom} » est déjà pris")
        data = _lire()
        if role is None:
            deja = any(u.get("profile_id") == profile_id for u in data["users"])
            role = ROLE_MEMBRE if deja else ROLE_RESPONSABLE
        user = {
            "id": uuid4().hex,
            "username": nom,
            "password_hash": _nouveau_hash(password),
            "profile_id": profile_id,
            "role": role,
            "created_at": time.time(),
        }
        data["users"].append(user)
        write_store(USERS_PATH, data)
        return dict(user)


def verify_credentials(username: str, password: str) -> dict | None:
    """Renvoie le compte si le mot de passe correspond, None sinon.

    Aucune distinction n'est faite entre « compte inconnu » et « mot de passe
    faux » : l'appelant ne doit pas pouvoir énumérer les comptes existants. Ni
    par la réponse, ni par le TEMPS de réponse : un identifiant inconnu passe
    par un dérivé « à blanc » de même coût. Sans cela, il répondait en quelques
    millisecondes contre plusieurs dizaines pour un compte existant, ce qui
    suffisait à deviner les identifiants valides.

    Un compte à l'ancien format (ou à un coût inférieur au réglage actuel) est
    remis à niveau dès que son mot de passe est vérifié : c'est le seul moment
    où le mot de passe en clair est disponible.
    """
    user = get_user_by_username(username)
    decode = _decoder_hash(user.get("password_hash", "")) if user else None
    if user is None or decode is None or not password:
        _deriver(password or "", _SEL_LEURRE, PBKDF2_ITERATIONS)
        return None
    iterations, sel, attendu = decode
    try:
        calcule = _deriver(password, sel, iterations)
    except ValueError:
        # Sel non hexadécimal : fichier bricolé à la main, compte inutilisable.
        return None
    if not secrets.compare_digest(calcule, attendu):
        return None
    if iterations < PBKDF2_ITERATIONS or not user["password_hash"].startswith(PREFIXE_HASH):
        _remettre_a_niveau(user["id"], password)
    return user


def _remettre_a_niveau(user_id: str, password: str) -> None:
    """Réécrit le dérivé d'un compte au format et au coût actuels.

    Un échec d'écriture (dossier non modifiable) n'empêche pas la connexion : le
    compte reste simplement à l'ancien format jusqu'à la prochaine fois.
    """
    with store_lock:
        try:
            data = _lire()
            for u in data["users"]:
                if u.get("id") == user_id:
                    u["password_hash"] = _nouveau_hash(password)
                    write_store(USERS_PATH, data)
                    return
        except (OSError, RuntimeError):
            return


# ---------- Gestion des comptes (lot 4c) ----------
# Fonctions communes à l'API (responsable, compte lui-même) et à la ligne de
# commande (service informatique). Elles ne ferment pas les sessions ni ne
# touchent aux tentatives : c'est à l'appelant de le faire (sessions.py,
# tentatives.py), pour garder ce module sans dépendance vers eux.

def _dernier_responsable(data: dict, u: dict) -> bool:
    """`u` est-il le seul responsable de son organisation ?"""
    if role_de(u) != ROLE_RESPONSABLE:
        return False
    return not any(v is not u and v.get("profile_id") == u.get("profile_id")
                   and role_de(v) == ROLE_RESPONSABLE for v in data["users"])


def _message_dernier_responsable(u: dict) -> str:
    return (f"« {u.get('username', '')} » est le dernier responsable de son organisation : "
            "nommez d'abord un autre responsable.")


def _trouver(data: dict, user_id: str) -> dict | None:
    if not is_valid_id(user_id):
        return None
    return next((u for u in data["users"] if u.get("id") == user_id), None)


def _ecrire_mot_de_passe(user_id: str, nouveau: str) -> bool:
    with store_lock:
        data = _lire()
        u = _trouver(data, user_id)
        if u is None:
            return False
        u["password_hash"] = _nouveau_hash(nouveau)
        write_store(USERS_PATH, data)
        return True


def changer_mot_de_passe(user_id: str, ancien: str, nouveau: str) -> bool:
    """Le compte change son propre mot de passe. False si l'ancien est faux.

    Lève ValueError si le nouveau ne respecte pas la politique CNIL, est
    identique à l'ancien, ou si le compte n'existe plus. La politique est
    vérifiée AVANT l'ancien mot de passe : une saisie refusée pour un nouveau
    mot de passe trop faible ne compte pas comme une tentative ratée.
    La temporisation des échecs est à la charge de l'appelant (tentatives.py).
    """
    probleme = probleme_mot_de_passe(nouveau)
    if probleme:
        raise ValueError(probleme)
    user = get_user(user_id)
    if user is None:
        raise ValueError("Compte introuvable.")
    verifie = verify_credentials(user["username"], ancien)
    if verifie is None or verifie.get("id") != user_id:
        return False
    if nouveau == ancien:
        raise ValueError("Le nouveau mot de passe doit être différent de l'actuel.")
    if not _ecrire_mot_de_passe(user_id, nouveau):
        raise ValueError("Compte introuvable.")
    return True


def reinitialiser_mot_de_passe(user_id: str, nouveau: str) -> bool:
    """Fixe un nouveau mot de passe SANS l'ancien (responsable, service
    informatique). False si le compte n'existe pas ; ValueError si le mot de
    passe ne respecte pas la politique."""
    probleme = probleme_mot_de_passe(nouveau)
    if probleme:
        raise ValueError(probleme)
    return _ecrire_mot_de_passe(user_id, nouveau)


def changer_role(user_id: str, role: str) -> dict | None:
    """Change le rôle d'un compte ; renvoie le compte, ou None s'il n'existe pas.

    Lève ValueError si le rôle est inconnu, OperationRefusee si le compte est le
    dernier responsable de son organisation et qu'on veut en faire un membre.
    """
    if role not in ROLES:
        raise ValueError(f"Rôle inconnu : {role} (responsable ou membre)")
    with store_lock:
        data = _lire()
        u = _trouver(data, user_id)
        if u is None:
            return None
        if role != ROLE_RESPONSABLE and _dernier_responsable(data, u):
            raise OperationRefusee(_message_dernier_responsable(u))
        if u.get("role") != role:
            u["role"] = role
            write_store(USERS_PATH, data)
        return _vue(u)


def supprimer_compte(user_id: str) -> dict | None:
    """Supprime un compte ; renvoie le compte supprimé, ou None s'il n'existait pas.

    Lève OperationRefusee s'il est le dernier responsable de son organisation.

    Ses conversations et tableaux privés NE SONT PAS supprimés : ils restent sur
    le disque, invisibles de tous les comptes (leur propriétaire n'existe plus
    et un identifiant n'est jamais réattribué), inclus dans l'export RGPD du
    responsable et purgés par l'effacement RGPD de l'organisation. Raison : un
    départ (fin de contrat, mutation) ne doit pas détruire sans retour un
    travail qui peut appartenir à l'organisation ; à l'inverse, les rendre
    visibles à d'autres trahirait leur caractère privé.
    """
    with store_lock:
        data = _lire()
        u = _trouver(data, user_id)
        if u is None:
            return None
        if _dernier_responsable(data, u):
            raise OperationRefusee(_message_dernier_responsable(u))
        data["users"] = [v for v in data["users"] if v is not u]
        write_store(USERS_PATH, data)
        return _vue(u)
