"""Lecteur IMAP générique (Gmail, Outlook.com, Infomaniak, etc.).

SÉCURITÉ : le mot de passe d'application est fourni par l'utilisateur via
l'UI Paramètres. Il n'est jamais loggué ni hardcodé.
"""
import imaplib
import email
from email.header import decode_header


def unread_count(host: str, user: str, password: str, folder: str = "INBOX") -> int:
    """Nombre de messages non lus — appel léger pour les notifications UI."""
    if not (host and user and password):
        raise ValueError("IMAP : host/user/password requis dans settings.json")
    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(user, password)
        imap.select(folder)
        typ, data = imap.search(None, "UNSEEN")
        count = len((data[0] or b"").split())
        try:
            imap.close()
        except Exception:
            pass
    return count


def read_inbox(host: str, user: str, password: str,
               folder: str = "INBOX", limit: int = 10) -> list[dict]:
    """Lit les N derniers messages non lus du dossier IMAP."""
    if not (host and user and password):
        raise ValueError("IMAP : host/user/password requis dans settings.json")

    messages = []
    with imaplib.IMAP4_SSL(host) as imap:
        imap.login(user, password)
        imap.select(folder)
        typ, data = imap.search(None, "UNSEEN")
        ids = (data[0] or b"").split()[-limit:]
        for mid in ids:
            typ, msg_data = imap.fetch(mid, "(RFC822)")
            if not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])

            def _decode(header):
                if header is None:
                    return ""
                parts = decode_header(header)
                return "".join(p.decode(c or "utf-8") if isinstance(p, bytes) else p
                               for p, c in parts)

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
