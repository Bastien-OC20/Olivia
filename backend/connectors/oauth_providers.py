"""Stubs OAuth Gmail / Outlook + Calendar ICS.

Pour activer Gmail OAuth :
  1. Console Google Cloud → créer une app OAuth → télécharger client_secret.json
  2. pip install google-auth google-auth-oauthlib google-api-python-client
  3. flow = InstalledAppFlow.from_client_secrets_file(...)
     creds = flow.run_local_server(port=0)
  4. Fournir creds.token à gmail_list_messages()

Pour Outlook OAuth :
  1. Microsoft Entra (Azure AD) → inscrire une app
  2. pip install msal requests
  3. MSAL device flow → obtenir access_token
  4. Fournir à outlook_list_messages()
"""
from typing import Optional


def gmail_list_messages(access_token: Optional[str], max_results: int = 10) -> list[dict]:
    if not access_token:
        return [{
            "warning": "OAuth Gmail non activé. "
                       "Voir backend/connectors/oauth_providers.py pour la procédure."
        }]
    return [{"info": "OAuth Gmail actif — branchement fonctionnel à implémenter côté utilisateur."}]


def outlook_list_messages(access_token: Optional[str], max_results: int = 10) -> list[dict]:
    if not access_token:
        return [{
            "warning": "OAuth Outlook non activé. "
                       "Voir backend/connectors/oauth_providers.py pour la procédure."
        }]
    return [{"info": "OAuth Outlook actif — branchement fonctionnel "
                     "à implémenter côté utilisateur."}]


def calendar_list_events(ics_path: str, limit: int = 10) -> list[dict]:
    """Lit un fichier .ics local (exporté depuis Google/Outlook/Apple Calendar)."""
    if not ics_path:
        return []
    from pathlib import Path
    p = Path(ics_path)
    if not p.exists():
        return [{"error": f"Fichier .ics introuvable : {ics_path}"}]
    try:
        from ics import Calendar
        with open(ics_path) as f:
            cal = Calendar(f.read())
        return [{
            "name": e.name,
            "begin": str(e.begin) if e.begin else "",
            "end": str(e.end) if e.end else "",
            "location": str(e.location or ""),
            "description": (e.description or "")[:200],
        } for e in list(cal.events)[:limit]]
    except ImportError:
        return [{"error": "Module 'ics' non installé. pip install ics"}]
    except Exception as e:
        return [{"error": f"Erreur parsing .ics : {e}"}]
