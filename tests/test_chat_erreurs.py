"""
Erreurs du moteur d'IA pendant une réponse (audit, point 9).

Quand Ollama était éteint ou que le modèle manquait, l'interface affichait une
bulle vide : le backend relayait l'erreur dans un JSON écrit à la main (illisible
dès que le message contenait un guillemet) ou relayait tel quel le corps
d'erreur d'Ollama, que l'interface ne reconnaissait pas.

Chaque ligne du flux doit être un JSON valide, et toute erreur doit arriver sous
la clé `error`, en français. Ollama est simulé (httpx.MockTransport).
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import conversations, main, profiles, sessions, settings, users

DEMANDE = {"model": "mistral-nemo", "messages": [{"role": "user", "content": "Bonjour"}]}


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
    c.profile_id = pid
    return c


def _faux_ollama(monkeypatch, gestionnaire):
    """Remplace le client HTTP du backend par un Ollama simulé."""
    vrai = httpx.AsyncClient

    class _Client(vrai):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(gestionnaire)
            super().__init__(*a, **k)
    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)


def _evenements(reponse) -> list[dict]:
    """Charges des lignes `data:` du flux SSE, en exigeant du JSON valide."""
    lignes = [ligne[5:].strip() for ligne in reponse.text.splitlines()
              if ligne.startswith("data:")]
    assert lignes, "flux vide"
    return [json.loads(ligne) for ligne in lignes]   # lève si une ligne est invalide


def test_ollama_eteint(client, monkeypatch):
    def _refus(_requete):
        raise httpx.ConnectError("All connection attempts failed")
    _faux_ollama(monkeypatch, _refus)
    evts = _evenements(client.post("/api/chat/stream", json=DEMANDE))
    assert evts == [{"error": main.MESSAGE_OLLAMA_INJOIGNABLE}]


def test_modele_absent_message_lisible_et_json_valide(client, monkeypatch):
    # Le message d'Ollama contient des guillemets : c'est ce qui cassait le
    # JSON écrit à la main.
    def _absent(_requete):
        return httpx.Response(
            404, json={"error": 'model "mistral-nemo" not found, try pulling it first'})
    _faux_ollama(monkeypatch, _absent)
    evts = _evenements(client.post("/api/chat/stream", json=DEMANDE))
    assert len(evts) == 1
    assert "« mistral-nemo » n'est pas installé" in evts[0]["error"]


def test_autre_erreur_d_ollama(client, monkeypatch):
    _faux_ollama(monkeypatch, lambda _r: httpx.Response(500, text='panne "interne"'))
    evts = _evenements(client.post("/api/chat/stream", json=DEMANDE))
    assert evts[0]["error"].startswith("Le moteur d'IA a refusé la demande (erreur 500)")
    assert 'panne "interne"' in evts[0]["error"]


def test_coupure_en_cours_de_reponse(client, monkeypatch):
    def _coupure(_requete):
        raise httpx.ReadError("connexion perdue")
    _faux_ollama(monkeypatch, _coupure)
    evts = _evenements(client.post("/api/chat/stream", json=DEMANDE))
    assert "interrompue" in evts[0]["error"]


def test_reponse_normale_relayee_telle_quelle(client, monkeypatch):
    corps = (json.dumps({"message": {"content": "Bon"}, "done": False}) + "\n"
             + json.dumps({"message": {"content": "jour"}, "done": True,
                           "done_reason": "stop"}) + "\n")
    _faux_ollama(monkeypatch, lambda _r: httpx.Response(200, text=corps))
    evts = _evenements(client.post("/api/chat/stream", json=DEMANDE))
    assert "".join(e["message"]["content"] for e in evts) == "Bonjour"
    assert evts[-1]["done"] is True and "error" not in evts[-1]


def test_l_erreur_d_un_tour_est_conservee_dans_l_historique(client):
    conv = client.post("/api/conversations", json={"messages": [
        {"role": "user", "content": "Bonjour"},
        {"role": "assistant", "content": "", "erreur": main.MESSAGE_OLLAMA_INJOIGNABLE},
    ]}).json()
    relue = client.get(f"/api/conversations/{conv['id']}").json()
    assert relue["messages"][1]["erreur"] == main.MESSAGE_OLLAMA_INJOIGNABLE
    assert relue["messages"][1]["content"] == ""
    # Un message sans erreur n'en reçoit pas une vide.
    assert "erreur" not in conversations._clean_messages([{"role": "user", "content": "x"}])[0]
