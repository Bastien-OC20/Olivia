"""
Persistance des conversations dans backend/conversations/<id>.json (un fichier par
conversation).

Le dossier est créé automatiquement au premier accès. Toutes les écritures sont
mutexées et atomic-write sur disque (fichier .tmp puis remplacement), comme pour
settings.py.
"""
import json
import re
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

_ID_RE = re.compile(r"^[0-9a-f]{32}$")

TITLE_MAX_LEN = 60
TITLE_FALLBACK = "Nouvelle conversation"

CONVERSATIONS_DIR = Path(__file__).parent / "conversations"
_lock = RLock()


def _is_valid_id(conv_id: str) -> bool:
    """Valide un identifiant de conversation avant toute utilisation dans un chemin
    disque : refuse tout ce qui ne ressemble pas à un uuid4().hex, ce qui exclut
    d'office les tentatives de path traversal."""
    return bool(_ID_RE.match(conv_id or ""))


def _path_for(conv_id: str) -> Path:
    return CONVERSATIONS_DIR / f"{conv_id}.json"


def _derive_title(messages: list[dict]) -> str:
    """Dérive un titre à partir des ~60 premiers caractères du premier message
    utilisateur. Repli sur TITLE_FALLBACK si aucun message utilisateur."""
    for m in messages:
        if isinstance(m, dict) and m.get("role") == "user":
            content = (m.get("content") or "").strip()
            if not content:
                continue
            if len(content) > TITLE_MAX_LEN:
                return content[:TITLE_MAX_LEN].rstrip() + "…"
            return content
    return TITLE_FALLBACK


def _clean_messages(messages: list[dict] | None) -> list[dict]:
    """Normalise la liste de messages entrants : ne conserve `sources` et
    `searchNote` que s'ils sont présents (ne les invente pas sinon)."""
    cleaned = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        entry = {"role": m.get("role", ""), "content": m.get("content", "")}
        if "sources" in m:
            entry["sources"] = m["sources"]
        if "searchNote" in m:
            entry["searchNote"] = m["searchNote"]
        cleaned.append(entry)
    return cleaned


def _save(data: dict):
    CONVERSATIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(data["id"])
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def list_conversations() -> list[dict]:
    """Métadonnées de toutes les conversations, triées par updated_at décroissant.
    Les fichiers JSON corrompus ou illisibles sont ignorés silencieusement."""
    with _lock:
        if not CONVERSATIONS_DIR.exists():
            return []
        results = []
        for f in CONVERSATIONS_DIR.glob("*.json"):
            if not _is_valid_id(f.stem):
                continue
            try:
                with open(f, encoding="utf-8") as fh:
                    data = json.load(fh)
                results.append({
                    "id": data["id"],
                    "title": data.get("title", TITLE_FALLBACK),
                    "updated_at": data.get("updated_at", 0),
                    "message_count": len(data.get("messages", [])),
                })
            except Exception:
                continue
        results.sort(key=lambda c: c["updated_at"], reverse=True)
        return results


def get_conversation(conv_id: str) -> dict | None:
    """Conversation complète, ou None si absente/invalide/corrompue."""
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        path = _path_for(conv_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def create_conversation(messages: list[dict] | None = None, title: str | None = None) -> dict:
    """Crée une nouvelle conversation et la persiste sur disque."""
    with _lock:
        cleaned = _clean_messages(messages)
        now = time.time()
        data = {
            "id": uuid4().hex,
            "title": (title or "").strip() or _derive_title(cleaned),
            "created_at": now,
            "updated_at": now,
            "messages": cleaned,
        }
        _save(data)
        return data


def update_conversation(
    conv_id: str, messages: list[dict] | None = None, title: str | None = None,
) -> dict | None:
    """Met à jour les messages et/ou le titre d'une conversation existante.
    Renvoie None si l'identifiant est invalide ou la conversation absente."""
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        data = get_conversation(conv_id)
        if data is None:
            return None
        if messages is not None:
            data["messages"] = _clean_messages(messages)
        if title is not None and title.strip():
            data["title"] = title.strip()
        data["updated_at"] = time.time()
        _save(data)
        return data


def delete_conversation(conv_id: str) -> bool:
    """Supprime une conversation. Renvoie False si l'identifiant est invalide
    ou la conversation absente."""
    if not _is_valid_id(conv_id):
        return False
    with _lock:
        path = _path_for(conv_id)
        if not path.exists():
            return False
        path.unlink()
        return True


def delete_all_conversations() -> int:
    """RGPD : supprime toutes les conversations. Renvoie le nombre de fichiers supprimés."""
    with _lock:
        if not CONVERSATIONS_DIR.exists():
            return 0
        removed = 0
        for f in CONVERSATIONS_DIR.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
        return removed


def export_all_conversations() -> list[dict]:
    """RGPD : conversations complètes (pas seulement les métadonnées), pour l'export."""
    with _lock:
        out = []
        for meta in list_conversations():
            data = get_conversation(meta["id"])
            if data is not None:
                out.append(data)
        return out
