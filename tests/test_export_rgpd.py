"""
Export RGPD sans secrets en clair (audit, point 10).

L'export (Paramètres → Confidentialité → Exporter mes données) recopiait les
réglages bruts : le mot de passe de la boîte mail professionnelle, la clé
d'API du moteur de recherche et le jeton Notion se retrouvaient en clair dans
un fichier téléchargé. Ils sont désormais masqués, comme dans GET
/api/settings, et l'export dit lesquels l'ont été.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users

SECRETS = ("MDP-IMAP-SECRET", "BSA-CLE-BRAVE", "secret_jeton_notion")


@pytest.fixture
def client(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    pid = profiles.create_profile("Lycée de l'Olivier")["id"]
    users.create_user("marie", "secret1", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "secret1"}).status_code == 200
    return c


def _configurer_secrets(client):
    r = client.put("/api/settings", json={
        "search_brave_api_key": SECRETS[1],
        "connectors": {
            "imap": {"enabled": True, "host": "imap.ac-exemple.fr",
                     "user": "secretariat@ac-exemple.fr", "password": SECRETS[0]},
            "notion": {"enabled": True, "api_token": SECRETS[2]},
        },
    })
    assert r.status_code == 200


def test_aucun_secret_en_clair_dans_l_export(client):
    _configurer_secrets(client)
    r = client.get("/api/privacy/export")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    # Contrôle sur le fichier BRUT : aucun secret, sous aucune forme.
    for secret in SECRETS:
        assert secret not in r.text
    export = r.json()
    assert export["settings"]["connectors"]["imap"]["password"] == "••••••••"
    assert export["settings"]["connectors"]["notion"]["api_token"] == "••••••••"
    assert export["settings"]["search_brave_api_key"] == "••••••••"
    assert sorted(export["secrets_masques"]) == [
        "connectors.imap.password", "connectors.notion.api_token", "search_brave_api_key"]
    assert "masqués" in export["note"]


def test_les_donnees_non_secretes_restent_exportees(client):
    _configurer_secrets(client)
    client.post("/api/conversations", json={"messages": [
        {"role": "user", "content": "Convocation du conseil de classe"}]})
    export = client.get("/api/privacy/export").json()
    imap = export["settings"]["connectors"]["imap"]
    assert imap["host"] == "imap.ac-exemple.fr"
    assert imap["user"] == "secretariat@ac-exemple.fr"
    assert export["organisation"] == "Lycée de l'Olivier"
    assert export["conversations"][0]["messages"][0]["content"] == \
        "Convocation du conseil de classe"


def test_sans_secret_rien_n_est_annonce_comme_masque(client):
    export = client.get("/api/privacy/export").json()
    assert export["secrets_masques"] == []
    assert "masqués" not in export["note"]


def test_le_secret_reste_utilisable_par_l_application(client):
    # Masquer l'export ne doit pas effacer le vrai mot de passe enregistré.
    _configurer_secrets(client)
    client.get("/api/privacy/export")
    pid = users.get_user_by_username("marie")["profile_id"]
    assert settings.reglages(pid).get()["connectors"]["imap"]["password"] == SECRETS[0]
