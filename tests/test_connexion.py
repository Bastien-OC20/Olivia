"""
Robustesse de la connexion (audit, point 11).

Constats de l'audit, tous vérifiés ici :
  - aucune limite d'essais : 30 tentatives d'affilée, aucune ne bloquée ;
  - un identifiant inconnu répondait ~20 fois plus vite qu'un vrai : on
    devinait les comptes existants au chronomètre ;
  - le calcul PBKDF2 tournait dans une route `async`, figeant tout le serveur ;
  - mots de passe de 4 caractères acceptés, coût de hachage sous la
    recommandation OWASP ;
  - un compte supprimé gardait l'accès jusqu'à expiration de sa session.

Tout se passe dans un dossier temporaire ; l'horloge de la temporisation est
simulée.
"""
import asyncio
import hashlib
import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, tentatives, users

MDP = "Secret-01"


@pytest.fixture
def org(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", MDP, pid)
    return {"pid": pid, "dossier": dossier}


@pytest.fixture
def horloge(monkeypatch):
    """Horloge de la temporisation, avançable à volonté."""
    etat = {"t": 1_000_000.0}
    monkeypatch.setattr(tentatives.time, "time", lambda: etat["t"])
    return etat


def _login(identifiant, mdp):
    return TestClient(main.app).post(
        "/api/auth/login", json={"username": identifiant, "password": mdp})


# ---------- Temporisation des échecs ----------
def test_attente_exponentielle_apres_trois_echecs(org, horloge):
    assert _login("marie", "faux-1").status_code == 401
    assert _login("marie", "faux-2").status_code == 401
    assert _login("marie", "faux-3").status_code == 401        # 3e échec : 20 s
    r = _login("marie", MDP)                                   # même le BON mot de passe
    assert r.status_code == 429
    assert "Réessayez dans 20 secondes" in r.json()["detail"]
    assert int(r.headers["retry-after"]) >= 20
    horloge["t"] += 21
    assert _login("marie", MDP).status_code == 200             # attente écoulée


def test_l_attente_double_et_depasse_une_minute_au_cinquieme_echec():
    attentes = [tentatives._attente_apres(n) for n in range(1, 8)]
    assert attentes == [0, 0, 20, 40, 80, 160, 320]
    assert tentatives._attente_apres(5) > 60
    assert tentatives._attente_apres(50) == tentatives.ATTENTE_MAX


def test_succes_remet_la_serie_a_zero(org, horloge):
    for i in range(2):
        _login("marie", f"faux-{i}")
    assert _login("marie", MDP).status_code == 200
    for i in range(2):                                       # nouvelle série de 2
        assert _login("marie", f"faux-{i}").status_code == 401
    assert _login("marie", MDP).status_code == 200           # pas d'attente


def test_plafond_de_25_echecs_sur_24_heures(org, horloge):
    # Échecs espacés et entrecoupés de réussites : jamais d'attente
    # exponentielle, mais le plafond quotidien finit par bloquer.
    for i in range(tentatives.MAX_ECHECS_FENETRE):
        tentatives.noter_echec("marie")
        tentatives.noter_succes("marie")
        horloge["t"] += 60
    r = _login("marie", MDP)
    assert r.status_code == 429
    assert "heure" in r.json()["detail"]
    horloge["t"] += tentatives.FENETRE                       # la fenêtre glisse
    assert _login("marie", MDP).status_code == 200


def test_identifiant_inconnu_bloque_comme_un_vrai(org, horloge):
    for i in range(3):
        assert _login("inconnu", f"x{i}").status_code == 401
    assert _login("inconnu", "x").status_code == 429


def test_identifiant_jamais_stocke_en_clair(org, horloge):
    _login("MonMotDePasseTapéPourIdentifiant", "x")
    contenu = (org["dossier"] / "tentatives.json").read_text(encoding="utf-8")
    assert "MonMotDePasse" not in contenu
    assert hashlib.sha256(b"monmotdepassetap\xc3\xa9pouridentifiant").hexdigest() in contenu


# ---------- Égalité des temps de réponse ----------
def test_identifiant_inconnu_aussi_lent_qu_un_vrai(org):
    def duree(identifiant):
        debut = time.perf_counter()
        for _ in range(3):
            users.verify_credentials(identifiant, "faux")
        return time.perf_counter() - debut
    vrai, inconnu = duree("marie"), duree("personne")
    # Avant correctif : rapport d'environ 1 à 20. Le dérivé « à blanc » doit
    # amener l'inconnu au même ordre de grandeur.
    assert inconnu > 0.6 * vrai, (vrai, inconnu)


def test_la_connexion_ne_bloque_pas_le_serveur():
    # Route synchrone : FastAPI l'exécute dans son pool de threads.
    assert not asyncio.iscoroutinefunction(main.auth_login)


# ---------- Hachage ----------
def test_nouveau_hachage_au_cout_owasp(org):
    stocke = users.get_user_by_username("marie")["password_hash"]
    prefixe, iterations, _sel, _derive = stocke.split("$")
    assert (prefixe, int(iterations)) == ("pbkdf2_sha256", 600_000)


def test_ancien_format_accepte_puis_remis_a_niveau(org):
    sel = secrets.token_hex(16)
    derive = hashlib.pbkdf2_hmac("sha256", b"ancien", bytes.fromhex(sel), 200_000).hex()
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    data["users"][0]["password_hash"] = f"{sel}${derive}"       # format d'avant
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")

    assert _login("marie", "ancien").status_code == 200
    apres = users.get_user_by_username("marie")["password_hash"]
    assert apres.startswith("pbkdf2_sha256$600000$")
    assert _login("marie", "ancien").status_code == 200         # toujours valable


# ---------- Politique de mot de passe (création) ----------
@pytest.mark.parametrize("mdp", ["Ab1!", "secret12", "SECRET12", "abcdefgh", "12345678"])
def test_mot_de_passe_faible_refuse(org, mdp):
    with pytest.raises(ValueError):
        users.create_user("julie", mdp, org["pid"])


@pytest.mark.parametrize("mdp", ["Secret12", "secret-12", "SECRET-12", "Sécurité-1"])
def test_mot_de_passe_conforme_accepte(org, mdp):
    assert users.create_user(f"julie{len(mdp)}{mdp[0]}", mdp, org["pid"])


# ---------- Compte supprimé : session révoquée ----------
def test_compte_supprime_perd_l_acces_immediatement(org):
    client = TestClient(main.app)
    assert client.post("/api/auth/login",
                       json={"username": "marie", "password": MDP}).status_code == 200
    assert client.get("/api/settings").status_code == 200
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    data["users"] = []                                         # compte retiré à la main
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")
    r = client.get("/api/settings")
    assert r.status_code == 401
    sess = json.loads(sessions.SESSIONS_PATH.read_text(encoding="utf-8"))["sessions"]
    assert sess == {}                                          # session supprimée
