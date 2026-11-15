"""
Sessions de connexion dans backend/profiles/sessions.json.

Jeton opaque tiré au hasard (secrets.token_urlsafe) plutôt qu'un JWT : rien à
signer, rien à vérifier, et une session se révoque en supprimant une ligne — ce
qu'un jeton auto-porté ne permet pas. Reste dans le style « fichier JSON +
verrou » du reste du backend, sans nouvelle dépendance.

Persister sur disque (et pas seulement en mémoire) évite de déconnecter tout le
monde à chaque redémarrage du service ou rechargement du serveur de dev.

Le fichier ne contient JAMAIS le jeton en clair, seulement son empreinte SHA-256 :
quiconque lit sessions.json (poste partagé, sauvegarde) ne peut pas recopier un
jeton dans un cookie. Le jeton en clair n'existe que dans le cookie du
navigateur. Un jeton à 256 bits d'entropie n'a pas besoin de sel ni de hachage
lent. Les sessions sont reconstructibles : un fichier illisible repart de zéro
(tout le monde se reconnecte), comme tentatives.json.
"""
import hashlib
import secrets
import time

from .profiles import PROFILES_DIR, read_store, store_lock, write_store

SESSIONS_PATH = PROFILES_DIR / "sessions.json"

# 8 heures : la durée d'une journée de travail. Une session ouverte le matin
# tient jusqu'au soir sans redemander le mot de passe (l'app est un outil
# bureautique utilisé en continu), et un poste laissé allumé la nuit ne reste pas
# connecté indéfiniment.
SESSION_TTL_SECONDS = 8 * 3600

# 32 octets d'entropie : un jeton de session doit être imprédictible, c'est le
# seul secret qui circule ensuite (dans un cookie HttpOnly).
TOKEN_OCTETS = 32


def _cle(token: str) -> str:
    # Les sessions enregistrées avant ce hachage (clé = jeton en clair) ne
    # correspondent plus à aucune empreinte : elles deviennent introuvables et
    # leurs titulaires se reconnectent une fois. Acceptable, et purgées à
    # l'expiration.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _lire() -> dict:
    try:
        data = read_store(SESSIONS_PATH, "sessions", vide={})
        if isinstance(data["sessions"], dict):
            return data
    except RuntimeError:
        pass
    # Fichier vide, tronqué (clé USB arrachée, coupure) ou de structure
    # inattendue : sans cela, CHAQUE requête, connexion comprise, répondait
    # 500 jusqu'à une suppression manuelle. On repart d'un magasin vide.
    return {"sessions": {}}


def _purger(sessions: dict, maintenant: float) -> int:
    """Retire les sessions expirées du dict passé. Renvoie le nombre de retraits."""
    expires = [t for t, s in sessions.items()
               if not isinstance(s, dict) or s.get("expires_at", 0) <= maintenant]
    for t in expires:
        del sessions[t]
    return len(expires)


def create_session(user_id: str, profile_id: str,
                   ttl_seconds: int = SESSION_TTL_SECONDS) -> str:
    """Ouvre une session et renvoie son jeton (à poser dans un cookie HttpOnly)."""
    with store_lock:
        data = _lire()
        maintenant = time.time()
        _purger(data["sessions"], maintenant)
        token = secrets.token_urlsafe(TOKEN_OCTETS)
        data["sessions"][_cle(token)] = {
            "user_id": user_id,
            "profile_id": profile_id,
            "expires_at": maintenant + ttl_seconds,
        }
        write_store(SESSIONS_PATH, data)
        return token


def resolve_session(token: str) -> dict | None:
    """Session correspondant au jeton, ou None si absent/expiré.

    Profite du passage pour purger les sessions expirées, mais n'écrit sur disque
    que s'il y a effectivement eu quelque chose à retirer : cette fonction est
    appelée à chaque requête authentifiée, elle ne doit pas déclencher une
    écriture à chaque fois.
    """
    if not token:
        return None
    with store_lock:
        data = _lire()
        sessions = data["sessions"]
        if _purger(sessions, time.time()):
            write_store(SESSIONS_PATH, data)
        session = sessions.get(_cle(token))
        return dict(session) if isinstance(session, dict) else None


def delete_session(token: str) -> bool:
    """Ferme une session (déconnexion). Renvoie False si le jeton est inconnu."""
    if not token:
        return False
    with store_lock:
        data = _lire()
        if data["sessions"].pop(_cle(token), None) is None:
            return False
        write_store(SESSIONS_PATH, data)
        return True


def supprimer_sessions_du_compte(user_id: str, sauf_jeton: str | None = None) -> int:
    """Ferme toutes les sessions d'un compte, sauf éventuellement celle du jeton
    donné (la session courante, quand on change son propre mot de passe).
    Renvoie le nombre de sessions fermées.

    Appelée à chaque changement ou réinitialisation de mot de passe et à la
    suppression d'un compte : un mot de passe changé parce qu'il a fuité ne
    sert à rien si les sessions ouvertes avec l'ancien restent valables 8 h.
    """
    if not user_id:
        return 0
    garder = _cle(sauf_jeton) if sauf_jeton else None
    with store_lock:
        data = _lire()
        sessions = data["sessions"]
        a_fermer = [cle for cle, s in sessions.items()
                    if isinstance(s, dict) and s.get("user_id") == user_id and cle != garder]
        for cle in a_fermer:
            del sessions[cle]
        if a_fermer:
            write_store(SESSIONS_PATH, data)
        return len(a_fermer)
