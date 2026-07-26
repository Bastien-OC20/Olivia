"""Connecteurs externes : IMAP / OAuth / Calendar / Obsidian / Notion / outils métier.

Aucun secret n'est hardcodé. Les credentials sont saisis par l'utilisateur via
l'UI Paramètres et stockés dans backend/settings.json (local uniquement).
En production, remplacer le stockage par la lib 'keyring' (coffre OS).
"""
from .imap_client import read_inbox, unread_count
from .oauth_providers import (
    gmail_list_messages,
    outlook_list_messages,
    calendar_list_events,
)
from .business_tools import ecole_directe_status, service_public_status

__all__ = [
    "read_inbox",
    "unread_count",
    "gmail_list_messages",
    "outlook_list_messages",
    "calendar_list_events",
    "ecole_directe_status",
    "service_public_status",
]
