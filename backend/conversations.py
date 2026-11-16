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

CONVERSATIONS PRIVÉES PAR COMPTE (lot 4) : une conversation créée par un compte
porte son `proprietaire` (user_id) ; seul ce compte la voit, la modifie ou la
supprime — pas même le responsable de l'organisation. Une conversation d'un
autre compte est « absente » (404), exactement comme celle d'une autre
organisation. Une conversation enregistrée AVANT les comptes privés n'a pas de
propriétaire : elle reste commune à tous les comptes de l'organisation, et une
modification ne lui en attribue pas (sinon le premier qui l'ouvre la
retirerait aux autres).

Le paramètre `pour_compte` (user_id de la session) applique ce filtre ; None
donne la vue d'ORGANISATION, réservée à l'export RGPD du responsable et à
l'effacement (main.privacy_export, privacy_delete). Une conversation dont le
compte a été supprimé reste sur le disque, invisible de tous, jusqu'à
l'effacement RGPD de l'organisation (voir users.supprimer_compte).
"""
import json
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

from . import profiles

TITLE_MAX_LEN = 60
TITLE_FALLBACK = "Nouvelle conversation"
# Même plafond que le titre d'un tableau blanc (tableaux.TITRE_MAX).
TABLEAU_TITRE_MAX = 80

# Documents joints rattachés à une conversation : la RÉFÉRENCE seulement (chemin
# virtuel `rN/...` et nom affiché), jamais le contenu, qui est relu à la
# réouverture. Bornes alignées sur l'interface (conversationDocs.js, DOC_MAX).
DOCUMENTS_MAX = 10
DOCUMENT_CHEMIN_MAX = 1000
DOCUMENT_NOM_MAX = 255

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
            content = m.get("content")
            # Le corps de la requête vient du client : un `content` qui n'est pas
            # une chaîne (liste, nombre) faisait planter la création en erreur 500.
            if not isinstance(content, str):
                continue
            content = content.strip()
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
        # Erreur du moteur d'IA sur ce tour (Ollama éteint, modèle absent…) :
        # conservée pour qu'une conversation rouverte dise pourquoi la réponse
        # manque, et gardée HORS de `content`, qui est renvoyé au modèle.
        if m.get("erreur"):
            entry["erreur"] = m["erreur"]
        # Tableau blanc créé par /tableau : le bouton « Ouvrir le tableau » doit
        # survivre à un rechargement. L'identifiant sert ensuite à une URL côté
        # interface : on n'accepte que la forme d'un vrai identifiant.
        tableau = m.get("tableau")
        if (isinstance(tableau, dict) and isinstance(tableau.get("id"), str)
                and _is_valid_id(tableau["id"]) and isinstance(tableau.get("titre"), str)):
            entry["tableau"] = {"id": tableau["id"], "titre": tableau["titre"][:TABLEAU_TITRE_MAX]}
        # Boucle d'outils : étapes de consultation et document Word proposé,
        # réaffichés à la réouverture. Venus du client : bornés champ par champ.
        etapes = _clean_etapes(m.get("etapes"))
        if etapes:
            entry["etapes"] = etapes
        proposition = _clean_proposition(m.get("proposition"))
        if proposition:
            entry["proposition"] = proposition
        cleaned.append(entry)
    return cleaned


# Bornes des champs de la boucle d'outils (voir backend/outils.py, mêmes ordres
# de grandeur) : une conversation enregistrée ne doit pas pouvoir grossir sans
# limite par ces champs, que l'interface renvoie tels qu'elle les a reçus.
ETAPES_MAX = 20
ETAPE_ID_MAX = 50
ETAPE_TEXTE_MAX = 200
ETATS_ETAPE = {"en_cours", "fini", "echec"}
PROPOSITION_CHAMP_MAX = 200
PROPOSITION_TEXTE_MAX = 8000


def _clean_etapes(etapes) -> list[dict]:
    """Étapes d'outils `[{id, outil, etat, libelle, resume, documents}]`.

    Une étape sans identifiant exploitable (entier, ou texte court) ou d'état
    inconnu est ignorée ; un champ texte d'un autre type est omis. Jamais
    d'erreur : l'enregistrement de la conversation ne doit pas échouer pour ça.
    """
    if not isinstance(etapes, list):
        return []
    sortie: list[dict] = []
    for e in etapes:
        if len(sortie) >= ETAPES_MAX:
            break
        if not isinstance(e, dict):
            continue
        ident = e.get("id")
        if isinstance(ident, bool) or not (
                isinstance(ident, int) or (isinstance(ident, str) and ident
                                           and len(ident) <= ETAPE_ID_MAX)):
            continue
        if e.get("etat") not in ETATS_ETAPE:
            continue
        propre = {"id": ident, "etat": e["etat"]}
        for champ in ("outil", "libelle", "resume"):
            if isinstance(e.get(champ), str):
                propre[champ] = e[champ][:ETAPE_TEXTE_MAX]
        if "documents" in e:
            propre["documents"] = _clean_documents(e["documents"])
        sortie.append(propre)
    return sortie


def _clean_proposition(proposition) -> dict | None:
    """Document Word proposé par le modèle (jamais créé par le serveur), ou None
    s'il est mal formé. Champs texte seulement, bornés."""
    if not isinstance(proposition, dict) or proposition.get("type") != "document_word":
        return None

    def texte(champ: str, maximum: int) -> str:
        valeur = proposition.get(champ)
        return valeur[:maximum] if isinstance(valeur, str) else ""

    return {
        "type": "document_word",
        "type_document": texte("type_document", PROPOSITION_CHAMP_MAX),
        "titre": texte("titre", PROPOSITION_CHAMP_MAX),
        "objet": texte("objet", PROPOSITION_CHAMP_MAX),
        "destinataire": texte("destinataire", PROPOSITION_CHAMP_MAX),
        "texte": texte("texte", PROPOSITION_TEXTE_MAX),
    }


def _clean_documents(documents) -> list[dict]:
    """Normalise la liste des documents joints : `[{"path", "name"}]`.

    Tout élément invalide est ignoré (jamais d'erreur : un enregistrement de
    conversation ne doit pas échouer pour une pièce jointe mal formée). Doublons
    de chemin écartés, nom vide remplacé par le chemin, comme dans l'interface.
    Seuls `path` et `name` sont gardés : un champ `content` envoyé par erreur
    n'est jamais écrit sur disque.
    """
    if not isinstance(documents, list):
        return []
    sortie: list[dict] = []
    vus: set[str] = set()
    for d in documents:
        if not isinstance(d, dict):
            continue
        chemin = d.get("path")
        nom = d.get("name")
        if not isinstance(chemin, str):
            continue
        chemin = chemin.strip()
        if not chemin or len(chemin) > DOCUMENT_CHEMIN_MAX or chemin in vus:
            continue
        nom = nom.strip() if isinstance(nom, str) else ""
        nom = nom or chemin.rsplit("/", 1)[-1] or chemin
        if len(nom) > DOCUMENT_NOM_MAX:
            nom = nom[:DOCUMENT_NOM_MAX]
        vus.add(chemin)
        sortie.append({"path": chemin, "name": nom})
        if len(sortie) >= DOCUMENTS_MAX:
            break
    return sortie


def _visible(data: dict, pour_compte: str | None) -> bool:
    """La conversation est-elle visible de ce compte ? (voir la docstring du module)"""
    if pour_compte is None:
        return True
    proprietaire = data.get("proprietaire") if isinstance(data, dict) else None
    return not proprietaire or proprietaire == pour_compte


def _save(profile_id: str, data: dict):
    dossier = _dir_for(profile_id)
    dossier.mkdir(parents=True, exist_ok=True)
    path = dossier / f"{data['id']}.json"
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


def list_conversations(profile_id: str, pour_compte: str | None = None) -> list[dict]:
    """Métadonnées des conversations de CETTE organisation visibles de
    `pour_compte`, triées par updated_at décroissant. Les fichiers JSON
    corrompus ou illisibles sont ignorés silencieusement."""
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
                if not _visible(data, pour_compte):
                    continue
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


def get_conversation(profile_id: str, conv_id: str,
                     pour_compte: str | None = None) -> dict | None:
    """Conversation complète, ou None si absente/invalide/corrompue.

    « Absente » couvre aussi la conversation d'une AUTRE organisation (son
    fichier n'existe pas dans ce dossier) et celle d'un AUTRE compte de la même
    organisation : un identifiant deviné répond 404 exactement comme un
    identifiant inventé.
    """
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        path = _path_for(profile_id, conv_id)
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
        if not _visible(data, pour_compte):
            return None
        # Conversation enregistrée avant les documents joints : liste vide, pour
        # que l'interface n'ait pas à distinguer les deux formes.
        if isinstance(data, dict) and not isinstance(data.get("documents"), list):
            data["documents"] = []
        return data


def create_conversation(profile_id: str, messages: list[dict] | None = None,
                        title: str | None = None, documents: list | None = None,
                        proprietaire: str | None = None) -> dict:
    """Crée une nouvelle conversation dans cette organisation et la persiste.

    `documents` : documents joints (voir `_clean_documents`).
    `proprietaire` : user_id du compte qui la crée, seul à la voir ensuite."""
    with _lock:
        cleaned = _clean_messages(messages)
        now = time.time()
        titre = title.strip() if isinstance(title, str) else ""
        data = {
            "id": uuid4().hex,
            "title": titre or _derive_title(cleaned),
            "created_at": now,
            "updated_at": now,
            "messages": cleaned,
            "documents": _clean_documents(documents),
        }
        if proprietaire:
            data["proprietaire"] = proprietaire
        _save(profile_id, data)
        return data


def update_conversation(
    profile_id: str, conv_id: str, messages: list[dict] | None = None,
    title: str | None = None, documents: list | None = None,
    pour_compte: str | None = None,
) -> dict | None:
    """Met à jour les messages, le titre et/ou les documents joints d'une
    conversation existante. `documents` absent (None) les laisse inchangés, `[]`
    les retire tous. Renvoie None si l'identifiant est invalide ou la
    conversation absente de cette organisation ou invisible de `pour_compte`.
    Le propriétaire n'est jamais modifié, ni ajouté à une ancienne conversation
    commune."""
    if not _is_valid_id(conv_id):
        return None
    with _lock:
        data = get_conversation(profile_id, conv_id, pour_compte)
        if data is None:
            return None
        if messages is not None:
            data["messages"] = _clean_messages(messages)
        if isinstance(title, str) and title.strip():
            data["title"] = title.strip()
        if documents is not None:
            data["documents"] = _clean_documents(documents)
        data["updated_at"] = time.time()
        _save(profile_id, data)
        return data


def delete_conversation(profile_id: str, conv_id: str,
                        pour_compte: str | None = None) -> bool:
    """Supprime une conversation de cette organisation. Renvoie False si
    l'identifiant est invalide ou la conversation absente (ou invisible de
    `pour_compte`). Une conversation commune (sans propriétaire) peut être
    supprimée par n'importe quel compte de l'organisation, comme avant."""
    if not _is_valid_id(conv_id):
        return False
    with _lock:
        path = _path_for(profile_id, conv_id)
        if not path.exists():
            return False
        if pour_compte is not None:
            try:
                with open(path, encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                # Illisible : son propriétaire est inconnu, on ne la supprime pas.
                return False
            if not _visible(data, pour_compte):
                return False
        path.unlink()
        return True


def delete_all_conversations(profile_id: str) -> int:
    """RGPD : supprime les conversations de CETTE organisation seulement.
    Renvoie le nombre de conversations supprimées.

    Les `.tmp` aussi : un plantage pendant une écriture (`_save` : .tmp puis
    remplacement) laisse une copie complète d'une conversation, qui survivait à
    l'effacement. Rien d'autre n'est touché, et seuls les `.json` sont comptés."""
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
        for f in dossier.glob("*.tmp"):
            try:
                f.unlink()
            except OSError:
                pass
        return removed


def export_all_conversations(profile_id: str, pour_compte: str | None = None) -> list[dict]:
    """RGPD : conversations complètes de CETTE organisation (pas seulement les
    métadonnées), pour l'export. `pour_compte` : seulement celles que ce compte
    voit (export d'un membre) ; None : toutes (export du responsable)."""
    with _lock:
        out = []
        for meta in list_conversations(profile_id, pour_compte):
            data = get_conversation(profile_id, meta["id"], pour_compte)
            if data is not None:
                out.append(data)
        return out
