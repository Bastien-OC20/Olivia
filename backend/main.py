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
  GET  /api/fs/drives                    : lecteurs disponibles (hors sandbox, dossiers only)
  GET  /api/fs/browse                    : sous-dossiers d'un chemin absolu (hors sandbox)
  POST /api/search                       : recherche web via provider configuré
  GET  /api/connectors/status            : état stylisable de tous les connecteurs
  GET  /api/connectors/mail/unread       : nombre d'e-mails non lus (notifications)
  GET  /api/connectors/imap/preview      : aperçu boîte mail
  GET  /api/connectors/calendar/preview  : aperçu calendrier .ics
  GET  /api/privacy/export               : RGPD — export de toutes les données locales
  POST /api/privacy/delete               : RGPD — suppression des données locales
  GET  /api/conversations                : liste des conversations (métadonnées)
  GET  /api/conversations/{conv_id}      : conversation complète
  POST /api/conversations                : crée une conversation
  PUT  /api/conversations/{conv_id}      : met à jour une conversation
  DELETE /api/conversations/{conv_id}    : supprime une conversation
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
from . import conversations
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
# Valeur par défaut (variable d'env ou ~/Documents) — utilisée si aucun dossier valide
# n'est configuré dans les paramètres, ou si le dossier configuré n'existe plus.
FS_ROOT_DEFAULT = Path(os.getenv("FS_ROOT", os.path.expanduser("~/Documents"))).resolve()
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
def get_fs_root_entries() -> list[tuple[Path, str]]:
    """Racines FS effectives avec leur libellé éventuel : liste de tuples
    (chemin résolu, label) issus des dossiers configurés dans les paramètres,
    filtrée aux entrées non vides, valides (dossier existant), résolues et
    dédupliquées par chemin (ordre préservé, on garde la première occurrence
    et son label).

    Chaque entrée de `fs_roots` peut être une chaîne (chemin seul, compat
    héritée) ou un objet `{"path": str, "label": str}` (label facultatif).

    Compat héritée : si la liste résultante est vide et que l'ancienne clé str
    `fs_root` (potentiellement présente dans un settings.json existant) est non
    vide et valide, elle est utilisée. Sinon repli sur FS_ROOT_DEFAULT
    (env FS_ROOT / ~/Documents). Ne renvoie jamais une liste vide.

    Lue à chaque appel : un changement de réglage s'applique donc sans redémarrage.
    """
    s = settings.get()
    configured = s.get("fs_roots")
    entries: list[tuple[Path, str]] = []
    seen: set[Path] = set()
    if isinstance(configured, list):
        for entry in configured:
            raw_path = ""
            label = ""
            if isinstance(entry, str):
                raw_path = entry.strip()
            elif isinstance(entry, dict):
                raw_path = str(entry.get("path") or "").strip()
                label = str(entry.get("label") or "").strip()
            if not raw_path:
                continue
            try:
                p = Path(raw_path)
                if p.is_dir():
                    rp = p.resolve()
                    if rp not in seen:
                        seen.add(rp)
                        entries.append((rp, label))
            except OSError:
                continue
    if entries:
        return entries
    # Compat héritée : ancienne clé str unique `fs_root`.
    legacy = (s.get("fs_root") or "").strip()
    if legacy:
        try:
            p = Path(legacy)
            if p.is_dir():
                return [(p.resolve(), "")]
        except OSError:
            pass
    return [(FS_ROOT_DEFAULT, "")]


def get_fs_roots() -> list[Path]:
    """Racines FS effectives (chemins seuls) — dérivé de get_fs_root_entries()."""
    return [p for p, _ in get_fs_root_entries()]


_R_PREFIX_RE = re.compile(r"^r(\d+)$")


def safe_path(virtual: str) -> tuple[Path, Path, str]:
    """Résout un chemin virtuel `rN/...` vers (chemin_absolu, racine, préfixe 'rN').

    Refuse les chemins absolus (403), les préfixes `rN` inconnus (404), et toute
    tentative de sortie de la racine désignée par traversal (403).
    """
    raw = (virtual or "").strip().replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : chemin absolu interdit ('{virtual}')",
        )
    first, _, rest = raw.partition("/")
    m = _R_PREFIX_RE.match(first)
    roots = get_fs_roots()
    if not m or not (0 <= int(m.group(1)) < len(roots)):
        raise HTTPException(404, "Dossier inconnu")
    idx = int(m.group(1))
    root = roots[idx]
    prefix = f"r{idx}"
    p = (root / rest).resolve() if rest else root
    try:
        p.relative_to(root)
    except ValueError:
        raise HTTPException(
            status_code=403,
            detail=f"Accès refusé : '{virtual}' sort du périmètre autorisé ({root})",
        )
    return p, root, prefix


def _virtual_path(p: Path, root: Path, prefix: str) -> str:
    """Reconstruit le chemin virtuel `rN/...` correspondant à un chemin absolu."""
    rel = p.relative_to(root)
    return prefix if str(rel) == "." else f"{prefix}/{rel.as_posix()}"


def _list_dir_items(p: Path, root: Path, prefix: str) -> list[dict]:
    items = []
    for entry in sorted(p.iterdir(), key=lambda x: (x.is_file(), x.name.lower())):
        try:
            stat = entry.stat()
            items.append({
                "name": entry.name,
                "path": _virtual_path(entry, root, prefix),
                "is_dir": entry.is_dir(),
                "size": stat.st_size if entry.is_file() else 0,
                "modified": stat.st_mtime,
                "ext": entry.suffix.lower(),
            })
        except PermissionError:
            continue
    return items


# Secrets stockés à la racine des paramètres (hors bloc `connectors`) : masqués
# comme les autres à la lecture, et ignorés au PUT s'ils reviennent masqués.
TOP_LEVEL_SECRET_KEYS = {"search_brave_api_key"}


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
    # Secrets hors bloc connecteurs (clé d'API du moteur de recherche).
    for k in TOP_LEVEL_SECRET_KEYS:
        if d.get(k):
            d[k] = "••••••••"
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
async def fs_list(path: str = Query("", description="Chemin virtuel rN/... (vide = racine)")):
    raw = (path or "").strip()
    entries = get_fs_root_entries()

    if raw == "":
        if len(entries) == 1:
            root, label = entries[0]
            if not root.exists() or not root.is_dir():
                raise HTTPException(404, f"Dossier introuvable : {root}")
            return {
                "root": str(root), "current": "", "items": _list_dir_items(root, root, "r0"),
                "root_label": label or root.name,
            }
        # Plusieurs racines : on les présente comme des dossiers de premier niveau.
        display_names = [label or r.name for r, label in entries]
        items = []
        for i, (r, label) in enumerate(entries):
            name = display_names[i]
            if display_names.count(name) > 1:
                name = f"{name} — {r.parent}"
            try:
                mtime = r.stat().st_mtime
            except OSError:
                mtime = 0
            items.append({
                "name": name, "path": f"r{i}", "is_dir": True,
                "size": 0, "modified": mtime, "ext": "",
            })
        return {
            "root": "Plusieurs dossiers", "current": "", "items": items,
            "root_label": "Plusieurs dossiers",
        }

    p, root, prefix = safe_path(raw)
    if not p.exists():
        raise HTTPException(404, f"Dossier introuvable : {p}")
    if not p.is_dir():
        raise HTTPException(400, f"Pas un dossier : {p}")
    idx = int(_R_PREFIX_RE.match(prefix).group(1))
    root_label = entries[idx][1] or root.name
    return {
        "root": str(root), "current": raw, "items": _list_dir_items(p, root, prefix),
        "root_label": root_label,
    }


@app.get("/api/fs/read")
async def fs_read(path: str = Query(...)):
    p, root, prefix = safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    if p.suffix.lower() not in ALLOWED_EXT:
        raise HTTPException(400, f"Extension non autorisée : {p.suffix}")
    if p.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(413, f"Fichier trop volumineux (>{MAX_FILE_SIZE} octets)")
    try:
        return {"path": _virtual_path(p, root, prefix), "content": p.read_text(errors="ignore")}
    except Exception as e:
        raise HTTPException(500, f"Erreur lecture : {e}")


@app.get("/api/fs/preview")
async def fs_preview(path: str = Query(...)):
    p, root, prefix = safe_path(path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    rel = _virtual_path(p, root, prefix)
    download_url = f"/api/fs/download?path={rel}"
    result = documents.preview(p, download_url)
    result["path"] = rel
    result["name"] = p.name
    return result


@app.get("/api/fs/download")
async def fs_download(path: str = Query(...)):
    p, _root, _prefix = safe_path(path)
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

    raw = (path or "").strip()
    if raw == "":
        root = get_fs_roots()[0]
        prefix = "r0"
        target_dir = root / UPLOAD_SUBDIR
    else:
        target_dir, root, prefix = safe_path(raw)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_dir = target_dir.resolve()
    try:
        target_dir.relative_to(root)  # revérifie le sandbox après création
    except ValueError:
        raise HTTPException(403, "Accès refusé : cible hors du périmètre autorisé")
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
    return {"path": _virtual_path(dest, root, prefix), "name": safe_name, "size": size}


@app.get("/api/fs/search")
async def fs_search(q: str = Query(..., min_length=1), path: str = Query("")):
    try:
        pattern = re.compile(q, re.IGNORECASE)
    except re.error:
        raise HTTPException(400, "Motif regex invalide")

    raw = (path or "").strip()
    if raw == "":
        targets = [(r, r, f"r{i}") for i, r in enumerate(get_fs_roots())]
    else:
        p, root, prefix = safe_path(raw)
        if not p.is_dir():
            raise HTTPException(400, "Le chemin doit être un dossier")
        targets = [(p, root, prefix)]

    results = []
    truncated = False
    for search_dir, root, prefix in targets:
        if truncated:
            break
        for fp in search_dir.rglob("*"):
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
                        "file": _virtual_path(fp, root, prefix),
                        "line": i,
                        "snippet": line.strip()[:200],
                    })
                    if len(results) >= 200:
                        truncated = True
                        break
            if truncated:
                break
    return {"query": q, "results": results, "truncated": truncated}


# ---------- Routes Filesystem hors sandbox : sélection d'un dossier ----------
# Ces deux routes sortent volontairement du périmètre imposé par safe_path().
# Raison : pour ajouter un nouveau dossier à `fs_roots` depuis l'interface (au lieu
# de taper un chemin à la main), il faut bien pouvoir parcourir le disque *avant*
# qu'un dossier ne devienne une racine autorisée — safe_path() ne peut donc pas
# s'appliquer ici, par construction. Une fois choisi, le dossier est validé et
# enregistré via PUT /api/settings (qui vérifie qu'il existe) ; à partir de là,
# et uniquement à partir de là, il redevient accessible en lecture via safe_path().
# Cadrage strict de ces deux routes, à ne jamais relâcher :
#   - dossiers uniquement : jamais de fichier, jamais de contenu, jamais de taille ;
#   - un seul niveau de profondeur par appel (aucune récursion) ;
#   - les dossiers illisibles (droits système) sont ignorés silencieusement ;
#   - elles restent soumises comme toute route /api/* à ApiTokenMiddleware
#     (API_TOKEN) — voir plus haut. Ne pas les exempter de ce middleware.
@app.get("/api/fs/drives")
async def fs_drives():
    """Lecteurs disponibles : lettres existantes sous Windows, '/' sous POSIX."""
    drives: list[str] = []
    if os.name == "nt":
        import string
        for letter in string.ascii_uppercase:
            d = Path(f"{letter}:/")
            try:
                if d.exists():
                    drives.append(str(d))
            except OSError:
                continue
    else:
        drives.append("/")
    return {"drives": drives}


@app.get("/api/fs/browse")
async def fs_browse(path: str = Query(..., description="Chemin absolu (hors sandbox)")):
    """Sous-dossiers directs d'un chemin absolu — et rien d'autre (voir note ci-dessus)."""
    p = Path(path)
    if not p.is_absolute():
        raise HTTPException(400, "Chemin absolu requis")
    if not p.exists() or not p.is_dir():
        raise HTTPException(404, f"Dossier introuvable : {p}")
    folders: list[dict] = []
    try:
        children = sorted(p.iterdir(), key=lambda x: x.name.lower())
    except (PermissionError, OSError):
        children = []
    for entry in children:
        try:
            if entry.is_dir():
                folders.append({"name": entry.name, "path": str(entry)})
        except OSError:
            continue
    return {"path": str(p), "folders": folders}


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
    if "fs_roots" in patch:
        raw_list = patch.get("fs_roots")
        if not isinstance(raw_list, list):
            raise HTTPException(400, "fs_roots doit être une liste de chemins")
        cleaned = []
        for entry in raw_list:
            if isinstance(entry, str):
                v = entry.strip()
                label = ""
            elif isinstance(entry, dict):
                v = str(entry.get("path") or "").strip()
                label = str(entry.get("label") or "").strip()[:60]
            else:
                raise HTTPException(400, "fs_roots doit être une liste de chemins")
            if not v:
                continue
            # Une liste vide signifie "revenir au défaut" : toujours autorisée.
            if not Path(v).is_dir():
                raise HTTPException(400, f"Dossier introuvable : {v}")
            cleaned.append({"path": v, "label": label})
        patch["fs_roots"] = cleaned
    settings.update(patch)
    return JSONResponse(_mask_secrets(settings.get()))


def _strip_masked(patch: dict):
    for conn in patch.get("connectors", {}).values():
        if isinstance(conn, dict):
            for k in list(conn.keys()):
                if conn[k] == "••••••••":
                    del conn[k]
    # Sans ceci, ré-enregistrer les paramètres depuis l'UI écraserait la vraie
    # clé par la valeur d'affichage masquée.
    for k in TOP_LEVEL_SECRET_KEYS:
        if patch.get(k) == "••••••••":
            del patch[k]


# ---------- Route Recherche web ----------
@app.post("/api/search")
async def do_search(body: dict):
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query manquante")
    s = settings.get()
    provider = s.get("search_provider", "duckduckgo")
    try:
        used_provider, results = await web_search(
            provider, query,
            searxng_url=s.get("searxng_url", "http://localhost:8888"),
            brave_api_key=s.get("search_brave_api_key", ""),
            limit=body.get("limit", 5),
        )
        return {"provider": used_provider, "query": query, "results": results}
    except Exception as e:
        raise HTTPException(502, f"Erreur recherche : {e}")


# ---------- Routes Conversations ----------
@app.get("/api/conversations")
async def list_conversations():
    """Liste des conversations (métadonnées seules), triées par date de mise à jour."""
    return {"conversations": conversations.list_conversations()}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    """Conversation complète (messages inclus)."""
    conv = conversations.get_conversation(conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation introuvable")
    return conv


@app.post("/api/conversations")
async def create_conversation(body: dict):
    """Crée une nouvelle conversation et la renvoie (avec son id)."""
    return conversations.create_conversation(
        messages=body.get("messages"), title=body.get("title"),
    )


@app.put("/api/conversations/{conv_id}")
async def update_conversation(conv_id: str, body: dict):
    """Met à jour les messages et/ou le titre d'une conversation existante."""
    conv = conversations.update_conversation(
        conv_id, messages=body.get("messages"), title=body.get("title"),
    )
    if conv is None:
        raise HTTPException(404, "Conversation introuvable")
    return conv


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    """Supprime une conversation."""
    if not conversations.delete_conversation(conv_id):
        raise HTTPException(404, "Conversation introuvable")
    return {"ok": True}


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
        "conversations": conversations.export_all_conversations(),
        "note": "Toutes vos données restent sur cette machine. Aucun envoi externe.",
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="mes-donnees-local-ai.json"'},
    )


@app.post("/api/privacy/delete")
async def privacy_delete():
    """Droit à l'effacement : réinitialise les paramètres + purge la zone d'upload de l'app
    dans chacune des racines documentaires configurées."""
    removed = 0
    for root in get_fs_roots():
        upload_dir = root / UPLOAD_SUBDIR
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
    conversations_removed = conversations.delete_all_conversations()
    return {
        "ok": True, "settings_reset": True, "uploads_removed": removed,
        "conversations_removed": conversations_removed,
    }


# ---------- Health ----------
@app.get("/api/health")
async def health():
    s = settings.get()
    return {
        "status": "ok",
        "version": app.version,
        "ollama": OLLAMA_URL,
        "fs_roots": [{"path": str(p), "label": label} for p, label in get_fs_root_entries()],
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
