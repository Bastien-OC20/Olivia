"""
État du moteur d'IA (GET /api/moteur/etat).

Un poste neuf (application de bureau installée, Ollama absent ou modèles non
tirés) ne découvrait la panne qu'au premier message, qui échouait. La route
dit, avant tout échange, si Ollama répond et quels modèles manquent ; le
panneau « Olivia n'est pas encore prête » de l'interface s'en sert pour guider.
Ollama est simulé (httpx.MockTransport).
"""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend import main, moteur, profiles, sessions, settings, users

GPU = settings.DEVICE_MODELS["gpu"][0]
CPU = settings.DEVICE_MODELS["cpu"][0]


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
    vrai = httpx.AsyncClient

    class _Client(vrai):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(gestionnaire)
            super().__init__(*a, **k)
    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)


def _installes(*noms):
    def _tags(requete):
        assert requete.url.path == "/api/tags"
        return httpx.Response(200, json={"models": [{"name": n} for n in noms]})
    return _tags


def _par_nom(etat):
    return {m["nom"]: m for m in etat["modeles"]}


def test_session_requise():
    assert TestClient(main.app).get("/api/moteur/etat").status_code == 401


def test_ollama_absent_ne_leve_pas(client, monkeypatch):
    def _refus(_requete):
        raise httpx.ConnectError("All connection attempts failed")
    _faux_ollama(monkeypatch, _refus)
    r = client.get("/api/moteur/etat")
    assert r.status_code == 200
    etat = r.json()
    assert etat["joignable"] is False and etat["pret"] is False
    # On ne sait rien des modèles : on ne prétend pas qu'ils manquent.
    assert all(m["installe"] is None for m in etat["modeles"])


def test_modeles_manquants(client, monkeypatch):
    settings.reglages(client.profile_id).update({"compute_device": "gpu"})
    _faux_ollama(monkeypatch, _installes())
    etat = client.get("/api/moteur/etat").json()
    assert etat["joignable"] is True and etat["pret"] is False
    m = _par_nom(etat)
    assert m[GPU]["niveau"] == moteur.INDISPENSABLE and m[GPU]["installe"] is False
    assert m["bge-m3"]["niveau"] == moteur.CONSEILLE


def test_pret_avec_le_modele_du_peripherique_choisi(client, monkeypatch):
    # Organisation en CPU : seul gemma2:2b est indispensable ; « bge-m3:latest »
    # est le nom qu'Ollama donne à un modèle tiré sous « bge-m3 ».
    settings.reglages(client.profile_id).update({"compute_device": "cpu"})
    _faux_ollama(monkeypatch, _installes(CPU, "bge-m3:latest"))
    etat = client.get("/api/moteur/etat").json()
    assert etat["pret"] is True and etat["complet"] is True
    m = _par_nom(etat)
    assert m[CPU]["niveau"] == moteur.INDISPENSABLE
    assert m[GPU]["niveau"] == moteur.FACULTATIF and m[GPU]["installe"] is False


def test_pret_sans_bge_m3_mais_incomplet(client, monkeypatch):
    settings.reglages(client.profile_id).update({"compute_device": "gpu"})
    _faux_ollama(monkeypatch, _installes(GPU))
    etat = client.get("/api/moteur/etat").json()
    assert etat["pret"] is True and etat["complet"] is False


def test_reponse_inattendue_d_ollama(client, monkeypatch):
    # Un autre service sur le port d'Ollama : JSON d'une autre forme.
    _faux_ollama(monkeypatch, lambda _r: httpx.Response(200, json=["pas", "un", "objet"]))
    etat = client.get("/api/moteur/etat").json()
    assert etat["joignable"] is False


def test_est_installe():
    assert moteur.est_installe("bge-m3", {"bge-m3:latest"})
    assert moteur.est_installe("gemma2:2b", {"gemma2:2b"})
    assert not moteur.est_installe("gemma2:2b", {"gemma2:9b"})
    assert not moteur.est_installe("gemma2:2b", {"gemma2:2b:latest"})


def test_message_ne_parle_plus_de_la_fenetre_noire():
    # Elle n'existe pas dans l'application de bureau.
    assert "fenêtre noire" not in main.MESSAGE_OLLAMA_INJOIGNABLE
