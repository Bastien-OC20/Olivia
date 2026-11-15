"""
Conversations et tableaux privés par compte (audit du 15/11/2026, lot 4b).

Avant ce lot, tous les comptes d'une organisation voyaient, modifiaient et
supprimaient les conversations et tableaux de tous les autres. Désormais :
  - un compte ne voit que les siens (404 sinon, comme pour une autre
    organisation), responsable compris ;
  - une conversation ou un tableau d'avant ce lot (sans propriétaire) reste
    commun à l'organisation, et le reste après modification ;
  - l'export RGPD d'un membre ne contient que ses données (et les communes),
    celui du responsable toute l'organisation ;
  - l'effacement (responsable) porte sur toute l'organisation.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import conversations, main, profiles, sessions, settings, tableaux, users, zones


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    pid = profiles.create_profile("Lycée")["id"]
    users.create_user("rachel", "Secret-01", pid)          # responsable
    users.create_user("marc", "Secret-02", pid)            # membre
    users.create_user("lea", "Secret-03", pid)             # membre
    yield {"pid": pid, "rachel": _client("rachel", "Secret-01"),
           "marc": _client("marc", "Secret-02"), "lea": _client("lea", "Secret-03")}
    zones.dossiers_reserves.cache_clear()


def _client(nom, mdp):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"username": nom, "password": mdp})
    assert r.status_code == 200, r.text
    c.user_id = r.json()["user_id"]
    return c


def _conv(client, texte):
    r = client.post("/api/conversations", json={"messages": [{"role": "user", "content": texte}]})
    assert r.status_code == 200
    return r.json()


def _ancienne_conversation(pid):
    """Conversation enregistrée avant ce lot : pas de champ `proprietaire`."""
    conv = conversations.create_conversation(pid, messages=[{"role": "user", "content": "vieux"}])
    assert "proprietaire" not in conv
    return conv


# ---------- Conversations ----------
def test_conversation_privee_au_compte_qui_la_cree(env):
    conv = _conv(env["marc"], "mes notes sur un élève")
    assert conv["proprietaire"] == env["marc"].user_id
    for autre in ("lea", "rachel"):            # membre ET responsable
        c = env[autre]
        assert c.get(f"/api/conversations/{conv['id']}").status_code == 404
        assert c.put(f"/api/conversations/{conv['id']}",
                     json={"title": "volée"}).status_code == 404
        assert c.delete(f"/api/conversations/{conv['id']}").status_code == 404
        assert conv["id"] not in [x["id"] for x in c.get("/api/conversations").json()[
            "conversations"]]
    relue = env["marc"].get(f"/api/conversations/{conv['id']}").json()
    assert relue["title"] == "mes notes sur un élève"
    assert [x["id"] for x in env["marc"].get("/api/conversations").json()[
        "conversations"]] == [conv["id"]]


def test_le_proprietaire_modifie_et_supprime_la_sienne(env):
    conv = _conv(env["marc"], "brouillon")
    r = env["marc"].put(f"/api/conversations/{conv['id']}", json={"title": "Réunion"})
    assert r.status_code == 200 and r.json()["proprietaire"] == env["marc"].user_id
    assert env["marc"].delete(f"/api/conversations/{conv['id']}").status_code == 200


def test_le_client_ne_choisit_pas_le_proprietaire(env):
    """Un `proprietaire` envoyé dans le corps est ignoré."""
    r = env["marc"].post("/api/conversations", json={
        "messages": [], "proprietaire": env["lea"].user_id})
    assert r.json()["proprietaire"] == env["marc"].user_id
    conv = r.json()
    r = env["marc"].put(f"/api/conversations/{conv['id']}", json={
        "title": "x", "proprietaire": env["lea"].user_id})
    assert r.json()["proprietaire"] == env["marc"].user_id
    assert env["lea"].get(f"/api/conversations/{conv['id']}").status_code == 404


def test_ancienne_conversation_reste_commune(env):
    vieille = _ancienne_conversation(env["pid"])
    for nom in ("marc", "lea", "rachel"):
        assert env[nom].get(f"/api/conversations/{vieille['id']}").status_code == 200
    # Modifiée par un membre : elle ne lui est PAS attribuée.
    r = env["marc"].put(f"/api/conversations/{vieille['id']}", json={"title": "Reprise"})
    assert r.status_code == 200 and "proprietaire" not in r.json()
    brut = json.loads((profiles.profile_dir(env["pid"]) / "conversations"
                       / f"{vieille['id']}.json").read_text(encoding="utf-8"))
    assert "proprietaire" not in brut
    assert env["lea"].get(f"/api/conversations/{vieille['id']}").json()["title"] == "Reprise"
    # Et n'importe quel compte peut la supprimer, comme avant.
    assert env["lea"].delete(f"/api/conversations/{vieille['id']}").status_code == 200


# ---------- Tableaux ----------
def test_tableau_prive_au_compte_qui_le_cree(env):
    t = env["marc"].post("/api/tableaux", json={"titre": "Plan"}).json()
    assert t["proprietaire"] == env["marc"].user_id
    for autre in ("lea", "rachel"):
        c = env[autre]
        assert c.get(f"/api/tableaux/{t['id']}").status_code == 404
        assert c.put(f"/api/tableaux/{t['id']}", json={"titre": "x"}).status_code == 404
        assert c.delete(f"/api/tableaux/{t['id']}").status_code == 404
        assert c.get("/api/tableaux").json()["tableaux"] == []
    assert env["marc"].put(f"/api/tableaux/{t['id']}", json={"titre": "Plan 2"}).status_code == 200
    assert [x["id"] for x in env["marc"].get("/api/tableaux").json()["tableaux"]] == [t["id"]]


def test_tableau_de_la_commande_tableau_reste_prive(env):
    """/tableau : l'interface crée le tableau puis l'attache à un message."""
    t = env["marc"].post("/api/tableaux", json={"titre": "Inscription"}).json()
    conv = env["marc"].post("/api/conversations", json={"messages": [
        {"role": "user", "content": "/tableau inscription"},
        {"role": "assistant", "content": "Tableau créé.",
         "tableau": {"id": t["id"], "titre": "Inscription"}},
    ]}).json()
    assert env["marc"].get(f"/api/tableaux/{t['id']}").status_code == 200
    assert env["lea"].get(f"/api/conversations/{conv['id']}").status_code == 404
    assert env["lea"].get(f"/api/tableaux/{t['id']}").status_code == 404


def test_ancien_tableau_reste_commun(env):
    vieux = tableaux.creer(env["pid"], titre="Ancien")
    assert "proprietaire" not in vieux
    r = env["lea"].put(f"/api/tableaux/{vieux['id']}", json={"titre": "Ancien modifié"})
    assert r.status_code == 200
    relu = env["marc"].get(f"/api/tableaux/{vieux['id']}").json()
    assert relu["titre"] == "Ancien modifié" and "proprietaire" not in relu


# ---------- Export et effacement ----------
def test_export_d_un_membre_limite_a_ses_donnees(env):
    a_moi = _conv(env["marc"], "à moi")
    _conv(env["lea"], "à léa")
    _conv(env["rachel"], "à rachel")
    vieille = _ancienne_conversation(env["pid"])
    t_moi = env["marc"].post("/api/tableaux", json={"titre": "moi"}).json()
    env["lea"].post("/api/tableaux", json={"titre": "léa"})
    export = env["marc"].get("/api/privacy/export").json()
    assert export["perimetre"] == "compte"
    assert {c["id"] for c in export["conversations"]} == {a_moi["id"], vieille["id"]}
    assert [t["id"] for t in export["tableaux"]] == [t_moi["id"]]
    assert "comptes" not in export


def test_export_du_responsable_couvre_toute_l_organisation(env):
    ids = {_conv(env[n], n)["id"] for n in ("marc", "lea", "rachel")}
    ids.add(_ancienne_conversation(env["pid"])["id"])
    env["lea"].post("/api/tableaux", json={"titre": "léa"})
    export = env["rachel"].get("/api/privacy/export").json()
    assert export["perimetre"] == "organisation"
    assert {c["id"] for c in export["conversations"]} == ids
    assert len(export["tableaux"]) == 1
    comptes = {c["username"]: c["role"] for c in export["comptes"]}
    assert comptes == {"rachel": "responsable", "marc": "membre", "lea": "membre"}
    assert "password_hash" not in json.dumps(export)


def test_effacement_porte_sur_toute_l_organisation(env):
    _conv(env["marc"], "privée de marc")
    _conv(env["lea"], "privée de léa")
    env["lea"].post("/api/tableaux", json={"titre": "léa"})
    _ancienne_conversation(env["pid"])
    r = env["rachel"].post("/api/privacy/delete")
    assert r.status_code == 200
    assert r.json()["conversations_removed"] == 3
    assert r.json()["tableaux_removed"] == 1
    assert conversations.list_conversations(env["pid"]) == []
