"""Connecteurs externes : IMAP / Calendar / Obsidian / Notion.

Aucun secret n'est hardcodé. Les credentials sont saisis par l'utilisateur via
l'UI Paramètres et stockés dans backend/settings.json (local uniquement).
En production, remplacer le stockage par la lib 'keyring' (coffre OS).

Seuls les connecteurs réellement fonctionnels sont exposés. Les squelettes
(OAuth Gmail/Outlook, École Directe, Service-Public) ont été retirés : visibles
dans les réglages, ils laissaient croire à des fonctionnalités disponibles.
Alternatives retenues, documentées dans le README — IMAP pour le courrier,
dossier synchronisé localement pour Google Drive et OneDrive.
"""
from .imap_client import read_inbox, unread_count
from .oauth_providers import calendar_list_events

__all__ = [
    "read_inbox",
    "unread_count",
    "calendar_list_events",
]
