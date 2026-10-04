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


# ---------- Téléchargement des modèles depuis Oliv'IA ----------
def _faux_client_sync(monkeypatch, gestionnaire):
    vrai = httpx.Client

    class _Client(vrai):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(gestionnaire)
            super().__init__(*a, **k)
    monkeypatch.setattr(moteur.httpx, "Client", _Client)


@pytest.fixture
def suivis_vides(monkeypatch):
    monkeypatch.setattr(moteur, "_suivis", {})


def _flux(*evenements):
    return "\n".join(__import__("json").dumps(e) for e in evenements) + "\n"


def test_telechargement_progression_puis_succes(monkeypatch, suivis_vides):
    recu = {}

    def _pull(requete):
        recu.update(__import__("json").loads(requete.content))
        return httpx.Response(200, text=_flux(
            {"status": "pulling manifest"},
            {"status": "pulling a", "digest": "sha256:a", "total": 100, "completed": 40},
            {"status": "pulling b", "digest": "sha256:b", "total": 300, "completed": 300},
            {"status": "success"},
        ))
    _faux_client_sync(monkeypatch, _pull)
    moteur._suivis[CPU] = {"etat": moteur.EN_COURS, "fait": 0, "total": 0, "message": ""}
    moteur._telecharger("http://ollama", CPU)
    assert recu == {"model": CPU, "stream": True}
    suivi = moteur.etat_telechargements()[CPU]
    assert suivi["etat"] == moteur.TERMINE and suivi["fait"] == suivi["total"] == 400


def test_telechargement_erreur_d_ollama(monkeypatch, suivis_vides):
    erreur = {"error": "pull model manifest: file does not exist"}
    _faux_client_sync(monkeypatch, lambda _r: httpx.Response(
        200, text=_flux({"status": "pulling manifest"}, erreur)))
    moteur._suivis[CPU] = {"etat": moteur.EN_COURS, "fait": 0, "total": 0, "message": ""}
    moteur._telecharger("http://ollama", CPU)
    suivi = moteur.etat_telechargements()[CPU]
    assert suivi["etat"] == moteur.ERREUR and "file does not exist" in suivi["message"]


def test_telechargement_ollama_injoignable(monkeypatch, suivis_vides):
    def _refus(_r):
        raise httpx.ConnectError("refusé")
    _faux_client_sync(monkeypatch, _refus)
    moteur._suivis[CPU] = {"etat": moteur.EN_COURS, "fait": 0, "total": 0, "message": ""}
    moteur._telecharger("http://ollama", CPU)
    suivi = moteur.etat_telechargements()[CPU]
    assert suivi["etat"] == moteur.ERREUR and "ne répond pas" in suivi["message"]


def test_flux_coupe_avant_la_fin(monkeypatch, suivis_vides):
    partiel = {"status": "pulling a", "digest": "sha256:a", "total": 10, "completed": 3}
    _faux_client_sync(monkeypatch, lambda _r: httpx.Response(200, text=_flux(partiel)))
    moteur._suivis[CPU] = {"etat": moteur.EN_COURS, "fait": 0, "total": 0, "message": ""}
    moteur._telecharger("http://ollama", CPU)
    assert moteur.etat_telechargements()[CPU]["etat"] == moteur.ERREUR


def test_pas_de_second_telechargement_simultane(monkeypatch, suivis_vides):
    lances = []
    monkeypatch.setattr(moteur.threading, "Thread",
                        lambda **k: type("T", (), {"start": lambda self: lances.append(k)})())
    assert moteur.lancer_telechargement("http://ollama", CPU) is True
    assert moteur.lancer_telechargement("http://ollama", CPU) is False
    assert len(lances) == 1


def test_route_refuse_un_modele_non_prevu(client, suivis_vides):
    r = client.post("/api/moteur/telecharger", json={"modele": "llama3:70b"})
    assert r.status_code == 400


def test_route_lance_un_modele_attendu(client, monkeypatch, suivis_vides):
    lances = []
    monkeypatch.setattr(moteur, "lancer_telechargement",
                        lambda url, nom: lances.append(nom) or True)
    r = client.post("/api/moteur/telecharger", json={"modele": "bge-m3"})
    assert r.status_code == 200 and r.json() == {"ok": True, "deja_en_cours": False}
    assert lances == ["bge-m3"]


def test_etat_rapporte_la_progression(client, monkeypatch, suivis_vides):
    _faux_ollama(monkeypatch, _installes())
    moteur._suivis["bge-m3"] = {"etat": moteur.EN_COURS, "fait": 5, "total": 10,
                                "message": "pulling"}
    m = _par_nom(client.get("/api/moteur/etat").json())
    assert m["bge-m3"]["telechargement"]["fait"] == 5
    assert m[GPU]["telechargement"] is None
