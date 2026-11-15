"""
Sessions : fichier abîmé (audit, point 8) et jetons non stockés en clair.

Tout se passe dans un dossier temporaire : rien n'est écrit dans
backend/profiles/ du dépôt.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users, zones

IDENTIFIANTS = {"username": "alice", "password": "PassA-001"}


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    pa = profiles.create_profile("Org A")
    users.create_user("alice", "PassA-001", pa["id"])
    yield {"pa": pa}
    zones.dossiers_reserves.cache_clear()


def _connecte():
    client = TestClient(main.app)
    assert client.post("/api/auth/login", json=IDENTIFIANTS).status_code == 200
    return client


@pytest.mark.parametrize("contenu", ["", "{pas du json", "[]", '{"sessions": []}'])
def test_sessions_json_abime_ne_bloque_ni_la_session_ni_la_connexion(env, contenu):
    """Un sessions.json vide ou invalide donnait une erreur 500 sur chaque requête."""
    client = _connecte()
    sessions.SESSIONS_PATH.write_text(contenu, encoding="utf-8")
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/login", json=IDENTIFIANTS).status_code == 200
    assert client.get("/api/auth/me").status_code == 200


def test_le_jeton_du_cookie_n_est_pas_dans_sessions_json(env):
    client = _connecte()
    jeton = client.cookies.get(main.COOKIE_SESSION)
    assert jeton
    brut = sessions.SESSIONS_PATH.read_text(encoding="utf-8")
    assert jeton not in brut
    assert len(json.loads(brut)["sessions"]) == 1


def test_deconnexion_ferme_la_session(env):
    client = _connecte()
    assert client.get("/api/auth/me").status_code == 200
    assert client.post("/api/auth/logout").status_code in (200, 204)
    assert client.get("/api/auth/me").status_code == 401
    assert json.loads(sessions.SESSIONS_PATH.read_text(encoding="utf-8"))["sessions"] == {}


def test_session_expiree_refusee_et_purgee(env):
    jeton = sessions.create_session("u" * 32, env["pa"]["id"], ttl_seconds=-1)
    assert sessions.resolve_session(jeton) is None
    assert json.loads(sessions.SESSIONS_PATH.read_text(encoding="utf-8"))["sessions"] == {}


def test_ancienne_session_a_cle_en_clair_devient_introuvable(env):
    sessions.SESSIONS_PATH.parent.mkdir(parents=True, exist_ok=True)
    sessions.SESSIONS_PATH.write_text(json.dumps({"sessions": {
        "jeton-en-clair": {"user_id": "u", "profile_id": "p", "expires_at": 9e12}}}),
        encoding="utf-8")
    assert sessions.resolve_session("jeton-en-clair") is None


def test_creation_resolution_suppression(env):
    jeton = sessions.create_session("u" * 32, env["pa"]["id"])
    assert sessions.resolve_session(jeton)["profile_id"] == env["pa"]["id"]
    assert sessions.delete_session(jeton) is True
    assert sessions.delete_session(jeton) is False
    assert sessions.resolve_session(jeton) is None
