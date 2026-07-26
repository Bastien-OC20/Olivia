"""
Prévisualisation simplifiée de fichiers pour l'UI.

Renvoie une structure uniforme selon le type :
  {kind: "text",  content}                 → texte / code
  {kind: "table", columns, rows, truncated}→ CSV / XLSX
  {kind: "doc",   paragraphs, truncated}   → DOCX
  {kind: "image", url, name}               → images (rendu via /api/fs/download)
  {kind: "pdf",   url, name}               → PDF (rendu natif navigateur)
  {kind: "unsupported", name, url}         → binaire non prévisualisable

Aucune dépendance lourde n'est importée au niveau module : docx/openpyxl sont
chargés paresseusement pour que l'app démarre même si elles manquent.
"""
from pathlib import Path

TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".vue", ".json", ".yaml",
            ".yml", ".html", ".css", ".log", ".sh", ".ini", ".cfg", ".xml"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}

MAX_ROWS = 200
MAX_CHARS = 30_000
MAX_PARAGRAPHS = 800


def preview(path: Path, download_url: str) -> dict:
    ext = path.suffix.lower()

    if ext in IMAGE_EXT:
        return {"kind": "image", "url": download_url, "name": path.name}
    if ext == ".pdf":
        return {"kind": "pdf", "url": download_url, "name": path.name}
    if ext == ".csv":
        return _preview_csv(path)
    if ext in {".xlsx", ".xlsm"}:
        return _preview_xlsx(path)
    if ext == ".docx":
        return _preview_docx(path)
    if ext in TEXT_EXT:
        try:
            content = path.read_text(errors="ignore")
        except Exception as e:
            return {"kind": "error", "detail": f"Lecture impossible : {e}"}
        truncated = len(content) > MAX_CHARS
        return {"kind": "text", "content": content[:MAX_CHARS], "truncated": truncated}

    return {"kind": "unsupported", "name": path.name, "url": download_url}


def _preview_csv(path: Path) -> dict:
    import csv
    rows = []
    truncated = False
    try:
        with open(path, newline="", encoding="utf-8", errors="ignore") as f:
            for i, row in enumerate(csv.reader(f)):
                if i >= MAX_ROWS + 1:
                    truncated = True
                    break
                rows.append([("" if c is None else str(c)) for c in row])
    except Exception as e:
        return {"kind": "error", "detail": f"Erreur CSV : {e}"}
    columns = rows[0] if rows else []
    return {"kind": "table", "columns": columns, "rows": rows[1:], "truncated": truncated}


def _preview_xlsx(path: Path) -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {"kind": "error", "detail": "Module 'openpyxl' non installé (pip install openpyxl)."}
    try:
        wb = load_workbook(path, read_only=True, data_only=True)
        ws = wb.active
        rows = []
        truncated = False
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_ROWS + 1:
                truncated = True
                break
            rows.append([("" if c is None else str(c)) for c in row])
        wb.close()
    except Exception as e:
        return {"kind": "error", "detail": f"Erreur XLSX : {e}"}
    columns = rows[0] if rows else []
    return {"kind": "table", "columns": columns, "rows": rows[1:],
            "sheet": getattr(ws, "title", ""), "truncated": truncated}


def _preview_docx(path: Path) -> dict:
    try:
        import docx  # python-docx
    except ImportError:
        return {"kind": "error",
                "detail": "Module 'python-docx' non installé (pip install python-docx)."}
    try:
        d = docx.Document(str(path))
        paras = [p.text for p in d.paragraphs if p.text.strip()]
    except Exception as e:
        return {"kind": "error", "detail": f"Erreur DOCX : {e}"}
    truncated = len(paras) > MAX_PARAGRAPHS
    return {"kind": "doc", "paragraphs": paras[:MAX_PARAGRAPHS], "truncated": truncated}
