"""
Tableaux blancs (Excalidraw) : /api/tableaux.

Un tableau appartient à une organisation, comme une conversation : un
identifiant deviné ne donne accès à rien hors de la sienne. La scène est
vérifiée (forme, taille), et les tableaux suivent l'export et l'effacement RGPD.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, tableaux, users

SCENE = {
    "type": "excalidraw", "version": 2, "source": "oliv-ia",
    "elements": [{"id": "a1", "type": "rectangle", "x": 0, "y": 0, "isDeleted": False},
                 {"id": "a2", "type": "text", "text": "Conseil de classe", "isDeleted": False},
                 {"id": "a3", "type": "ellipse", "isDeleted": True}],
    "appState": {"viewBackgroundColor": "#ffffff"},
    "files": {},
}


def _client(nom: str, mot_de_passe: str, profil: str) -> TestClient:
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"username": nom, "password": mot_de_passe})
    assert r.status_code == 200
    c.profile_id = profil
    return c


@pytest.fixture
def deux_orgs(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    a = profiles.create_profile("Lycée A")["id"]
    b = profiles.create_profile("Mairie B")["id"]
    users.create_user("alice", "Secret-01", a)
    users.create_user("bruno", "Secret-02", b)
    return _client("alice", "Secret-01", a), _client("bruno", "Secret-02", b)


def test_session_requise():
    assert TestClient(main.app).get("/api/tableaux").status_code == 401


def test_creer_lire_modifier_supprimer(deux_orgs):
    alice, _ = deux_orgs
    cree = alice.post("/api/tableaux", json={"titre": "  Plan   de la cour  "}).json()
    assert cree["titre"] == "Plan de la cour"
    assert cree["scene"]["elements"] == []

    r = alice.put(f"/api/tableaux/{cree['id']}", json={"scene": SCENE})
    assert r.status_code == 200
    relu = alice.get(f"/api/tableaux/{cree['id']}").json()
    assert relu["scene"] == SCENE and relu["titre"] == "Plan de la cour"

    liste = alice.get("/api/tableaux").json()["tableaux"]
    assert [(t["id"], t["elements"]) for t in liste] == [(cree["id"], 2)]  # supprimés exclus

    assert alice.put(f"/api/tableaux/{cree['id']}", json={"titre": ""}).json()["titre"] \
        == tableaux.TITRE_PAR_DEFAUT
    assert alice.delete(f"/api/tableaux/{cree['id']}").status_code == 200
    assert alice.get(f"/api/tableaux/{cree['id']}").status_code == 404


def test_cloisonnement_entre_organisations(deux_orgs):
    alice, bruno = deux_orgs
    tid = alice.post("/api/tableaux", json={"titre": "Privé", "scene": SCENE}).json()["id"]
    assert bruno.get(f"/api/tableaux/{tid}").status_code == 404
    assert bruno.put(f"/api/tableaux/{tid}", json={"titre": "Piraté"}).status_code == 404
    assert bruno.delete(f"/api/tableaux/{tid}").status_code == 404
    assert bruno.get("/api/tableaux").json()["tableaux"] == []
    assert alice.get(f"/api/tableaux/{tid}").json()["titre"] == "Privé"


@pytest.mark.parametrize("tid", ["../../registry", "abc", "0" * 31 + "Z"])
def test_identifiant_invalide(deux_orgs, tid):
    alice, _ = deux_orgs
    assert alice.get(f"/api/tableaux/{tid}").status_code == 404


@pytest.mark.parametrize("scene", [
    "pas un objet",
    {"elements": "pas une liste"},
    {"elements": [], "files": []},
    {"elements": [], "appState": "x"},
])
def test_scene_mal_formee_refusee(deux_orgs, scene):
    alice, _ = deux_orgs
    assert alice.post("/api/tableaux", json={"scene": scene}).status_code == 400
    tid = alice.post("/api/tableaux", json={}).json()["id"]
    assert alice.put(f"/api/tableaux/{tid}", json={"scene": scene}).status_code == 400


def test_tableau_trop_volumineux(deux_orgs, monkeypatch):
    alice, _ = deux_orgs
    monkeypatch.setattr(tableaux, "MAX_OCTETS", 1000)
    tid = alice.post("/api/tableaux", json={}).json()["id"]
    lourd = dict(SCENE, files={"img": {"dataURL": "data:image/png;base64," + "A" * 2000}})
    r = alice.put(f"/api/tableaux/{tid}", json={"scene": lourd})
    assert r.status_code == 400 and "volumineux" in r.json()["detail"]
    # Le tableau existant n'a pas été écrasé par la sauvegarde refusée.
    assert alice.get(f"/api/tableaux/{tid}").json()["scene"]["elements"] == []


def test_rgpd_export_et_effacement(deux_orgs):
    alice, bruno = deux_orgs
    alice.post("/api/tableaux", json={"titre": "À exporter", "scene": SCENE})
    bruno.post("/api/tableaux", json={"titre": "De Bruno"})

    export = alice.get("/api/privacy/export").json()
    assert [t["titre"] for t in export["tableaux"]] == ["À exporter"]
    assert export["tableaux"][0]["scene"] == SCENE

    r = alice.post("/api/privacy/delete").json()
    assert r["tableaux_removed"] == 1
    assert alice.get("/api/tableaux").json()["tableaux"] == []
    # L'effacement d'une organisation ne touche pas les tableaux de l'autre.
    assert [t["titre"] for t in bruno.get("/api/tableaux").json()["tableaux"]] == ["De Bruno"]
