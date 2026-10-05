"""
Commande /tableau : le message d'Olivia qui a créé un tableau blanc garde un
champ `tableau` ({id, titre}) dans l'historique, pour que le bouton « Ouvrir le
tableau » survive à un rechargement. Le champ est filtré à l'enregistrement : son
identifiant sert ensuite à une adresse /api/tableaux/<id> côté interface.
"""
import pytest
from fastapi.testclient import TestClient

from backend import conversations, main, profiles, sessions, settings, users

ID_VALIDE = "0123456789abcdef0123456789abcdef"


def _message(tableau):
    return {"role": "assistant", "content": "Voilà.", "tableau": tableau}


def test_le_tableau_d_un_message_est_conserve():
    nettoye = conversations._clean_messages(
        [_message({"id": ID_VALIDE, "titre": "Inscription d'un élève"})])
    assert nettoye[0]["tableau"] == {"id": ID_VALIDE, "titre": "Inscription d'un élève"}


def test_le_titre_du_tableau_est_tronque():
    nettoye = conversations._clean_messages([_message({"id": ID_VALIDE, "titre": "x" * 200})])
    assert nettoye[0]["tableau"]["titre"] == "x" * 80


def test_le_champ_tableau_inutile_est_ignore():
    mauvais = [
        {"id": "../../secret", "titre": "Piégé"},       # identifiant invalide
        {"id": ID_VALIDE.upper(), "titre": "Majuscules"},
        {"id": 12345, "titre": "Pas une chaîne"},
        {"id": ID_VALIDE, "titre": 42},                  # titre qui n'est pas une chaîne
        {"id": ID_VALIDE},                               # titre absent
        {"titre": "Sans identifiant"},
        "pas un dictionnaire", ["id", ID_VALIDE], 7, None, {},
    ]
    for tableau in mauvais:
        assert "tableau" not in conversations._clean_messages([_message(tableau)])[0], tableau


def test_un_message_sans_tableau_n_en_recoit_pas():
    assert "tableau" not in conversations._clean_messages(
        [{"role": "assistant", "content": "Bonjour"}])[0]


@pytest.fixture
def client(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", "Secret-01", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    return c


def test_le_tableau_survit_a_l_enregistrement_et_a_la_relecture(client):
    conv = client.post("/api/conversations", json={"messages": [
        {"role": "user", "content": "/tableau étapes de l'inscription"},
        {"role": "assistant", "content": "J'ai créé le tableau.",
         "tableau": {"id": ID_VALIDE, "titre": "Inscription"}},
    ]}).json()
    relue = client.get(f"/api/conversations/{conv['id']}").json()
    assert relue["messages"][1]["tableau"] == {"id": ID_VALIDE, "titre": "Inscription"}
    assert "tableau" not in relue["messages"][0]
