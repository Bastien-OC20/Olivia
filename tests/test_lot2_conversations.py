"""
Documents joints rattachés à leur conversation (audit du 15/11/2026, lot 2,
point 19 ; décision de Bastien : chaque conversation garde SES documents).

Contrat partagé avec l'interface (frontend/src/conversationDocs.js) : un champ
`documents`, liste de `{"path", "name"}` (chemin virtuel `rN/...` et nom
affiché), 10 au plus, jamais le contenu du document. Dans PUT, `documents`
absent laisse la liste inchangée et `[]` la vide.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import conversations, main, profiles, sessions, settings, users, zones


@pytest.fixture
def client(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", "Secret-01", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    c.pid = pid
    yield c
    zones.dossiers_reserves.cache_clear()


DOCS = [{"path": "r0/convocations/conseil.docx", "name": "conseil.docx"},
        {"path": "r1/eleves.xlsx", "name": "eleves.xlsx"}]


def test_documents_crees_puis_relus(client):
    r = client.post("/api/conversations", json={"messages": [], "documents": DOCS})
    assert r.status_code == 200
    assert r.json()["documents"] == DOCS
    conv = client.get(f"/api/conversations/{r.json()['id']}").json()
    assert conv["documents"] == DOCS


def test_chaque_conversation_garde_ses_documents(client):
    a = client.post("/api/conversations", json={"documents": DOCS[:1]}).json()["id"]
    b = client.post("/api/conversations", json={"documents": DOCS[1:]}).json()["id"]
    assert client.get(f"/api/conversations/{a}").json()["documents"] == DOCS[:1]
    assert client.get(f"/api/conversations/{b}").json()["documents"] == DOCS[1:]


def test_put_sans_documents_les_laisse_inchanges(client):
    conv_id = client.post("/api/conversations", json={"documents": DOCS}).json()["id"]
    r = client.put(f"/api/conversations/{conv_id}",
                   json={"messages": [{"role": "user", "content": "Bonjour"}]})
    assert r.json()["documents"] == DOCS


def test_put_liste_vide_les_retire(client):
    conv_id = client.post("/api/conversations", json={"documents": DOCS}).json()["id"]
    r = client.put(f"/api/conversations/{conv_id}", json={"documents": []})
    assert r.json()["documents"] == []
    assert client.get(f"/api/conversations/{conv_id}").json()["documents"] == []


def test_put_remplace_la_liste(client):
    conv_id = client.post("/api/conversations", json={"documents": DOCS}).json()["id"]
    r = client.put(f"/api/conversations/{conv_id}", json={"documents": DOCS[1:]})
    assert r.json()["documents"] == DOCS[1:]


def test_elements_invalides_ignores_et_contenu_jamais_stocke(client):
    brut = [
        "r0/texte-seul.txt",                                    # pas un objet
        {"name": "sans-chemin.docx"},                           # pas de chemin
        {"path": 12, "name": "chemin non texte"},
        {"path": "   ", "name": "chemin vide"},
        {"path": "r0/" + "x" * 1000, "name": "chemin trop long"},
        {"path": "r0/note.txt", "name": "note.txt", "content": "DONNÉE PERSONNELLE"},
        {"path": "r0/note.txt", "name": "doublon"},
        {"path": "r0/sans-nom.pdf"},
        {"path": "r0/long.pdf", "name": "n" * 300},
    ]
    r = client.post("/api/conversations", json={"documents": brut})
    assert r.json()["documents"] == [
        {"path": "r0/note.txt", "name": "note.txt"},
        {"path": "r0/sans-nom.pdf", "name": "sans-nom.pdf"},
        {"path": "r0/long.pdf", "name": "n" * 255},
    ]
    fichier = profiles.profile_dir(client.pid) / conversations.SOUS_DOSSIER \
        / f"{r.json()['id']}.json"
    assert "DONNÉE PERSONNELLE" not in fichier.read_text(encoding="utf-8")


@pytest.mark.parametrize("valeur", ["r0/a.txt", {"path": "r0/a.txt"}, 3, None])
def test_documents_mal_formes_donnent_une_liste_vide(client, valeur):
    r = client.post("/api/conversations", json={"documents": valeur})
    assert r.status_code == 200
    assert r.json()["documents"] == []


def test_au_plus_dix_documents(client):
    beaucoup = [{"path": f"r0/doc{i}.pdf", "name": f"doc{i}.pdf"} for i in range(15)]
    r = client.post("/api/conversations", json={"documents": beaucoup})
    assert r.json()["documents"] == beaucoup[:conversations.DOCUMENTS_MAX]
    assert conversations.DOCUMENTS_MAX == 10


def test_ancienne_conversation_sans_champ(client):
    conv_id = client.post("/api/conversations", json={"messages": []}).json()["id"]
    fichier = profiles.profile_dir(client.pid) / conversations.SOUS_DOSSIER / f"{conv_id}.json"
    donnees = json.loads(fichier.read_text(encoding="utf-8"))
    del donnees["documents"]
    fichier.write_text(json.dumps(donnees), encoding="utf-8")
    assert client.get(f"/api/conversations/{conv_id}").json()["documents"] == []


def test_liste_des_conversations_sans_documents(client):
    client.post("/api/conversations", json={"documents": DOCS})
    meta = client.get("/api/conversations").json()["conversations"][0]
    assert "documents" not in meta
