"""
Rôles responsable / membre (audit du 15/11/2026, lot 4a).

Avant les rôles, tout compte d'une organisation pouvait changer ses dossiers de
travail, ses connecteurs (et leurs mots de passe), le moteur OCR exécuté, et
déclencher l'effacement RGPD de toute l'organisation. Ces tests garantissent
qu'un membre n'y a plus accès, qu'il garde ses réglages de confort, et que les
comptes d'avant les rôles gardent leurs droits.

Tout se passe dans un dossier temporaire : rien n'est écrit dans
backend/profiles/ du dépôt.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, manage_users, profiles, sessions, settings, users, zones


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "modele.docx").write_bytes(b"pas un vrai docx")
    autre = tmp_path / "autre"
    autre.mkdir()
    pid = profiles.create_profile("Lycée")["id"]
    users.create_user("rachel", "Secret-01", pid)          # premier : responsable
    users.create_user("marc", "Secret-02", pid)            # suivant : membre
    rachel = _client("rachel", "Secret-01")
    marc = _client("marc", "Secret-02")
    assert rachel.put("/api/settings", json={
        "fs_roots": [str(docs)],
        "connectors": {"imap": {"host": "imap.exemple.fr", "password": "MDP-IMAP"}},
        "search_brave_api_key": "CLE-BRAVE",
    }).status_code == 200
    yield {"tmp": tmp_path, "pid": pid, "docs": docs, "autre": autre,
           "rachel": rachel, "marc": marc}
    zones.dossiers_reserves.cache_clear()


def _client(nom, mdp):
    c = TestClient(main.app)
    r = c.post("/api/auth/login", json={"username": nom, "password": mdp})
    assert r.status_code == 200, r.text
    c.connexion = r.json()
    return c


# ---------- Rôle par défaut, migration ----------
def test_premier_compte_responsable_suivants_membres(env):
    assert users.get_user_by_username("rachel")["role"] == "responsable"
    assert users.get_user_by_username("marc")["role"] == "membre"


def test_connexion_et_me_renvoient_le_role(env):
    assert env["rachel"].connexion["role"] == "responsable"
    assert env["marc"].connexion["role"] == "membre"
    assert env["rachel"].get("/api/auth/me").json()["role"] == "responsable"
    assert env["marc"].get("/api/auth/me").json()["role"] == "membre"


def test_compte_sans_role_reste_responsable_sans_reecriture(env):
    """Migration : un users.json d'avant les rôles garde tous ses droits."""
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    for u in data["users"]:
        del u["role"]
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")
    marc = _client("marc", "Secret-02")
    assert marc.connexion["role"] == "responsable"
    assert marc.get("/api/fs/drives").status_code == 200
    # Rien n'a été réécrit : le champ n'apparaît pas tout seul.
    relu = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    assert all("role" not in u for u in relu["users"])


def test_role_inconnu_vaut_membre(env):
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    for u in data["users"]:
        if u["username"] == "rachel":
            u["role"] = "administrateur"
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")
    assert env["rachel"].get("/api/auth/me").json()["role"] == "membre"
    assert env["rachel"].get("/api/fs/drives").status_code == 403


def test_retrogradation_immediate(env):
    """Le rôle est relu à chaque requête : pas d'attente de fin de session."""
    data = json.loads(users.USERS_PATH.read_text(encoding="utf-8"))
    for u in data["users"]:
        if u["username"] == "rachel":
            u["role"] = "membre"
    users.USERS_PATH.write_text(json.dumps(data), encoding="utf-8")
    assert env["rachel"].get("/api/fs/drives").status_code == 403


# ---------- Routes réservées ----------
@pytest.mark.parametrize("methode, url, corps", [
    ("post", "/api/privacy/delete", None),
    ("post", "/api/documents/modele", {"source": "r0/modele.docx"}),
    ("get", "/api/fs/drives", None),
    ("get", "/api/fs/browse?path=__TMP__", None),
])
def test_routes_reservees_refusees_au_membre(env, methode, url, corps):
    url = url.replace("__TMP__", str(env["tmp"]))
    kwargs = {"json": corps} if corps is not None else {}
    r = getattr(env["marc"], methode)(url, **kwargs)
    assert r.status_code == 403
    assert "responsable" in r.json()["detail"]
    r = getattr(env["rachel"], methode)(url, **kwargs)
    assert r.status_code != 403


def test_effacement_par_un_membre_ne_touche_a_rien(env):
    conv = env["rachel"].post("/api/conversations", json={"messages": []}).json()
    assert env["marc"].post("/api/privacy/delete").status_code == 403
    assert env["rachel"].get(f"/api/conversations/{conv['id']}").status_code == 200
    assert env["rachel"].get("/api/settings").json()["fs_roots"]


# ---------- Réglages réservés ----------
@pytest.mark.parametrize("patch", [
    {"fs_roots": []},
    {"fs_roots": ["__AUTRE__"]},
    {"connectors": {"imap": {"host": "pirate.exemple"}}},
    {"connectors": {"imap": {"password": "nouveau"}}},
    {"connectors": {"notion": {"enabled": True}}},
    {"search_provider": "brave"},
    {"searxng_url": "http://ailleurs:8888"},
    {"search_brave_api_key": "AUTRE-CLE"},
    {"search_official_only": True},
    {"ocr_enabled": False},
    {"ocr_tesseract_path": "C:/tesseract/tesseract.exe"},
    {"system_prompt": "Réponds en anglais."},
    {"docgen_appel": "Chers parents,"},
    {"docgen_formule_politesse": "Bien à vous."},
    {"docgen_lieu": "Ailleurs"},
    {"docgen_signature": "Quelqu'un d'autre"},
])
def test_membre_ne_change_pas_un_reglage_reserve(env, patch):
    patch = json.loads(json.dumps(patch).replace("__AUTRE__", str(env["autre"]).replace(
        "\\", "\\\\")))
    avant = env["rachel"].get("/api/settings").json()
    r = env["marc"].put("/api/settings", json={**patch, "tone": "formal"})
    assert r.status_code == 403
    assert "responsable" in r.json()["detail"]
    apres = env["rachel"].get("/api/settings").json()
    assert apres == avant                    # rien enregistré, pas même le ton
    # Le secret enregistré n'a pas bougé.
    vrais = settings.reglages(env["pid"]).get()
    assert vrais["connectors"]["imap"]["password"] == "MDP-IMAP"
    assert vrais["search_brave_api_key"] == "CLE-BRAVE"


def test_responsable_change_les_reglages_reserves(env):
    r = env["rachel"].put("/api/settings", json={
        "fs_roots": [str(env["autre"])], "system_prompt": "Sois bref.",
        "connectors": {"imap": {"host": "imap.lycee.fr"}}, "ocr_enabled": False,
    })
    assert r.status_code == 200
    s = r.json()
    assert s["system_prompt"] == "Sois bref." and s["ocr_enabled"] is False
    assert s["connectors"]["imap"]["host"] == "imap.lycee.fr"


def test_outils_actifs_reserve_au_responsable(env):
    """La boucle d'outils décide de ce que le modèle lit de lui-même (documents,
    mails, agenda) : un membre ne la change pas, le responsable si."""
    r = env["marc"].put("/api/settings", json={"outils_actifs": False})
    assert r.status_code == 403
    assert "outils_actifs" in r.json()["detail"]
    assert settings.reglages(env["pid"]).get()["outils_actifs"] is True
    # Renvoyée inchangée (l'interface renvoie tout), elle n'est pas refusée.
    assert env["marc"].put("/api/settings", json={"outils_actifs": True}).status_code == 200
    r = env["rachel"].put("/api/settings", json={"outils_actifs": False})
    assert r.status_code == 200 and r.json()["outils_actifs"] is False


def test_membre_enregistre_son_ton_en_renvoyant_tous_les_reglages(env):
    """L'interface renvoie TOUS les réglages (secrets masqués) à chaque
    « Enregistrer » : un membre doit pouvoir changer son ton malgré cela."""
    tout = env["marc"].get("/api/settings").json()
    # Depuis le 16/11/2026, un membre ne reçoit plus les réglages réservés
    # (connecteurs compris, voir tests/test_reglages_membre.py) : il renvoie sa vue.
    assert "connectors" not in tout and "search_brave_api_key" not in tout
    tout.update(tone="formal", reasoning_style="concise", temperature=0.3,
                simple_mode=False, privacy_consent=True)
    r = env["marc"].put("/api/settings", json=tout)
    assert r.status_code == 200, r.text
    s = r.json()
    assert (s["tone"], s["reasoning_style"], s["temperature"]) == ("formal", "concise", 0.3)
    vrais = settings.reglages(env["pid"]).get()
    assert vrais["connectors"]["imap"]["password"] == "MDP-IMAP"
    assert vrais["search_brave_api_key"] == "CLE-BRAVE"


def test_membre_renvoie_les_dossiers_sous_forme_de_chemins(env):
    """Une racine renvoyée inchangée, en chaîne ou en objet, n'est pas une modification."""
    docs = str(env["docs"])
    for forme in ([docs], [{"path": docs}], [{"path": docs, "label": ""}]):
        r = env["marc"].put("/api/settings", json={"fs_roots": forme, "tone": "friendly"})
        assert r.status_code == 200, (forme, r.text)


def test_membre_garde_les_reglages_de_confort(env):
    r = env["marc"].put("/api/settings", json={
        "compute_device": "cpu", "tone": "teacher", "simple_mode": True})
    assert r.status_code == 200


def test_membre_enregistre_le_theme_de_l_interface(env):
    """Le thème est un réglage de confort : pas réservé au responsable."""
    r = env["marc"].put("/api/settings", json={"theme": "sombre"})
    assert r.status_code == 200, r.text
    assert r.json()["theme"] == "sombre"


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


def test_init_seul_un_responsable_confirme(env, monkeypatch, capsys):
    n = manage_users.ESSAIS_CONFIRMATION
    _clavier(monkeypatch, ["1"] + ["marc"] * n + ["julie"], ["Secret-02"] * n)
    assert manage_users.main(["init"]) == 1
    assert users.get_user_by_username("julie") is None
    assert "seul un responsable" in capsys.readouterr().out


def test_init_cree_un_membre_par_defaut(env, monkeypatch):
    _clavier(monkeypatch, ["1", "rachel", "", "julie"], ["Secret-01", "Secret-03", "Secret-03"])
    assert manage_users.main(["init"]) == 0
    assert users.get_user_by_username("julie")["role"] == "membre"


def test_init_peut_creer_un_responsable(env, monkeypatch):
    _clavier(monkeypatch, ["1", "rachel", "3", "2", "julie"],
             ["Secret-01", "Secret-03", "Secret-03"])
    assert manage_users.main(["init"]) == 0
    assert users.get_user_by_username("julie")["role"] == "responsable"


def test_init_nouvelle_organisation_premier_compte_responsable(env, monkeypatch):
    _clavier(monkeypatch, ["n", "Mairie", "julie"], ["Secret-03", "Secret-03"])
    assert manage_users.main(["init"]) == 0
    assert users.get_user_by_username("julie")["role"] == "responsable"


def test_create_user_option_role(env, monkeypatch):
    _clavier(monkeypatch, [], ["Secret-03", "Secret-03"])
    assert manage_users.main(["create-user", "julie", env["pid"], "--role", "responsable"]) == 0
    assert users.get_user_by_username("julie")["role"] == "responsable"
    _clavier(monkeypatch, [], ["Secret-04", "Secret-04"])
    assert manage_users.main(["create-user", "paul", env["pid"]]) == 0
    assert users.get_user_by_username("paul")["role"] == "membre"


def test_create_user_role_inconnu_refuse(env):
    with pytest.raises(ValueError):
        users.create_user("julie", "Secret-03", env["pid"], role="chef")
