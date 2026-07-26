"""
FastAPI backend pour Olivia (assistante locale).

Routes principales :
  GET  /api/health                       : diagnostic de service
  GET  /api/models                       : liste des modèles Ollama installés
  GET  /api/settings                     : retourne settings.json (secrets masqués)
  PUT  /api/settings                     : patch partiel des paramètres
  POST /api/chat/stream                  : appel Ollama SSE (token par token)
  POST /api/chat                         : appel Ollama non-stream
  GET  /api/fs/list                      : liste un dossier (sandboxé)
  GET  /api/fs/read                      : lit un fichier texte (sandboxé, filtré)
  GET  /api/fs/search                    : recherche regex dans un dossier
  GET  /api/fs/preview                   : prévisualisation (txt/csv/xlsx/docx/img/pdf)
  POST /api/fs/upload                    : upload d'un fichier (sandboxé, filtré)
  GET  /api/fs/download                  : téléchargement d'un fichier (sandboxé)
  POST /api/search                       : recherche web via provider configuré
  GET  /api/connectors/status            : état stylisable de tous les connecteurs
  GET  /api/connectors/mail/unread       : nombre d'e-mails non lus (notifications)
  GET  /api/connectors/imap/preview      : aperçu boîte mail
  GET  /api/connectors/calendar/preview  : aperçu calendrier .ics
  GET  /api/privacy/export               : RGPD — export de toutes les données locales
  POST /api/privacy/delete               : RGPD — suppression des données locales
  /ui                                    : interface Vue buildée (frontend/dist)
"""
import os
import re
import sys
import shutil
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query, UploadFile, File, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    StreamingResponse, JSONResponse, FileResponse, RedirectResponse, PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from .settings import settings, style_directives
from .search import web_search
from . import documents
from .connectors import (
    read_inbox,
    unread_count,
    gmail_list_messages,
    outlook_list_messages,
    calendar_list_events,
    ecole_directe_status,
    service_public_status,
)

# ---------- Configuration runtime ----------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
FS_ROOT = Path(os.getenv("FS_ROOT", os.path.expanduser("~/Documents"))).resolve()
UPLOAD_SUBDIR = "_uploads"                       # RGPD : zone de données créée par l'app
MAX_FILE_SIZE = 1_000_000                         # 1 Mo pour la lecture texte
MAX_UPLOAD_SIZE = 25 * 1024 * 1024                # 25 Mo pour l'upload
API_TOKEN = os.getenv("API_TOKEN", "")           # sécurité optionnelle (jeton local)

ALLOWED_EXT = {".txt", ".md", ".py", ".js", ".ts", ".vue", ".json",
               ".yaml", ".yml", ".csv", ".html", ".css", ".log", ".sh"}
# Extensions acceptées à l'upload / preview (plus large que la lecture texte brute)
UPLOAD_EXT = ALLOWED_EXT | {".docx", ".xlsx", ".xlsm", ".pdf",
                            ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}

# Origines CORS autorisées : uniquement le poste local (dev Vite + prod servie).
ALLOWED_ORIGINS = [
    "http://localhost:5173", "http://127.0.0.1:5173",
    "http://localhost:8000", "http://127.0.0.1:8000",
]


def _bundle_base() -> Path:
    """Racine des ressources — gère le mode 'gelé' PyInstaller (_MEIPASS)."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return Path(__file__).resolve().parent.parent


FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(_bundle_base() / "frontend" / "dist")))

app = FastAPI(title="Olivia — assistante locale", version="3.0.0")


# ---------- Middleware sécurité ----------
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        # SAMEORIGIN (pas DENY) : autorise l'aperçu PDF via <iframe> same-origin
        # tout en bloquant l'embarquement par un site tiers.
        resp.headers["X-Frame-Options"] = "SAMEORIGIN"
        resp.headers["Referrer-Policy"] = "no-referrer"
        resp.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data: blob:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'; "
            "connect-src 'self'; frame-ancestors 'self'; base-uri 'self'; "
            "object-src 'self'; form-action 'self'"
        )
        return resp


class ApiTokenMiddleware(BaseHTTPMiddleware):
    """Si API_TOKEN est défini dans l'environnement, exige X-API-Token sur /api/*."""
    async def dispatch(self, request: Request, call_next):
        if API_TOKEN and request.url.path.startswith("/api/") \
                and request.url.path != "/api/health":
            if request.headers.get("X-API-Token") != API_TOKEN:
                return JSONResponse({"detail": "Jeton API invalide ou manquant"}, status_code=401)
        return await call_next(request)


app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ApiTokenMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# ---------- Schemas ----------
class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    temperature: Optional[float] = None
    stream: Optional[bool] = True


# ---------- Sécurité : anti path-traversal ----------
def safe_path(rel_or_abs: str) -> Path:
    p = Path(rel_or_abs)
    p = p.resolve() if p.is_absolute() else (FS_ROOT / rel_or_abs).resolve()
    try:
        p.relative_to(FS_ROOT)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : '{rel_or_abs}' sort du périmètre autorisé ({FS_ROOT})",
        )
    return p


def _mask_secrets(data: dict) -> dict:
    """Masque les secrets dans la réponse GET /api/settings (défense en profondeur).
    L'UI n'a pas besoin de relire les mots de passe ; elle ne réécrit que ce qui change.
    """
    import copy
    d = copy.deepcopy(data)
    secret_keys = {"password", "api_token", "client_secret_path"}
    for conn in d.get("connectors", {}).values():
        if isinstance(conn, dict):
            for k in list(conn.keys()):
                if k in secret_keys and conn[k]:
                    conn[k] = "••••••••"
    return d


# ---------- Routes Ollama ----------
@app.get("/api/models")
async def list_models():
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
            return {"models": [
                {"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2)}
                for m in data.get("models", [])
            ]}
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Ollama injoignable : {e}")


def _build_options(temperature: float | None) -> dict:
    s = settings.get()
    eff_temp = s.get("temperature", 0.7) if temperature is None else temperature
    options = {"temperature": eff_temp}
    # CPU/GPU : num_gpu=0 force le calcul CPU ; sinon Ollama utilise le GPU auto.
    if s.get("compute_device") == "cpu":
        options["num_gpu"] = 0
    return options


def _inject_system_prompt(messages: list[ChatMessage]) -> list[dict]:
    s = settings.get()
    directive = style_directives(s.get("reasoning_style", "balanced"), s.get("tone", "neutral"))
    custom = s.get("system_prompt", "").strip()
    combined = (custom + " " + directive).strip() or "Tu es un assistant IA local."
    out = [{"role": "system", "content": combined}]
    out.extend(m.dict() for m in messages)
    return out


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    body = {
        "model": req.model,
        "messages": _inject_system_prompt(req.messages),
        "stream": True,
        "options": _build_options(req.temperature),
    }

    async def event_generator():
        try:
            async with httpx.AsyncClient(timeout=None) as client:
                async with client.stream("POST", f"{OLLAMA_URL}/api/chat", json=body) as resp:
                    async for line in resp.aiter_lines():
                        if line:
                            yield f"data: {line}\n\n"
        except httpx.HTTPError as e:
            yield f'data: {{"error": "Ollama error: {str(e)}"}}\n\n'
        except Exception as e:
            yield f'data: {{"error": "{str(e)}"}}\n\n'

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/api/chat")
async def chat_blocking(req: ChatRequest):
    body = {
        "model": req.model,
        "messages": _inject_system_prompt(req.messages),
        "stream": False,
        "options": _build_options(req.temperature),
    }
    async with httpx.AsyncClient(timeout=120) as client:
        try:
            r = await client.post(f"{OLLAMA_URL}/api/chat", json=body)
            r.raise_for_status()
            return r.json()
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Ollama erreur : {e}")


# ---------- Routes Filesystem sandboxées ----------
@app.get("/api/fs/list")
async def fs_list(path: str = Query("", description="Chemin relatif sous FS_ROOT")):
    p = safe_path(path)
    if not p.exists():
        raise HTTPException(404, f"Dossier introuvable : {p}")
    if not p.is_dir():
        raise HTTPException(400, f"Pas un dossier : {p}")
    items = []
    for entry in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": str(entry.relative_to(FS_ROOT)),
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
                "modified": stat.st_mtime,
                "ext": entry.suffix.lower(),
            })
        except PermissionError:
            continue
    return {"root": str(FS_ROOT), "current": str(p.relative_to(FS_ROOT)), "items": items}


@app.get("/api/fs/read")
async def fs_read(path: str = Query(...)):
    p = safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    if p.suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(400, f"Extension non autorisée : {p.suffix}")
    if p.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"Fichier trop volumineux (>{MAX_FILE_SIZE} octets)")
    try:
        return {"path": str(p.relative_to(FS_ROOT)), "content": p.read_text(errors="ignore")}
    except Exception as e:
        raise HTTPException(500, f"Erreur lecture : {e}")


@app.get("/api/fs/preview")
async def fs_preview(path: str = Query(...)):
    p = safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    rel = str(p.relative_to(FS_ROOT))
    download_url = f"/api/fs/download?path={rel}"
    result = documents.preview(p, download_url)
    result["path"] = rel
    result["name"] = p.name
    return result


@app.get("/api/fs/download")
async def fs_download(path: str = Query(...)):
    p = safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    return FileResponse(str(p), filename=p.name)


@app.post("/api/fs/upload")
async def fs_upload(file: UploadFile = File(...), path: str = Query("")):
    # Nom de fichier assaini : on ne garde que le basename.
    safe_name = Path(file.filename or "fichier").name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(400, "Nom de fichier invalide")
    ext = Path(safe_name).suffix.lower()
    if ext not in UPLOAD_EXT:
        raise HTTPException(400, f"Type de fichier non autorisé : {ext or 'inconnu'}")

    target_dir = safe_path(path) if path else (FS_ROOT / UPLOAD_SUBDIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    safe_path(str(target_dir))  # revérifie le sandbox
    dest = target_dir / safe_name

    size = 0
    try:
        with open(dest, "wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    out.close()
                    dest.unlink(missing_ok=True)
                    raise HTTPException(
                        413,
                        f"Fichier trop volumineux (> {MAX_UPLOAD_SIZE // (1024 * 1024)} Mo)",
                    )
                out.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Erreur d'upload : {e}")
    return {"path": str(dest.relative_to(FS_ROOT)), "name": safe_name, "size": size}


@app.get("/api/fs/search")
async def fs_search(q: str = Query(..., min_length=1), path: str = Query("")):
    p = safe_path(path)
    if not p.is_dir():
        raise HTTPException(400, "Le chemin doit être un dossier")
    results = []
    try:
        pattern = re.compile(q, re.IGNORECASE)
    except re.error:
        raise HTTPException(400, "Motif regex invalide")
    for fp in p.rglob("*"):
        if not fp.is_file() or fp.suffix.lower() not in ALLOWED_EXT:
            continue
        if fp.stat().st_size > MAX_FILE_SIZE:
            continue
        try:
            text = fp.read_text(errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line):
                results.append({
                    "file": str(fp.relative_to(FS_ROOT)),
                    "line": i,
                    "snippet": line.strip()[:200],
                })
                if len(results) >= 200:
                    return {"query": q, "results": results, "truncated": True}
    return {"query": q, "results": results, "truncated": False}


# ---------- Routes Settings ----------
@app.get("/api/settings")
async def get_settings():
    return JSONResponse(_mask_secrets(settings.get()))


@app.put("/api/settings")
async def update_settings(patch: dict):
    if not isinstance(patch, dict):
        raise HTTPException(400, "Body doit être un objet JSON")
    # On ignore les secrets masqués renvoyés tels quels par l'UI (valeur sentinelle).
    _strip_masked(patch)
    settings.update(patch)
    return JSONResponse(_mask_secrets(settings.get()))


def _strip_masked(patch: dict):
    for conn in patch.get("connectors", {}).values():
        if isinstance(conn, dict):
            for k in list(conn.keys()):
                if conn[k] == "••••••••":
                    del conn[k]


# ---------- Route Recherche web ----------
@app.post("/api/search")
async def do_search(body: dict):
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query manquante")
    s = settings.get()
    provider = s.get("search_provider", "duckduckgo")
    try:
        results = await web_search(
            provider, query,
            searxng_url=s.get("searxng_url", "http://localhost:8888"),
            limit=body.get("limit", 5),
        )
        return {"provider": provider, "query": query, "results": results}
    except Exception as e:
        raise HTTPException(502, f"Erreur recherche via {provider} : {e}")


# ---------- Routes Connecteurs ----------
@app.get("/api/connectors/status")
async def connectors_status():
    """État synthétique et stylisable de tous les connecteurs (pour la barre UI)."""
    c = settings.get().get("connectors", {})

    def mail(cfg):
        return {
            "id": "imap", "label": cfg.get("label", "Boîte pro"), "icon": "📬",
            "enabled": bool(cfg.get("enabled")),
            "status": "connected" if cfg.get("enabled") and cfg.get("host") and cfg.get("user")
                      else ("misconfigured" if cfg.get("enabled") else "idle"),
        }

    def simple(id_, label, icon, cfg, key_ok):
        return {
            "id": id_, "label": label, "icon": icon,
            "enabled": bool(cfg.get("enabled")),
            "status": "connected" if cfg.get("enabled") and key_ok(cfg)
                      else ("misconfigured" if cfg.get("enabled") else "idle"),
        }

    out = [
        mail(c.get("imap", {})),
        simple("calendar_ics", "Calendrier", "📅", c.get("calendar_ics", {}),
               lambda x: bool(x.get("path"))),
        simple("gmail_oauth", "Gmail OAuth", "🔐", c.get("gmail_oauth", {}),
               lambda x: bool(x.get("client_id"))),
        simple("outlook_oauth", "Outlook OAuth", "🔐", c.get("outlook_oauth", {}),
               lambda x: bool(x.get("client_id"))),
        simple("obsidian", "Obsidian", "📝", c.get("obsidian", {}),
               lambda x: bool(x.get("vault_path"))),
        simple("notion", "Notion", "🔗", c.get("notion", {}),
               lambda x: bool(x.get("api_token"))),
        ecole_directe_status(c.get("ecole_directe", {})) | {"icon": "🎓"},
        service_public_status(c.get("service_public", {})) | {"icon": "🏛️"},
    ]
    return {"connectors": out}


@app.get("/api/connectors/mail/unread")
async def connectors_mail_unread():
    cfg = settings.get().get("connectors", {}).get("imap", {})
    if not cfg.get("enabled"):
        return {"enabled": False, "count": 0}
    try:
        count = unread_count(cfg.get("host", ""), cfg.get("user", ""),
                             cfg.get("password", ""), cfg.get("folder", "INBOX"))
        return {"enabled": True, "count": count, "label": cfg.get("label", "Boîte pro")}
    except Exception as e:
        return {"enabled": True, "count": 0, "error": str(e)}


@app.get("/api/connectors/imap/preview")
async def connectors_imap(limit: int = 10):
    cfg = settings.get().get("connectors", {}).get("imap", {})
    if not cfg.get("enabled"):
        return {"enabled": False, "messages": []}
    try:
        msgs = read_inbox(cfg.get("host", ""), cfg.get("user", ""),
                          cfg.get("password", ""), cfg.get("folder", "INBOX"), limit=limit)
        return {"enabled": True, "messages": msgs}
    except Exception as e:
        raise HTTPException(502, f"Erreur IMAP : {e}")


@app.get("/api/connectors/oauth/{provider}/preview")
async def connectors_oauth(provider: str, access_token: str = ""):
    if provider == "gmail":
        return {"provider": "gmail", "messages": gmail_list_messages(access_token)}
    if provider == "outlook":
        return {"provider": "outlook", "messages": outlook_list_messages(access_token)}
    raise HTTPException(400, f"Provider OAuth inconnu : {provider}")


@app.get("/api/connectors/calendar/preview")
async def connectors_calendar():
    cfg = settings.get().get("connectors", {}).get("calendar_ics", {})
    if not cfg.get("enabled") or not cfg.get("path"):
        return {"enabled": False, "events": []}
    return {"enabled": True, "events": calendar_list_events(cfg.get("path", ""), limit=20)}


# ---------- RGPD ----------
@app.get("/api/privacy/export")
async def privacy_export():
    """Droit d'accès/portabilité : export de toutes les données locales de l'app."""
    payload = {
        "settings": settings.get(),
        "note": "Toutes vos données restent sur cette machine. Aucun envoi externe.",
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="mes-donnees-local-ai.json"'},
    )


@app.post("/api/privacy/delete")
async def privacy_delete():
    """Droit à l'effacement : réinitialise les paramètres + purge la zone d'upload de l'app."""
    removed = 0
    upload_dir = FS_ROOT / UPLOAD_SUBDIR
    if upload_dir.exists():
        for f in upload_dir.glob("*"):
            try:
                if f.is_file():
                    f.unlink()
                    removed += 1
                elif f.is_dir():
                    shutil.rmtree(f)
            except Exception:
                pass
    settings.reset()
    return {"ok": True, "settings_reset": True, "uploads_removed": removed}


# ---------- Health ----------
@app.get("/api/health")
async def health():
    s = settings.get()
    return {
        "status": "ok",
        "version": app.version,
        "ollama": OLLAMA_URL,
        "fs_root": str(FS_ROOT),
        "compute_device": s.get("compute_device", "gpu"),
        "frontend_ui": FRONTEND_DIST.exists(),
        "api_token_required": bool(API_TOKEN),
        "active_connectors": [k for k, v in s.get("connectors", {}).items()
                              if isinstance(v, dict) and v.get("enabled")],
    }


# ---------- Service de l'interface Vue buildée ----------
@app.get("/")
async def root():
    if FRONTEND_DIST.exists():
        return RedirectResponse("/ui/")
    return RedirectResponse("/docs")


if FRONTEND_DIST.exists():
    app.mount("/ui", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="ui")
else:
    @app.get("/ui")
    async def ui_missing():
        return PlainTextResponse(
            "Interface non buildée. Lancez : cd frontend && npm install && npm run build\n"
            "(ou 'python launch.py' en mode dev pour utiliser Vite).",
            status_code=404,
        )


if __name__ == "__main__":
    # À lancer depuis la RACINE du projet : python -m backend.main
    import uvicorn
    uvicorn.run("backend.main:app", host="127.0.0.1", port=8000, reload=True)
