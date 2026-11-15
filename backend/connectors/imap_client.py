"""Lecteur IMAP générique (Gmail, Outlook.com, Infomaniak, etc.).

SÉCURITÉ : le mot de passe d'application est fourni par l'utilisateur via
l'UI Paramètres. Il n'est jamais loggué ni hardcodé.
"""
import email
import imaplib
import ssl
from email.header import decode_header

# Secondes d'attente maximale pour une connexion ou une réponse. Sans délai,
# imaplib attend indéfiniment un serveur qui ne répond pas et immobilise un
# fil d'exécution du serveur d'Olivia.
DELAI_IMAP = 15

# Plafond de messages renvoyés par l'aperçu : `limit=0` donnait `[-0:]`, donc
# TOUS les non lus, et un négatif presque tous.
LIMITE_MAX_MESSAGES = 50


def _ouvrir(host: str):
    """Connexion IMAP chiffrée. Isolée pour que les tests puissent la simuler.

    `IMAP4_SSL(host)` seul utilise un contexte NON vérifié (`ssl._create_stdlib_context`) :
    n'importe qui sur le réseau pourrait se faire passer pour le serveur de
    messagerie et lire le mot de passe. Le contexte par défaut vérifie le
    certificat et le nom d'hôte.
    """
    return imaplib.IMAP4_SSL(host, ssl_context=ssl.create_default_context(),
                             timeout=DELAI_IMAP)


def _borner(limit) -> int:
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        limit = 10
    return max(1, min(LIMITE_MAX_MESSAGES, limit))


def _decode(header) -> str:
    """En-tête décodé ; ne lève jamais (jeu de caractères inconnu, octets invalides)."""
    if header is None:
        return ""
    try:
        parts = decode_header(str(header))
    except Exception:
        return str(header)
    morceaux = []
    for p, c in parts:
        if not isinstance(p, bytes):
            morceaux.append(p)
            continue
        try:
            morceaux.append(p.decode(c or "utf-8", errors="replace"))
        except LookupError:
            # Jeu de caractères inconnu de Python : repli sur utf-8.
            morceaux.append(p.decode("utf-8", errors="replace"))
    return "".join(morceaux)


def unread_count(host: str, user: str, password: str, folder: str = "INBOX") -> int:
    """Nombre de messages non lus — appel léger pour les notifications UI."""
    if not (host and user and password):
        raise ValueError("IMAP : host/user/password requis dans settings.json")
    with _ouvrir(host) as imap:
        imap.login(user, password)
        imap.select(folder, readonly=True)
        typ, data = imap.search(None, "UNSEEN")
        count = len((data[0] or b"").split())
        try:
            imap.close()
        except Exception:
            pass
    return count


def read_inbox(host: str, user: str, password: str,
               folder: str = "INBOX", limit: int = 10) -> list[dict]:
    """Lit les N derniers messages non lus du dossier IMAP (N entre 1 et 50)."""
    if not (host and user and password):
        raise ValueError("IMAP : host/user/password requis dans settings.json")

    limit = _borner(limit)
    messages = []
    with _ouvrir(host) as imap:
        imap.login(user, password)
        # Lecture seule + BODY.PEEK : un simple aperçu ne doit pas marquer les
        # messages comme lus dans la vraie boîte de l'utilisatrice.
        imap.select(folder, readonly=True)
        typ, data = imap.search(None, "UNSEEN")
        ids = (data[0] or b"").split()[-limit:]
        for mid in ids:
            typ, msg_data = imap.fetch(mid, "(BODY.PEEK[])")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            messages.append({
                "id": mid.decode(),
                "from": _decode(msg.get("From")),
                "subject": _decode(msg.get("Subject")),
                "date": _decode(msg.get("Date")),
                "snippet": _extract_text(msg)[:500],
            })
        try:
            imap.close()
        except Exception:
            pass
    return messages


def _extract_text(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    try:
                        return payload.decode(errors="ignore")
                    except Exception:
                        pass
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            try:
                return payload.decode(errors="ignore")
            except Exception:
                pass
    return ""
