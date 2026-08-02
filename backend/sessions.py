"""
Sessions de connexion dans backend/profiles/sessions.json.

Jeton opaque tiré au hasard (secrets.token_urlsafe) plutôt qu'un JWT : rien à
signer, rien à vérifier, et une session se révoque en supprimant une ligne — ce
qu'un jeton auto-porté ne permet pas. Reste dans le style « fichier JSON +
verrou » du reste du backend, sans nouvelle dépendance.

Persister sur disque (et pas seulement en mémoire) évite de déconnecter tout le
monde à chaque redémarrage du service ou rechargement du serveur de dev.
"""
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


def _lire() -> dict:
    return read_store(SESSIONS_PATH, "sessions", vide={})


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
        data["sessions"][token] = {
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
        session = sessions.get(token)
        return dict(session) if isinstance(session, dict) else None


def delete_session(token: str) -> bool:
    """Ferme une session (déconnexion). Renvoie False si le jeton est inconnu."""
    if not token:
        return False
    with store_lock:
        data = _lire()
        if data["sessions"].pop(token, None) is None:
            return False
        write_store(SESSIONS_PATH, data)
        return True
