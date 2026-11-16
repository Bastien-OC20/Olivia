"""
Fenêtre de contexte envoyée à Ollama (`num_ctx`).

Sans elle, Ollama appliquait sa valeur par défaut (4096 jetons) et coupait EN
SILENCE le début d'une conversation plus longue, alors que l'interface admet
jusqu'à 24 000 caractères de documents joints. Chaque requête de conversation
doit donc porter le `num_ctx` du périphérique choisi. Ollama est simulé.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users

DEMANDE = {"model": "mistral-nemo", "messages": [{"role": "user", "content": "Bonjour"}]}
REPONSE = json.dumps({"message": {"content": "Bonjour"}, "done": True,
                      "done_reason": "stop"}) + "\n"


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


def _ollama_espion(monkeypatch) -> list[dict]:
    """Ollama simulé qui garde le corps de chaque requête reçue."""
    recues: list[dict] = []
    vrai = httpx.AsyncClient

    def _gestionnaire(requete):
        recues.append(json.loads(requete.content))
        return httpx.Response(200, text=REPONSE)

    class _Client(vrai):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(_gestionnaire)
            super().__init__(*a, **k)
    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return recues


@pytest.mark.parametrize("peripherique", ["gpu", "cpu", "leger"])
def test_le_chat_fixe_la_fenetre_de_contexte_du_peripherique(
        client, monkeypatch, peripherique):
    assert client.put("/api/settings",
                      json={"compute_device": peripherique}).status_code == 200
    recues = _ollama_espion(monkeypatch)
    client.post("/api/chat/stream", json=DEMANDE)
    client.post("/api/chat", json=DEMANDE)
    assert len(recues) == 2
    for corps in recues:
        assert corps["options"]["num_ctx"] == settings.NUM_CTX[peripherique]


def test_la_fenetre_depasse_le_defaut_d_ollama():
    # 4096 est le défaut relevé d'Ollama : rester au-dessous ou à égalité ne
    # corrigerait rien. gemma2:2b plafonne à 8192 : ne pas le dépasser en CPU.
    assert all(v > 4096 for v in settings.NUM_CTX.values())
    assert settings.NUM_CTX["cpu"] <= 8192
