"""Lecture d'un calendrier au format .ics (export Google / Outlook / Apple).

Ce module contenait aussi des squelettes OAuth Gmail et Outlook, retirés car non
fonctionnels. Pour le courrier, le connecteur IMAP (imap_client.py) fonctionne
réellement et suffit à la plupart des messageries, y compris académiques.

Pour les fichiers Google Drive / OneDrive, l'OAuth est inutile : les deux services
se synchronisent dans un dossier local qu'il suffit de désigner comme dossier de
travail (Documents → Parcourir). Aucune autorisation à demander, et cela évite la
validation Google (jetons expirant tous les 7 jours hors app vérifiée) comme le
consentement administrateur d'un tenant Microsoft.
"""


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
