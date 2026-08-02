"""
Persistance des conversations, CLOISONNÉE PAR ORGANISATION :
backend/profiles/<profile_id>/conversations/<id>.json (un fichier par conversation).

Le dossier est créé automatiquement au premier accès. Toutes les écritures sont
mutexées et atomic-write sur disque (fichier .tmp puis remplacement), comme pour
settings.py.

Toutes les fonctions publiques prennent le `profile_id` en PREMIER paramètre,
résolu par `main.get_current_profile()` — jamais fourni par le client. Le
cloisonnement par dossier corrige au passage un problème latent du mode
mono-organisation : un `conv_id` seul (uuid4 hex) suffisait à lire, écrire ou
supprimer n'importe quelle conversation, aucun champ ne disant à qui elle
appartenait. Désormais un identifiant deviné ne désigne rien hors du dossier du
profil appelant.
"""
import json
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

from . import profiles

TITLE_MAX_LEN = 60
TITLE_FALLBACK = "Nouvelle conversation"

SOUS_DOSSIER = "conversations"
_lock = RLock()

# Un identifiant de conversation a exactement la même forme qu'un identifiant de
# profil (uuid4().hex) : on réutilise la validation de profiles.py plutôt que d'en
# entretenir une seconde copie ici — c'est le même filtre anti-path-traversal.
_is_valid_id = profiles.is_valid_id


def _dir_for(profile_id: str) -> Path:
    """Dossier des conversations d'une organisation (valide l'identifiant)."""
    return profiles.profile_dir(profile_id) / SOUS_DOSSIER


def _path_for(profile_id: str, conv_id: str) -> Path:
    return _dir_for(profile_id) / f"{conv_id}.json"


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


def _save(profile_id: str, data: dict):
    dossier = _dir_for(profile_id)
    dossier.mkdir(parents=True, exist_ok=True)
    path = dossier / f"{data['id']}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def list_conversations(profile_id: str) -> list[dict]:
    """Métadonnées des conversations de CETTE organisation, triées par updated_at
    décroissant. Les fichiers JSON corrompus ou illisibles sont ignorés
    silencieusement."""
    dossier = _dir_for(profile_id)
    with _lock:
        if not dossier.exists():
            return []
        results = []
        for f in dossier.glob("*.json"):
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


def get_conversation(profile_id: str, conv_id: str) -> dict | None:
    """Conversation complète, ou None si absente/invalide/corrompue.

    « Absente » couvre aussi la conversation d'une AUTRE organisation : son
    fichier n'existe pas dans ce dossier, donc un identifiant deviné répond 404
    exactement comme un identifiant inventé.
    """
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        path = _path_for(profile_id, conv_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None


def create_conversation(profile_id: str, messages: list[dict] | None = None,
                        title: str | None = None) -> dict:
    """Crée une nouvelle conversation dans cette organisation et la persiste."""
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
        _save(profile_id, data)
        return data


def update_conversation(
    profile_id: str, conv_id: str, messages: list[dict] | None = None,
    title: str | None = None,
) -> dict | None:
    """Met à jour les messages et/ou le titre d'une conversation existante.
    Renvoie None si l'identifiant est invalide ou la conversation absente de
    cette organisation."""
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        data = get_conversation(profile_id, conv_id)
        if data is None:
            return None
        if messages is not None:
            data["messages"] = _clean_messages(messages)
        if title is not None and title.strip():
            data["title"] = title.strip()
        data["updated_at"] = time.time()
        _save(profile_id, data)
        return data


def delete_conversation(profile_id: str, conv_id: str) -> bool:
    """Supprime une conversation de cette organisation. Renvoie False si
    l'identifiant est invalide ou la conversation absente."""
    if not _is_valid_id(conv_id):
        return False
    with _lock:
        path = _path_for(profile_id, conv_id)
        if not path.exists():
            return False
        path.unlink()
        return True


def delete_all_conversations(profile_id: str) -> int:
    """RGPD : supprime les conversations de CETTE organisation seulement.
    Renvoie le nombre de fichiers supprimés."""
    dossier = _dir_for(profile_id)
    with _lock:
        if not dossier.exists():
            return 0
        removed = 0
        for f in dossier.glob("*.json"):
            try:
                f.unlink()
                removed += 1
            except Exception:
                pass
        return removed


def export_all_conversations(profile_id: str) -> list[dict]:
    """RGPD : conversations complètes de CETTE organisation (pas seulement les
    métadonnées), pour l'export."""
    with _lock:
        out = []
        for meta in list_conversations(profile_id):
            data = get_conversation(profile_id, meta["id"])
            if data is not None:
                out.append(data)
        return out
