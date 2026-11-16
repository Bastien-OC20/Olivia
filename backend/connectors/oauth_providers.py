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

# Messages d'erreur SANS le chemin du fichier : l'aperçu du calendrier est ouvert
# à tous les comptes de l'organisation, alors que le chemin est un réglage du
# responsable. Les anciens messages recopiaient le chemin, ou le texte brut de
# l'exception, qui le contient (« [Errno 13] Permission denied: 'C:\\…' ») : un
# membre y lisait l'arborescence du poste.
ICS_INTROUVABLE = ("Le fichier de l'agenda (.ics) est introuvable : vérifiez son "
                   "emplacement dans Paramètres → Connexions.")
ICS_ILLISIBLE = ("Le fichier de l'agenda n'a pas pu être lu : vérifiez qu'il s'agit "
                 "bien d'un export de calendrier (.ics).")
ICS_MODULE_ABSENT = ("La lecture des agendas n'est pas disponible sur ce poste : "
                     "prévenez le service informatique.")


def calendar_list_events(ics_path: str, limit: int = 10) -> list[dict]:
    """Lit un fichier .ics local (exporté depuis Google/Outlook/Apple Calendar)."""
    if not ics_path:
        return []
    from pathlib import Path
    p = Path(ics_path)
    if not p.exists():
        return [{"error": ICS_INTROUVABLE}]
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
        return [{"error": ICS_MODULE_ABSENT}]
    except Exception:
        # Pas de texte de l'exception : il cite le chemin (voir plus haut).
        return [{"error": ICS_ILLISIBLE}]
