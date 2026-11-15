"""
Gestion des comptes (audit du 15/11/2026, lot 4c).

Avant ce lot, un mot de passe ne pouvait être ni changé ni réinitialisé, un
compte ni supprimé ni débloqué, sans retoucher users.json à la main. Ces tests
couvrent l'API (le compte lui-même, le responsable de l'organisation) et la
ligne de commande du service informatique, avec leurs garde-fous : cloisonnement
entre organisations, dernier responsable, temporisation, sessions fermées.

Tout se passe dans un dossier temporaire : rien n'est écrit dans
backend/profiles/ du dépôt.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import (conversations, main, manage_users, profiles, sessions, settings,
                     tentatives, users, zones)


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
    autre = profiles.create_profile("Mairie")["id"]
    users.create_user("rachel", "Secret-01", pid)          # responsable
    users.create_user("marc", "Secret-02", pid)            # membre
    users.create_user("bob", "Secret-09", autre)           # responsable d'une autre org
    yield {"pid": pid, "autre": autre, "rachel": _client("rachel", "Secret-01"),
           "marc": _client("marc", "Secret-02"), "bob": _client("bob", "Secret-09")}
    zones.dossiers_reserves.cache_clear()


def _login(nom, mdp):
    return TestClient(main.app).post("/api/auth/login", json={"username": nom, "password": mdp})


def _client(nom, mdp):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"username": nom, "password": mdp})
    assert r.status_code == 200, r.text
    c.user_id = r.json()["user_id"]
    return c


def _id(nom):
    return users.get_user_by_username(nom)["id"]


# ---------- sessions.py et tentatives.py ----------
def test_fermer_les_sessions_d_un_compte_sauf_une(env):
    j1 = sessions.create_session(_id("marc"), env["pid"])
    j2 = sessions.create_session(_id("marc"), env["pid"])
    j3 = sessions.create_session(_id("rachel"), env["pid"])
    # + la session ouverte par la fixture pour marc
    assert sessions.supprimer_sessions_du_compte(_id("marc"), sauf_jeton=j2) == 2
    assert sessions.resolve_session(j1) is None
    assert sessions.resolve_session(j2) is not None
    assert sessions.resolve_session(j3) is not None
    assert sessions.supprimer_sessions_du_compte("") == 0


def test_debloquer_efface_attente_et_plafond(env):
    for _ in range(tentatives.MAX_ECHECS_FENETRE):
        tentatives.noter_echec("marc")
    assert tentatives.est_bloque("Marc")
    assert tentatives.debloquer("MARC") is True
    assert not tentatives.est_bloque("marc")
    assert tentatives.debloquer("marc") is False
    assert _login("marc", "Secret-02").status_code == 200


# ---------- POST /api/auth/mot-de-passe ----------
def test_changer_son_mot_de_passe(env):
    autre_session = _client("marc", "Secret-02")
    marc = env["marc"]
    r = marc.post("/api/auth/mot-de-passe", json={"ancien": "Secret-02", "nouveau": "Nouveau-02"})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "sessions_fermees": 1}
    assert marc.get("/api/auth/me").status_code == 200                 # session courante gardée
    assert autre_session.get("/api/auth/me").status_code == 401        # les autres fermées
    assert _login("marc", "Secret-02").status_code == 401
    assert _login("marc", "Nouveau-02").status_code == 200
    assert "Nouveau-02" not in json.dumps(json.loads(users.USERS_PATH.read_text("utf-8")))


def test_ancien_mot_de_passe_faux_temporise(env):
    marc = env["marc"]
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        r = marc.post("/api/auth/mot-de-passe", json={"ancien": "faux", "nouveau": "Nouveau-02"})
        assert r.status_code == 400
        assert r.json()["detail"] == "Mot de passe actuel incorrect."
    # Le BON ancien mot de passe est refusé pendant l'attente, comme à la connexion.
    r = marc.post("/api/auth/mot-de-passe", json={"ancien": "Secret-02", "nouveau": "Nouveau-02"})
    assert r.status_code == 429
    assert _login("marc", "Secret-02").status_code == 429              # même compteur
    assert marc.get("/api/auth/me").status_code == 200                 # pas déconnecté


@pytest.mark.parametrize("nouveau", ["court", "secret12", "Secret-02"])
def test_nouveau_mot_de_passe_refuse(env, nouveau):
    r = env["marc"].post("/api/auth/mot-de-passe",
                         json={"ancien": "Secret-02", "nouveau": nouveau})
    assert r.status_code == 400
    assert _login("marc", "Secret-02").status_code == 200


def test_politique_verifiee_avant_l_ancien_mot_de_passe(env):
    """Un nouveau mot de passe trop faible ne compte pas comme un échec."""
    for _ in range(5):
        r = env["marc"].post("/api/auth/mot-de-passe", json={"ancien": "x", "nouveau": "abc"})
        assert r.status_code == 400
    assert not tentatives.est_bloque("marc")


def test_changer_son_mot_de_passe_exige_une_session():
    r = TestClient(main.app).post("/api/auth/mot-de-passe",
                                  json={"ancien": "a", "nouveau": "Nouveau-02"})
    assert r.status_code == 401


# ---------- GET /api/comptes ----------
def test_liste_des_comptes_reservee_au_responsable(env):
    assert env["marc"].get("/api/comptes").status_code == 403
    r = env["rachel"].get("/api/comptes")
    assert r.status_code == 200
    comptes = r.json()["comptes"]
    assert [(c["username"], c["role"], c["moi"]) for c in comptes] == [
        ("rachel", "responsable", True), ("marc", "membre", False)]
    assert set(comptes[0]) == {"id", "username", "role", "created_at", "bloque", "moi"}
    assert "bob" not in r.text and "password" not in r.text


def test_liste_signale_un_compte_bloque(env):
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("marc")
    comptes = {c["username"]: c for c in env["rachel"].get("/api/comptes").json()["comptes"]}
    assert comptes["marc"]["bloque"] is True and comptes["rachel"]["bloque"] is False
    r = env["rachel"].post(f"/api/comptes/{_id('marc')}/debloquer")
    assert r.status_code == 200 and r.json()["bloque"] is False
    assert _login("marc", "Secret-02").status_code == 200


# ---------- Routes du responsable sur un compte ----------
@pytest.mark.parametrize("methode, suffixe, corps", [
    ("post", "/mot-de-passe", {"nouveau": "Nouveau-09"}),
    ("post", "/debloquer", None),
    ("put", "/role", {"role": "membre"}),
    ("delete", "", None),
])
def test_compte_d_une_autre_organisation_introuvable(env, methode, suffixe, corps):
    url = f"/api/comptes/{_id('bob')}{suffixe}"
    kwargs = {"json": corps} if corps is not None else {}
    r = getattr(env["rachel"], methode)(url, **kwargs)
    assert r.status_code == 404
    # Identifiant inventé : même réponse.
    r = getattr(env["rachel"], methode)(f"/api/comptes/{'0' * 32}{suffixe}", **kwargs)
    assert r.status_code == 404
    assert _login("bob", "Secret-09").status_code == 200             # intact
    # Et un membre est refusé avant tout.
    assert getattr(env["marc"], methode)(url, **kwargs).status_code == 403


def test_reinitialiser_le_mot_de_passe_d_un_membre(env):
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("marc")
    r = env["rachel"].post(f"/api/comptes/{_id('marc')}/mot-de-passe",
                           json={"nouveau": "Nouveau-02"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert env["marc"].get("/api/auth/me").status_code == 401         # sessions fermées
    assert _login("marc", "Nouveau-02").status_code == 200             # et débloqué


def test_reinitialisation_refusee_sur_soi_meme_ou_mot_de_passe_faible(env):
    r = env["rachel"].post(f"/api/comptes/{_id('rachel')}/mot-de-passe",
                           json={"nouveau": "Nouveau-01"})
    assert r.status_code == 400 and "Changer mon mot de passe" in r.json()["detail"]
    r = env["rachel"].post(f"/api/comptes/{_id('marc')}/mot-de-passe", json={"nouveau": "abc"})
    assert r.status_code == 400
    assert _login("marc", "Secret-02").status_code == 200


def test_changer_le_role(env):
    r = env["rachel"].put(f"/api/comptes/{_id('marc')}/role", json={"role": "responsable"})
    assert r.status_code == 200 and r.json()["role"] == "responsable"
    assert env["marc"].get("/api/comptes").status_code == 200        # effet immédiat
    # Deux responsables : rachel peut redevenir membre.
    r = env["rachel"].put(f"/api/comptes/{_id('rachel')}/role", json={"role": "membre"})
    assert r.status_code == 200
    assert env["rachel"].get("/api/comptes").status_code == 403


def test_dernier_responsable_ne_devient_pas_membre(env):
    r = env["rachel"].put(f"/api/comptes/{_id('rachel')}/role", json={"role": "membre"})
    assert r.status_code == 409 and "dernier responsable" in r.json()["detail"]
    assert users.get_user_by_username("rachel")["role"] == "responsable"


def test_role_inconnu_refuse(env):
    r = env["rachel"].put(f"/api/comptes/{_id('marc')}/role", json={"role": "chef"})
    assert r.status_code == 400


def test_supprimer_un_compte(env):
    conv = env["marc"].post("/api/conversations", json={"messages": [
        {"role": "user", "content": "privé"}]}).json()
    r = env["rachel"].delete(f"/api/comptes/{_id('marc')}")
    assert r.status_code == 200
    assert env["marc"].get("/api/auth/me").status_code == 401
    assert _login("marc", "Secret-02").status_code == 401
    # La conversation privée reste sur le disque, invisible…
    assert env["rachel"].get(f"/api/conversations/{conv['id']}").status_code == 404
    assert conversations.get_conversation(env["pid"], conv["id"]) is not None
    # … incluse dans l'export du responsable, et purgée par l'effacement.
    export = env["rachel"].get("/api/privacy/export").json()
    assert conv["id"] in [c["id"] for c in export["conversations"]]
    assert env["rachel"].post("/api/privacy/delete").json()["conversations_removed"] == 1


def test_on_ne_se_supprime_pas_soi_meme(env):
    r = env["rachel"].delete(f"/api/comptes/{_id('rachel')}")
    assert r.status_code == 400 and "propre compte" in r.json()["detail"]
    assert env["rachel"].get("/api/auth/me").status_code == 200


def test_supprimer_compte_dernier_responsable(env):
    """Garde-fou de users.py, commun à l'API et à la ligne de commande."""
    with pytest.raises(users.OperationRefusee):
        users.supprimer_compte(_id("rachel"))
    with pytest.raises(users.OperationRefusee):
        users.changer_role(_id("bob"), "membre")
    # Un compte d'avant les rôles (sans champ) compte comme responsable.
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    for u in data["users"]:
        u.pop("role", None)
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")
    assert users.supprimer_compte(_id("marc"))["username"] == "marc"
    with pytest.raises(users.OperationRefusee):
        users.supprimer_compte(_id("rachel"))


# ---------- Ligne de commande ----------
def _clavier(monkeypatch, lignes, mots_de_passe):
    lignes, mots_de_passe = iter(lignes), iter(mots_de_passe)

    def _input(_invite=""):
        try:
            return next(lignes)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr("builtins.input", _input)

    def _getpass(_invite=""):
        try:
            return next(mots_de_passe)
        except StopIteration:
            raise EOFError
    monkeypatch.setattr(manage_users.getpass, "getpass", _getpass)


def test_cli_list_users(env, capsys):
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("marc")
    assert manage_users.main(["list-users"]) == 0
    sortie = capsys.readouterr().out
    assert "Lycée" in sortie and "Mairie" in sortie
    ligne_marc = next(li for li in sortie.splitlines() if "marc" in li)
    assert "membre" in ligne_marc and "BLOQUÉ" in ligne_marc
    assert manage_users.main(["list-users", "--profil", env["autre"]]) == 0
    sortie = capsys.readouterr().out
    assert "bob" in sortie and "rachel" not in sortie
    assert "pbkdf2" not in sortie


def test_cli_change_password(env, monkeypatch, capsys):
    _clavier(monkeypatch, [], ["faux", "Secret-02", "Nouveau-02", "Nouveau-02"])
    assert manage_users.main(["change-password", "Marc"]) == 0
    assert "incorrect" in capsys.readouterr().out
    assert env["marc"].get("/api/auth/me").status_code == 401         # sessions fermées
    assert _login("marc", "Nouveau-02").status_code == 200


def test_cli_change_password_temporise(env, monkeypatch):
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("marc")
    _clavier(monkeypatch, [], ["Secret-02", "Nouveau-02", "Nouveau-02"])
    assert manage_users.main(["change-password", "marc"]) == 1
    assert users.verify_credentials("marc", "Secret-02") is not None


def test_cli_reset_password_et_unlock(env, monkeypatch, capsys):
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("marc")
    _clavier(monkeypatch, [], ["Nouveau-02", "Nouveau-02"])
    assert manage_users.main(["reset-password", "marc"]) == 0
    assert env["marc"].get("/api/auth/me").status_code == 401
    assert _login("marc", "Nouveau-02").status_code == 200
    for _ in range(tentatives.SEUIL_TEMPORISATION):
        tentatives.noter_echec("rachel")
    assert manage_users.main(["unlock", "rachel"]) == 0
    assert "débloqué" in capsys.readouterr().out
    assert _login("rachel", "Secret-01").status_code == 200


def test_cli_set_role_et_dernier_responsable(env, capsys):
    assert manage_users.main(["set-role", "bob", "membre"]) == 1
    assert "dernier responsable" in capsys.readouterr().err
    assert manage_users.main(["set-role", "marc", "responsable"]) == 0
    assert users.get_user_by_username("marc")["role"] == "responsable"
    assert manage_users.main(["set-role", "rachel", "membre"]) == 0


def test_cli_delete_user(env, monkeypatch, capsys):
    _clavier(monkeypatch, ["non"], [])
    assert manage_users.main(["delete-user", "marc"]) == 1
    assert "Rien n'a été modifié" in capsys.readouterr().err
    assert users.get_user_by_username("marc") is not None
    _clavier(monkeypatch, ["oui"], [])
    assert manage_users.main(["delete-user", "marc"]) == 0
    assert users.get_user_by_username("marc") is None
    assert env["marc"].get("/api/auth/me").status_code == 401
    _clavier(monkeypatch, ["oui"], [])
    assert manage_users.main(["delete-user", "rachel"]) == 1          # dernier responsable
    assert users.get_user_by_username("rachel") is not None


def test_cli_identifiant_inconnu(env, capsys):
    assert manage_users.main(["unlock", "personne"]) == 1
    assert "Aucun compte" in capsys.readouterr().err
