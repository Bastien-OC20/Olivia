"""
FastAPI backend pour Olivia (assistante locale).

Routes principales :
  POST /api/auth/login                   : ouvre une session (cookie HttpOnly)
  POST /api/auth/logout                  : ferme la session courante
  GET  /api/auth/me                      : compte et organisation connectés
  GET  /api/health                       : diagnostic de service
  GET  /api/models                       : liste des modèles Ollama installés
  GET  /api/settings                     : retourne les réglages du profil (secrets masqués)
  PUT  /api/settings                     : patch partiel des paramètres
  POST /api/chat/stream                  : appel Ollama SSE (token par token)
  POST /api/chat                         : appel Ollama non-stream
  GET  /api/fs/list                      : liste un dossier (sandboxé)
  GET  /api/fs/read                      : lit un fichier texte (sandboxé, filtré)
  GET  /api/fs/text                      : texte brut d'un document (docx/xlsx/pdf/texte)
  GET  /api/fs/search                    : recherche en langage courant (docx/xlsx/pdf/texte)
  GET  /api/fs/search/semantic           : recherche par le sens (embeddings + FAISS)
  GET  /api/docindex/status              : état de l'index sémantique
  POST /api/docindex/build               : construit/met à jour l'index sémantique
  POST /api/docindex/cancel              : interrompt la construction en cours
  GET  /api/fs/preview                   : prévisualisation (txt/csv/xlsx/docx/img/pdf)
  POST /api/fs/upload                    : upload d'un fichier (sandboxé, filtré)
  GET  /api/fs/download                  : téléchargement d'un fichier (sandboxé)
  GET  /api/fs/drives                    : lecteurs disponibles (hors sandbox, dossiers only)
  GET  /api/fs/browse                    : sous-dossiers d'un chemin absolu (hors sandbox)
  GET  /api/documents/status             : état du modèle Word de l'établissement
  POST /api/documents/modele             : (re)fabrique le modèle depuis un document réel
  POST /api/documents/generate           : produit un document Word (sandboxé)
  POST /api/search                       : recherche web via provider configuré
  GET  /api/connectors/status            : état stylisable de tous les connecteurs
  GET  /api/connectors/mail/unread       : nombre d'e-mails non lus (notifications)
  GET  /api/connectors/imap/preview      : aperçu boîte mail
  GET  /api/connectors/calendar/preview  : aperçu calendrier .ics
  GET  /api/privacy/export               : RGPD — export des données de l'organisation
  POST /api/privacy/delete               : RGPD — suppression des données de l'organisation
  GET  /api/conversations                : liste des conversations (métadonnées)
  GET  /api/conversations/{conv_id}      : conversation complète
  POST /api/conversations                : crée une conversation
  PUT  /api/conversations/{conv_id}      : met à jour une conversation
  DELETE /api/conversations/{conv_id}    : supprime une conversation
  /ui                                    : interface Vue buildée (frontend/dist)

CLOISONNEMENT PAR ORGANISATION : hormis /api/health (diagnostic de service) et
/api/auth/login, toute route /api/* exige une session ouverte et ne travaille que
sur le profil qu'elle résout, via `Depends(get_current_profile)`. Aucun
identifiant d'organisation n'est jamais accepté depuis le client.
"""
import os
import re
import sys
import shutil
from pathlib import Path
from typing import Optional

import httpx
from fastapi import (
    Depends, FastAPI, File, HTTPException, Query, Request, Response, UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (
    StreamingResponse, JSONResponse, FileResponse, RedirectResponse, PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from .settings import reglages, style_directives
from .search import web_search
from . import documents
from . import docsearch
from . import docindex
from . import docgen
from . import docmodele
from . import ocr
from . import conversations
from . import profiles
from . import sessions
from . import users
from .connectors import (
    read_inbox,
    unread_count,
    calendar_list_events,
)

# ---------- Configuration runtime ----------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Valeur par défaut (variable d'env ou ~/Documents) — utilisée si aucun dossier valide
# n'est configuré dans les paramètres, ou si le dossier configuré n'existe plus.
FS_ROOT_DEFAULT = Path(os.getenv("FS_ROOT", os.path.expanduser("~/Documents"))).resolve()
UPLOAD_SUBDIR = "_uploads"                       # RGPD : zone de données créée par l'app
MAX_FILE_SIZE = 1_000_000                         # 1 Mo pour la lecture texte
MAX_UPLOAD_SIZE = 25 * 1024 * 1024                # 25 Mo pour l'upload
# Garde-fou de génération : borne le nombre de tokens qu'une réponse peut
# produire, quel que soit le modèle. Sans cette limite, un modèle qui part en
# boucle (constaté avec certains modèles Qwen3 combinés au style « détaillé »,
# voir DEVICE_MODELS dans settings.py) peut tourner des dizaines de minutes à
# pleine charge sans jamais s'arrêter — source probable d'un plantage machine
# en test. 4096 tokens couvrent largement le plus long document produit par
# Olivia (circulaire, compte rendu détaillé) sans jamais tronquer une réponse
# légitime, tout en bornant le pire cas à quelques minutes même sur un modèle
# lent en CPU.
MAX_TOKENS_REPONSE = 4096

ALLOWED_EXT = {".txt", ".md", ".py", ".js", ".ts", ".vue", ".json",
               ".yaml", ".yml", ".csv", ".html", ".css", ".log", ".sh"}
# Extensions acceptées à l'upload / preview (plus large que la lecture texte brute).
# Un secrétariat reçoit des formats qu'aucune bibliothèque du projet ne sait lire —
# .xls d'un export de logiciel scolaire, .doc ancien, .odt d'un poste LibreOffice.
# Les refuser à l'import serait absurde : le dossier de travail est celui de
# l'utilisatrice, elle doit pouvoir y déposer ses fichiers même si Olivia ne sait
# pas encore les ouvrir. L'aperçu annoncera alors « format non prévisualisable ».
BUREAUTIQUE_EXT = {".docx", ".doc", ".xlsx", ".xlsm", ".xls", ".pptx", ".ppt",
                   ".odt", ".ods", ".odp", ".rtf", ".pdf"}
# .tif/.tiff : formats de sortie courants des scanners et des télécopieurs — et
# l'OCR sait déjà les lire (voir OCR_IMAGE_EXT dans documents.py).
IMAGE_UPLOAD_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp",
                    ".tif", ".tiff"}
UPLOAD_EXT = ALLOWED_EXT | BUREAUTIQUE_EXT | IMAGE_UPLOAD_EXT

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


# Note : un middleware exigeait auparavant un jeton statique partagé (API_TOKEN /
# en-tête X-API-Token) sur /api/*. Il a été retiré avec l'arrivée des sessions :
# un secret unique commun à tout le monde n'identifie personne, et il ne pouvait
# donc pas servir de base au cloisonnement par organisation. L'authentification
# passe désormais par /api/auth/login et le cookie de session (voir plus bas).

app.add_middleware(SecurityHeadersMiddleware)
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


class BlocContenu(BaseModel):
    """Un bloc de contenu déjà structuré (voir backend/docgen.py)."""
    type: str = "paragraphe"
    texte: str = ""
    niveau: int = 1
    items: list[str] = []
    lignes: list[list[str]] = []


class DemandeDocument(BaseModel):
    """Demande de production d'un document Word.

    `contenu` (blocs structurés) l'emporte sur `texte` (réponse brute d'Olivia,
    structurée côté serveur). Dans les deux cas c'est le CONTENU qui arrive ici :
    la mise en forme est décidée par `docgen`, jamais par le modèle.
    """
    type: str = "circulaire"
    titre: str = ""
    objet: str = ""
    texte: str = ""
    contenu: list[BlocContenu] = []
    destinataire: str = ""
    lieu: str = ""
    date: str = ""
    participants: list[str] = []
    appel: str = ""
    formule_politesse: str = ""
    signature: str = ""
    dossier: str = ""
    nom_fichier: str = ""


# ---------- Authentification : session et profil courant ----------
# Une session Olivia = un cookie contenant un jeton opaque (voir sessions.py).
# HttpOnly : le jeton reste inaccessible à tout script de la page, donc une
# éventuelle faille XSS ne permet pas de l'exfiltrer.
# Pas de `secure=True` : le déploiement de référence est un poste ou un serveur
# de réseau local SANS TLS, où un cookie Secure ne serait jamais renvoyé — à
# passer à True le jour où Olivia est exposée en HTTPS.
# SameSite=Lax : un site tiers ne peut pas déclencher de requête authentifiée en
# POST/PUT/DELETE ; CORS est par ailleurs déjà restreint au poste local.
COOKIE_SESSION = "olivia_session"


class DemandeConnexion(BaseModel):
    username: str
    password: str


def _identite(user: dict) -> dict:
    """Vue publique d'un compte : jamais le hash, jamais d'horodatage interne."""
    profil = profiles.get_profile(user.get("profile_id", ""))
    return {
        "user_id": user.get("id", ""),
        "username": user.get("username", ""),
        "profile_id": user.get("profile_id", ""),
        "profile_name": profil["name"] if profil else "",
    }


def get_current_session(request: Request) -> dict:
    """Session résolue depuis le cookie, ou 401 si absente/invalide/expirée."""
    session = sessions.resolve_session(request.cookies.get(COOKIE_SESSION, ""))
    if session is None:
        raise HTTPException(401, "Session absente, invalide ou expirée")
    return session


def get_current_profile(request: Request) -> str:
    """Identifiant du profil (organisation) de la session courante, ou 401.

    C'est LE point d'entrée du cloisonnement : toute route touchant à des données
    d'organisation doit passer par Depends(get_current_profile) et n'utiliser que
    ce profile_id — jamais un identifiant fourni par le client, qui pourrait
    désigner l'organisation d'à côté.
    """
    profile_id = get_current_session(request).get("profile_id", "")
    if not profiles.is_valid_id(profile_id):
        raise HTTPException(401, "Session rattachée à un profil invalide")
    return profile_id


@app.post("/api/auth/login")
async def auth_login(demande: DemandeConnexion, response: Response):
    """Vérifie les identifiants et ouvre une session."""
    user = users.verify_credentials(demande.username, demande.password)
    if user is None:
        # Message volontairement unique : ne dit pas si le compte existe.
        raise HTTPException(401, "Identifiant ou mot de passe incorrect")
    token = sessions.create_session(user["id"], user["profile_id"])
    response.set_cookie(
        COOKIE_SESSION, token,
        max_age=sessions.SESSION_TTL_SECONDS,
        httponly=True, samesite="lax", secure=False, path="/",
    )
    return _identite(user)


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    """Ferme la session courante. Idempotent : réussit même sans session valide,
    pour qu'un cookie périmé n'empêche jamais de se déconnecter."""
    sessions.delete_session(request.cookies.get(COOKIE_SESSION, ""))
    response.delete_cookie(COOKIE_SESSION, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
async def auth_me(session: dict = Depends(get_current_session)):
    """Compte et organisation de la session courante."""
    user = users.get_user(session.get("user_id", ""))
    if user is None:
        # Session valide mais compte supprimé entre-temps : à traiter comme une
        # session morte, pas comme une erreur serveur.
        raise HTTPException(401, "Compte introuvable")
    return _identite(user)


# ---------- Sécurité : anti path-traversal ----------
# Les dossiers documentaires (`fs_roots`) sont un RÉGLAGE, donc désormais propres à
# une organisation : ces trois fonctions prennent le `profile_id` de la session et
# ne voient jamais les dossiers d'un autre profil. Un même dossier physique peut
# être déclaré par deux organisations — c'est le choix de l'exploitant, pas une
# fuite : Olivia n'ouvre que ce qu'on lui a désigné.
def get_fs_root_entries(profile_id: str) -> list[tuple[Path, str]]:
    """Racines FS effectives de cette organisation, avec leur libellé éventuel :
    liste de tuples
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
    s = reglages(profile_id).get()
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


def get_fs_roots(profile_id: str) -> list[Path]:
    """Racines FS effectives (chemins seuls) — dérivé de get_fs_root_entries()."""
    return [p for p, _ in get_fs_root_entries(profile_id)]


_R_PREFIX_RE = re.compile(r"^r(\d+)$")


def safe_path(profile_id: str, virtual: str) -> tuple[Path, Path, str]:
    """Résout un chemin virtuel `rN/...` vers (chemin_absolu, racine, préfixe 'rN').

    Les `rN` sont indexés sur les racines de CETTE organisation : le même `r0`
    désigne un dossier différent pour deux profils, et un `rN` que le profil
    appelant n'a pas configuré répond 404.

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
    roots = get_fs_roots(profile_id)
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
async def list_models(profile_id: str = Depends(get_current_profile)):
    """Modèles installés utilisables pour la CONVERSATION.

    Ne lit aucun réglage, mais reste réservée à une session ouverte comme toute
    route /api/* : la liste des modèles installés est une information sur la
    machine, pas une donnée publique.

    Ollama liste tous les modèles installés sans distinction d'usage — un
    modèle d'embeddings comme bge-m3 (tiré pour la recherche par le sens, voir
    docindex.py) s'y retrouve mélangé aux modèles de conversation. Envoyé tel
    quel au front-end, il devenait sélectionnable dans le menu, et pouvait même
    être choisi par défaut (le premier de la liste) : les réponses de chat
    échouent ou sont incohérentes avec un modèle qui n'a pas de gabarit de
    conversation. On filtre donc sur `capabilities`, exposé par Ollama lui-même
    (« completion » = sait converser), plutôt que sur une liste de noms à
    maintenir à la main — un futur modèle d'embeddings serait filtré pareil.
    """
    async with httpx.AsyncClient(timeout=10) as client:
        try:
            r = await client.get(f"{OLLAMA_URL}/api/tags")
            r.raise_for_status()
            data = r.json()
            return {"models": [
                {"name": m["name"], "size_gb": round(m.get("size", 0) / 1e9, 2)}
                for m in data.get("models", [])
                if "completion" in (m.get("capabilities") or [])
            ]}
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Ollama injoignable : {e}")


def _build_options(profile_id: str, temperature: float | None) -> dict:
    s = reglages(profile_id).get()
    eff_temp = s.get("temperature", 0.7) if temperature is None else temperature
    options = {"temperature": eff_temp, "num_predict": MAX_TOKENS_REPONSE}
    # CPU/GPU : num_gpu=0 force le calcul CPU ; sinon Ollama utilise le GPU auto.
    if s.get("compute_device") == "cpu":
        options["num_gpu"] = 0
    return options


def _inject_system_prompt(profile_id: str, messages: list[ChatMessage]) -> list[dict]:
    s = reglages(profile_id).get()
    directive = style_directives(s.get("reasoning_style", "balanced"), s.get("tone", "neutral"))
    custom = s.get("system_prompt", "").strip()
    combined = (custom + " " + directive).strip() or "Tu es un assistant IA local."
    out = [{"role": "system", "content": combined}]
    out.extend(m.dict() for m in messages)
    return out


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest, profile_id: str = Depends(get_current_profile)):
    body = {
        "model": req.model,
        "messages": _inject_system_prompt(profile_id, req.messages),
        "stream": True,
        "options": _build_options(profile_id, req.temperature),
        # -1 : le modèle reste chargé en mémoire indéfiniment. Poste dédié à
        # Olivia (pas de partage GPU) : évite de repayer le chargement complet
        # après chaque pause de plus de 5 min (défaut Ollama).
        "keep_alive": -1,
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
async def chat_blocking(req: ChatRequest, profile_id: str = Depends(get_current_profile)):
    body = {
        "model": req.model,
        "messages": _inject_system_prompt(profile_id, req.messages),
        "stream": False,
        "options": _build_options(profile_id, req.temperature),
        "keep_alive": -1,
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
async def fs_list(path: str = Query("", description="Chemin virtuel rN/... (vide = racine)"),
                  profile_id: str = Depends(get_current_profile)):
    raw = (path or "").strip()
    entries = get_fs_root_entries(profile_id)

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

    p, root, prefix = safe_path(profile_id, raw)
    if not p.exists():
        raise HTTPException(404, f"Dossier introuvable : {p}")
    if not p.is_dir():
        raise HTTPException(400, f"Pas un dossier : {p}")
    m = _R_PREFIX_RE.match(prefix)
    if not m:
        raise HTTPException(400, f"Préfixe invalide : {prefix}")
    idx = int(m.group(1))
    root_label = entries[idx][1] or root.name
    return {
        "root": str(root), "current": raw, "items": _list_dir_items(p, root, prefix),
        "root_label": root_label,
    }


@app.get("/api/fs/read")
async def fs_read(path: str = Query(...), profile_id: str = Depends(get_current_profile)):
    p, root, prefix = safe_path(profile_id, path)
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
async def fs_preview(path: str = Query(...), profile_id: str = Depends(get_current_profile)):
    p, root, prefix = safe_path(profile_id, path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    rel = _virtual_path(p, root, prefix)
    download_url = f"/api/fs/download?path={rel}"
    result = documents.preview(p, download_url)
    result["path"] = rel
    result["name"] = p.name
    return result


# Budget de texte injecté dans la conversation pour UN document. Au-delà, le
# contenu est coupé et l'interface doit le dire (voir `truncated`).
MAX_TEXT_CHARS = 60_000


@app.get("/api/fs/text")
def fs_text(path: str = Query(...), profile_id: str = Depends(get_current_profile)):
    """Texte brut d'un document (Word, Excel, PDF, texte, CSV), pour la conversation.

    Complète `/api/fs/preview`, qui produit un aperçu structuré destiné à
    l'affichage : ici on veut le contenu lisible par le modèle.
    """
    p, root, prefix = safe_path(profile_id, path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    if p.suffix.lower() not in documents.SEARCHABLE_EXT:
        raise HTTPException(400, f"Ce type de fichier ne contient pas de texte : {p.suffix}")
    content = documents.extract_text(profile_id, p)
    truncated = len(content) > MAX_TEXT_CHARS
    return {
        "path": _virtual_path(p, root, prefix),
        "name": p.name,
        "content": content[:MAX_TEXT_CHARS],
        "truncated": truncated,
        "empty": not content.strip(),
    }


@app.get("/api/fs/download")
async def fs_download(path: str = Query(...), profile_id: str = Depends(get_current_profile)):
    p, _root, _prefix = safe_path(profile_id, path)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Fichier introuvable : {p}")
    return FileResponse(str(p), filename=p.name)


@app.post("/api/fs/upload")
async def fs_upload(file: UploadFile = File(...), path: str = Query(""),
                    profile_id: str = Depends(get_current_profile)):
    # Nom de fichier assaini : on ne garde que le basename.
    safe_name = Path(file.filename or "fichier").name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(400, "Nom de fichier invalide")
    ext = Path(safe_name).suffix.lower()
    if ext not in UPLOAD_EXT:
        # Message explicite : « type non autorisé » sans dire lesquels le sont
        # laisse l'utilisatrice sans solution.
        courants = ".pdf, .docx, .xlsx, .xls, .csv, .txt, images (.png, .jpg, .tif)"
        raise HTTPException(
            400,
            f"Format « {ext or 'inconnu'} » non accepté à l'import. "
            f"Formats courants acceptés : {courants}.",
        )

    raw = (path or "").strip()
    if raw == "":
        root = get_fs_roots(profile_id)[0]
        prefix = "r0"
        target_dir = root / UPLOAD_SUBDIR
    else:
        target_dir, root, prefix = safe_path(profile_id, raw)
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
    # Le fichier vient d'apparaître : sans ce déclenchement, il resterait
    # introuvable par la recherche par le sens jusqu'au prochain démarrage ou
    # clic manuel sur « Construire l'index ». Tâche de fond, jamais bloquant.
    _indexer_automatiquement(profile_id)
    return {"path": _virtual_path(dest, root, prefix), "name": safe_name, "size": size}


def _iter_searchable_files(targets):
    """Parcourt les dossiers autorisés et produit (chemin absolu, chemin virtuel).

    Sécurité : `os.walk` ne suit pas les liens symboliques, et chaque fichier
    retenu est en plus revérifié comme étant bien sous sa racine — un lien
    pointant hors du périmètre ne peut donc pas être lu.
    """
    for search_dir, root, prefix in targets:
        for dirpath, dirnames, filenames in os.walk(search_dir):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")
                           and d.lower() not in docsearch.IGNORED_DIRS]
            base = Path(dirpath)
            for name in filenames:
                fp = base / name
                try:
                    reel = fp.resolve()
                    reel.relative_to(root)
                except (OSError, ValueError):
                    continue
                yield fp, _virtual_path(fp, root, prefix)


def _resolve_search_targets(profile_id: str, path: str) -> list[tuple[Path, Path, str]]:
    """Périmètre d'un balayage : (dossier à parcourir, racine, préfixe 'rN').

    Chemin vide = toutes les racines configurées PAR CETTE ORGANISATION. Sinon un
    seul sous-dossier, validé par `safe_path()` — le balayage reste donc borné au
    sandbox du profil appelant.
    """
    raw = (path or "").strip()
    if raw == "":
        return [(r, r, f"r{i}") for i, r in enumerate(get_fs_roots(profile_id))]
    p, root, prefix = safe_path(profile_id, raw)
    if not p.is_dir():
        raise HTTPException(400, "Le chemin doit être un dossier")
    return [(p, root, prefix)]


def _virtual_for_abs(profile_id: str, p: Path) -> str | None:
    """Chemin virtuel rN/... pour un chemin absolu, ou None s'il ne tombe sous
    aucune racine actuellement autorisée pour cette organisation."""
    for i, root in enumerate(get_fs_roots(profile_id)):
        try:
            rel = p.resolve().relative_to(root)
        except (OSError, ValueError):
            continue
        return f"r{i}" if str(rel) == "." else f"r{i}/{rel.as_posix()}"
    return None


# Route volontairement synchrone (def et non async def) : l'extraction de texte
# est un travail CPU/disque bloquant. FastAPI l'exécute alors dans son pool de
# threads, ce qui évite de figer le reste de l'application pendant une recherche.
@app.get("/api/fs/search")
def fs_search(q: str = Query(..., min_length=1), path: str = Query(""),
              profile_id: str = Depends(get_current_profile)):
    """Recherche en langage courant dans le contenu des documents.

    La requête est une phrase ordinaire (jamais une expression régulière) ;
    la comparaison ignore la casse et les accents ; les résultats sont groupés
    par document et classés par pertinence. Voir `docsearch.py`.
    """
    cibles = _resolve_search_targets(profile_id, path)
    return docsearch.search(profile_id, _iter_searchable_files(cibles), q)


# ---------- Routes Recherche par le sens (embeddings + index vectoriel) ----------
def _indexer_automatiquement(profile_id: str) -> None:
    """Lance une mise à jour de l'index sémantique d'UNE organisation en tâche de
    fond, sans jamais bloquer l'appelant : au démarrage de l'application (rattrape
    les documents ajoutés pendant qu'Olivia n'était pas lancée) et après chaque
    import réussi (`/api/fs/upload`), pour qu'un fichier tout juste déposé soit
    cherchable par le sens sans action manuelle.

    Ne fait rien si le modèle bge-m3 n'est pas installé : lancer quand même la
    construction échouerait fichier par fichier sans jamais aboutir — mieux vaut
    ne pas occuper un thread pour ça. `lancer_construction()` refuse par ailleurs
    silencieusement si une construction tourne déjà POUR CE PROFIL (verrou par
    organisation), donc un import pendant une construction en cours ne fait
    qu'attendre le prochain passage — et n'empêche jamais une autre organisation
    de construire le sien.
    """
    if docindex.etat(profile_id).get("modele_disponible"):
        cibles = _resolve_search_targets(profile_id, "")
        docindex.lancer_construction(profile_id, _iter_searchable_files(cibles))


@app.on_event("startup")
def _demarrer_indexation_semantique():
    """Rattrapage au démarrage, POUR CHAQUE organisation provisionnée.

    Il n'y a pas de session ouverte à cet instant : on ne peut pas résoudre « le »
    profil courant, et laisser l'indexation attendre la première connexion
    priverait la recherche par le sens des documents ajoutés hors ligne. On balaie
    donc le registre. Chaque profil a son propre verrou et son propre index, donc
    ces constructions cohabitent ; elles se mettent naturellement en file sur
    Ollama, qui sert les requêtes d'embeddings une à une.
    """
    try:
        profils = profiles.list_profiles()
    except Exception:
        # Registre absent (installation neuve) ou illisible : le démarrage du
        # service ne doit jamais en dépendre.
        return
    for profil in profils:
        try:
            _indexer_automatiquement(profil["id"])
        except Exception:
            continue


@app.get("/api/docindex/status")
def docindex_status(profile_id: str = Depends(get_current_profile)):
    """État de l'index sémantique (embeddings bge-m3 + FAISS). Voir docindex.etat()."""
    return docindex.etat(profile_id)


@app.post("/api/docindex/build")
def docindex_build(path: str = Query(""), profile_id: str = Depends(get_current_profile)):
    """Démarre (ou signale déjà en cours) la construction/mise à jour de l'index
    sémantique en tâche de fond. Route synchrone : le lancement est instantané,
    le travail réel se fait dans un thread démon (voir docindex.py)."""
    targets = _resolve_search_targets(profile_id, path)
    demarree = docindex.lancer_construction(profile_id, _iter_searchable_files(targets))
    etat = docindex.etat(profile_id)
    etat["demarree"] = demarree
    return etat


@app.post("/api/docindex/cancel")
def docindex_cancel(profile_id: str = Depends(get_current_profile)):
    """Interrompt la construction en cours de cette organisation : l'arrêt est
    effectif entre deux fichiers, et le travail déjà fait est conservé. Une
    construction lancée par une autre organisation n'est pas touchée."""
    docindex.annuler_construction(profile_id)
    return docindex.etat(profile_id)


@app.get("/api/fs/search/semantic")
def fs_search_semantic(q: str = Query(..., min_length=1), path: str = Query(""),
                       profile_id: str = Depends(get_current_profile)):
    """Recherche par le sens (embeddings + FAISS) — voir docindex.py. Ne renvoie
    que des résultats sous une racine actuellement configurée : une entrée de
    l'index devenue hors périmètre (fs_roots reconfiguré depuis la construction)
    est silencieusement écartée, jamais exposée."""
    dossier = None
    raw = (path or "").strip()
    if raw:
        p, _root, _prefix = safe_path(profile_id, raw)
        dossier = p
    brut = docindex.rechercher(profile_id, q, k=10, dossier=dossier)
    resultats = []
    for r in brut["results"]:
        virtuel = _virtual_for_abs(profile_id, Path(r["path"]))
        if virtuel is None:
            continue
        resultats.append({**r, "path": virtuel})
    brut["results"] = resultats
    brut["mode"] = "semantic"
    return brut


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
#   - elles doivent rester réservées à une session authentifiée comme toute route
#     /api/* (voir get_current_profile) : ne jamais les en exempter.
@app.get("/api/fs/drives")
async def fs_drives(profile_id: str = Depends(get_current_profile)):
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
async def fs_browse(path: str = Query(..., description="Chemin absolu (hors sandbox)"),
                    profile_id: str = Depends(get_current_profile)):
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
async def get_settings(profile_id: str = Depends(get_current_profile)):
    """Réglages de l'organisation connectée (jamais ceux d'une autre)."""
    return JSONResponse(_mask_secrets(reglages(profile_id).get()))


@app.put("/api/settings")
async def update_settings(patch: dict, profile_id: str = Depends(get_current_profile)):
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
    reglages_profil = reglages(profile_id)
    reglages_profil.update(patch)
    return JSONResponse(_mask_secrets(reglages_profil.get()))


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


# ---------- Route Reconnaissance de caractères (documents scannés) ----------
@app.get("/api/ocr/status")
def ocr_status(profile_id: str = Depends(get_current_profile)):
    """État du moteur de reconnaissance, affiché dans Paramètres → Documents.

    Le moteur est commun à la machine, mais les deux réglages qui le pilotent
    (`ocr_enabled`, `ocr_tesseract_path`) sont ceux de l'organisation connectée.

    Route volontairement synchrone : elle touche le disque (présence du binaire,
    langues installées). Elle ne déclenche aucune reconnaissance.
    """
    return ocr.etat(profile_id)


# ---------- Routes Production de documents Word ----------
# Caractères refusés par Windows dans un nom de fichier, plus les séparateurs :
# le nom vient de l'interface, donc de l'utilisatrice, donc potentiellement de la
# réponse d'un modèle. On n'en garde qu'un nom de fichier nu.
_CAR_INTERDITS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# Noms réservés MS-DOS : un fichier « CON.docx » est impossible à créer.
_NOMS_RESERVES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | \
                 {f"LPT{i}" for i in range(1, 10)}
MAX_NOM_FICHIER = 120


def _nom_document_sain(brut: str, defaut: str = "document") -> str:
    """Nom de fichier .docx assaini : basename seul, sans caractère interdit.

    Même esprit que `fs_upload` : on ne fait jamais confiance au nom reçu. Toute
    tentative de traversée (`../`, `C:\\...`, séparateur) est écrasée ici, et
    `safe_path()` reste le garde-fou sur le dossier de destination.
    """
    nom = Path((brut or "").strip()).name
    nom = _CAR_INTERDITS.sub(" ", nom)
    nom = re.sub(r"\s+", " ", nom).strip(" .")
    if nom.lower().endswith(".docx"):
        nom = nom[:-5].strip(" .")
    if not nom or nom in {".", ".."}:
        nom = defaut
    if nom.upper() in _NOMS_RESERVES:
        nom = f"_{nom}"
    return f"{nom[:MAX_NOM_FICHIER]}.docx"


def _destination_libre(dossier: Path, nom: str) -> Path:
    """Chemin non existant : on n'écrase JAMAIS un document déjà là."""
    base, ext = os.path.splitext(nom)
    candidat = dossier / nom
    i = 2
    while candidat.exists():
        candidat = dossier / f"{base} ({i}){ext}"
        i += 1
        if i > 500:
            raise HTTPException(409, "Trop de documents portent déjà ce nom.")
    return candidat


@app.get("/api/documents/status")
def documents_status(profile_id: str = Depends(get_current_profile)):
    """État du modèle Word de l'établissement (Paramètres → Documents)."""
    etat = docmodele.etat(profile_id)
    etat["types"] = [{"id": k, "libelle": v["libelle"]} for k, v in docgen.PROFILS.items()]
    return etat


@app.post("/api/documents/modele")
async def documents_modele(body: dict, profile_id: str = Depends(get_current_profile)):
    """(Re)fabrique le modèle de l'établissement à partir d'un document réel.

    `source` est un chemin virtuel `rN/...` : la lecture reste sandboxée. Le
    modèle produit est écrit hors du sandbox, dans `modeles/`, à côté de
    l'application — il n'a pas à traîner dans les documents de l'utilisatrice.
    """
    source = (body.get("source") or "").strip()
    if not source:
        raise HTTPException(400, "Chemin du document source manquant")
    p, _root, _prefix = safe_path(profile_id, source)
    if not p.exists() or not p.is_file():
        raise HTTPException(404, f"Document introuvable : {source}")
    try:
        infos = docmodele.construire_modele(p, profile_id=profile_id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, f"Fabrication du modèle impossible : {e}")
    return {"ok": True, "modele": infos, "etat": docmodele.etat(profile_id)}


@app.post("/api/documents/generate")
async def documents_generate(demande: DemandeDocument,
                             profile_id: str = Depends(get_current_profile)):
    """Produit un document Word dans le dossier de travail de l'utilisatrice."""
    if demande.type not in docgen.PROFILS:
        raise HTTPException(400, f"Type de document inconnu : {demande.type}")

    raw = (demande.dossier or "").strip()
    if raw == "":
        root = get_fs_roots(profile_id)[0]
        prefix = "r0"
        dossier = root
    else:
        dossier, root, prefix = safe_path(profile_id, raw)
    if dossier.exists() and not dossier.is_dir():
        raise HTTPException(400, "La destination n'est pas un dossier")
    dossier.mkdir(parents=True, exist_ok=True)
    dossier = dossier.resolve()
    try:
        dossier.relative_to(root)          # revérifie le sandbox après création
    except ValueError:
        raise HTTPException(403, "Accès refusé : cible hors du périmètre autorisé")

    profil = docgen.PROFILS[demande.type]
    defaut = demande.titre.strip() or profil["titre_defaut"]
    nom = _nom_document_sain(demande.nom_fichier or defaut, profil["libelle"])
    dest = _destination_libre(dossier, nom)
    try:
        dest.resolve().parent.relative_to(root)
    except ValueError:
        raise HTTPException(403, "Accès refusé : cible hors du périmètre autorisé")

    charge = demande.model_dump()
    # Priorité : champ rempli dans la demande > réglage de l'utilisatrice >
    # défaut codé dans docgen.TEXTES. On ne remplace QUE les champs laissés
    # vides par la requête — une valeur saisie dans le formulaire doit primer.
    s = reglages(profile_id).get()
    for champ, cle_reglage in (
        ("appel", "docgen_appel"),
        ("formule_politesse", "docgen_formule_politesse"),
        ("lieu", "docgen_lieu"),
        ("signature", "docgen_signature"),
    ):
        if not str(charge.get(champ) or "").strip():
            valeur = str(s.get(cle_reglage) or "").strip()
            if valeur:
                charge[champ] = valeur
    try:
        # Le modèle Word est résolu ICI, avec le profil connecté : `docgen` n'a pas
        # de session et retomberait sinon sur l'emplacement par défaut.
        infos = docgen.generer(charge, dest,
                               chemin_modele=docmodele.chemin_modele(profile_id))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(500, f"Création du document impossible : {e}")

    return {
        "path": _virtual_path(dest, root, prefix),
        "name": dest.name,
        "size": dest.stat().st_size,
        "type": infos["type"],
        "libelle": infos["libelle"],
        "titre": infos["titre"],
        "avertissement": infos["avertissement"],
    }


# ---------- Route Recherche web ----------
@app.post("/api/search")
async def do_search(body: dict, profile_id: str = Depends(get_current_profile)):
    query = (body.get("query") or "").strip()
    if not query:
        raise HTTPException(400, "query manquante")
    s = reglages(profile_id).get()
    provider = s.get("search_provider", "duckduckgo")
    try:
        used_provider, results = await web_search(
            provider, query,
            searxng_url=s.get("searxng_url", "http://localhost:8888"),
            brave_api_key=s.get("search_brave_api_key", ""),
            # Transmis explicitement : `search.py` ne lit plus les réglages, qui
            # appartiennent maintenant à une organisation (voir settings.py).
            official_only=bool(s.get("search_official_only", False)),
            limit=body.get("limit", 5),
        )
        return {"provider": used_provider, "query": query, "results": results}
    except Exception as e:
        raise HTTPException(502, f"Erreur recherche : {e}")


# ---------- Routes Conversations ----------
# Les quatre routes portant un {conv_id} répondent 404 — et non 403 — pour la
# conversation d'une AUTRE organisation : son fichier n'existe pas dans le dossier
# du profil appelant, donc un identifiant deviné est indiscernable d'un identifiant
# inventé. C'est exactement l'effet voulu : aucune réponse ne confirme l'existence
# d'une conversation qu'on n'a pas le droit de voir.
@app.get("/api/conversations")
async def list_conversations(profile_id: str = Depends(get_current_profile)):
    """Liste des conversations (métadonnées seules), triées par date de mise à jour."""
    return {"conversations": conversations.list_conversations(profile_id)}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str, profile_id: str = Depends(get_current_profile)):
    """Conversation complète (messages inclus)."""
    conv = conversations.get_conversation(profile_id, conv_id)
    if conv is None:
        raise HTTPException(404, "Conversation introuvable")
    return conv


@app.post("/api/conversations")
async def create_conversation(body: dict, profile_id: str = Depends(get_current_profile)):
    """Crée une nouvelle conversation et la renvoie (avec son id)."""
    return conversations.create_conversation(
        profile_id, messages=body.get("messages"), title=body.get("title"),
    )


@app.put("/api/conversations/{conv_id}")
async def update_conversation(conv_id: str, body: dict,
                              profile_id: str = Depends(get_current_profile)):
    """Met à jour les messages et/ou le titre d'une conversation existante."""
    conv = conversations.update_conversation(
        profile_id, conv_id, messages=body.get("messages"), title=body.get("title"),
    )
    if conv is None:
        raise HTTPException(404, "Conversation introuvable")
    return conv


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str, profile_id: str = Depends(get_current_profile)):
    """Supprime une conversation."""
    if not conversations.delete_conversation(profile_id, conv_id):
        raise HTTPException(404, "Conversation introuvable")
    return {"ok": True}


# ---------- Routes Connecteurs ----------
@app.get("/api/connectors/status")
async def connectors_status(profile_id: str = Depends(get_current_profile)):
    """État synthétique et stylisable des connecteurs de CETTE organisation.

    Les identifiants de connecteurs (hôte IMAP, comptes, jetons) vivent dans les
    réglages, donc par profil : deux organisations sur le même poste ne voient
    jamais la boîte mail l'une de l'autre.
    """
    c = reglages(profile_id).get().get("connectors", {})

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
        simple("obsidian", "Obsidian", "📝", c.get("obsidian", {}),
               lambda x: bool(x.get("vault_path"))),
        simple("notion", "Notion", "🔗", c.get("notion", {}),
               lambda x: bool(x.get("api_token"))),
    ]
    return {"connectors": out}


@app.get("/api/connectors/mail/unread")
async def connectors_mail_unread(profile_id: str = Depends(get_current_profile)):
    cfg = reglages(profile_id).get().get("connectors", {}).get("imap", {})
    if not cfg.get("enabled"):
        return {"enabled": False, "count": 0}
    try:
        count = unread_count(cfg.get("host", ""), cfg.get("user", ""),
                             cfg.get("password", ""), cfg.get("folder", "INBOX"))
        return {"enabled": True, "count": count, "label": cfg.get("label", "Boîte pro")}
    except Exception as e:
        return {"enabled": True, "count": 0, "error": str(e)}


@app.get("/api/connectors/imap/preview")
async def connectors_imap(limit: int = 10, profile_id: str = Depends(get_current_profile)):
    cfg = reglages(profile_id).get().get("connectors", {}).get("imap", {})
    if not cfg.get("enabled"):
        return {"enabled": False, "messages": []}
    try:
        msgs = read_inbox(cfg.get("host", ""), cfg.get("user", ""),
                          cfg.get("password", ""), cfg.get("folder", "INBOX"), limit=limit)
        return {"enabled": True, "messages": msgs}
    except Exception as e:
        raise HTTPException(502, f"Erreur IMAP : {e}")


@app.get("/api/connectors/calendar/preview")
async def connectors_calendar(profile_id: str = Depends(get_current_profile)):
    cfg = reglages(profile_id).get().get("connectors", {}).get("calendar_ics", {})
    if not cfg.get("enabled") or not cfg.get("path"):
        return {"enabled": False, "events": []}
    return {"enabled": True, "events": calendar_list_events(cfg.get("path", ""), limit=20)}


# ---------- RGPD ----------
# Ces deux routes n'agissent QUE sur l'organisation connectée. C'est le point le
# plus sensible du cloisonnement : en mode mono-organisation, elles agissaient sur
# la totalité du poste, et une demande de droit à l'oubli d'une collectivité
# effacerait les données de toutes les autres présentes sur la même machine.
# Toute évolution de ces routes doit préserver cette propriété.
@app.get("/api/privacy/export")
async def privacy_export(profile_id: str = Depends(get_current_profile)):
    """Droit d'accès/portabilité : export des données locales de l'organisation
    connectée (ses réglages et ses conversations), et d'elle seule."""
    profil = profiles.get_profile(profile_id)
    payload = {
        "organisation": (profil or {}).get("name", ""),
        "settings": reglages(profile_id).get(),
        "conversations": conversations.export_all_conversations(profile_id),
        "note": "Toutes vos données restent sur cette machine. Aucun envoi externe. "
                "Cet export ne contient que les données de votre organisation.",
    }
    return JSONResponse(
        payload,
        headers={"Content-Disposition": 'attachment; filename="mes-donnees-local-ai.json"'},
    )


@app.post("/api/privacy/delete")
async def privacy_delete(profile_id: str = Depends(get_current_profile)):
    """Droit à l'effacement, POUR LA SEULE ORGANISATION CONNECTÉE : réinitialise
    ses réglages, supprime ses conversations et son index sémantique, purge la zone
    d'upload de l'app dans chacune de SES racines documentaires, et retire du cache
    OCR les entrées venues de ces mêmes racines.

    L'ORDRE compte : les dossiers documentaires sont lus AVANT la réinitialisation
    des réglages, puisque c'est elle qui efface `fs_roots`. Les lire après ne
    donnerait plus que le dossier par défaut, et la zone d'upload comme le cache
    OCR de l'organisation resteraient en place — un effacement incomplet, annoncé
    comme complet.
    """
    racines = get_fs_roots(profile_id)
    removed = 0
    for root in racines:
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
    # Le texte reconnu sur les documents scannés et l'index sémantique sont des
    # RECOPIES du contenu de documents personnels : ils relèvent du droit à
    # l'effacement au même titre que les conversations. Le cache OCR étant commun
    # au poste, il est filtré sur les racines de cette organisation (voir
    # ocr.vider_cache) ; l'index, lui, est déjà propre au profil.
    ocr_cache_removed = ocr.vider_cache(racines)
    docindex_removed = docindex.purger_index(profile_id)
    reglages(profile_id).reset()
    conversations_removed = conversations.delete_all_conversations(profile_id)
    return {
        "ok": True, "settings_reset": True, "uploads_removed": removed,
        "conversations_removed": conversations_removed,
        "ocr_cache_removed": ocr_cache_removed,
        "docindex_removed": docindex_removed,
    }


# ---------- Health ----------
@app.get("/api/health")
async def health():
    """Diagnostic de SERVICE, volontairement laissé sans authentification.

    Choix assumé du cloisonnement : cette route ne rapporte plus `fs_roots`,
    `compute_device` ni la liste des connecteurs actifs. Ces trois informations
    sont devenues des réglages d'organisation, et /api/health n'a pas de session
    donc pas d'organisation à désigner — les servir aurait exigé soit d'en choisir
    une arbitrairement (faux), soit d'agréger tous les profils (fuite : les
    dossiers documentaires d'une collectivité, lisibles sans être connecté).
    Elle répond donc à la seule question qui la justifie : « le service est-il
    debout, et avec quoi parle-t-il ? ». Les informations retirées restent
    disponibles, authentifiées, sur /api/settings et /api/connectors/status.
    """
    return {
        "status": "ok",
        "version": app.version,
        "ollama": OLLAMA_URL,
        "frontend_ui": FRONTEND_DIST.exists(),
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
