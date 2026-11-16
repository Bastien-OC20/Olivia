"""
Réglages lus par un MEMBRE : jamais ceux réservés au responsable.

`GET /api/settings` renvoyait à tout compte de l'organisation l'ensemble des
réglages : chemins des dossiers de travail, du calendrier `.ics` et de
Tesseract, serveur et compte IMAP, URL SearXNG, prompt système… L'interface les
cachait au membre, mais le serveur les lui envoyait quand même (constaté le
16/11/2026 en corrigeant la fuite du chemin `.ics` dans l'aperçu du
calendrier). Un membre ne reçoit plus que ses réglages de confort, plus le NOM
des dossiers de travail (sans leur chemin), dont l'explorateur a besoin.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users, zones


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    secret = tmp_path / "Arborescence-secrete"
    (secret / "Compta").mkdir(parents=True)
    (secret / "Courrier").mkdir()
    pid = profiles.create_profile("Org")["id"]
    users.create_user("rachel", "Secret-01", pid)          # premier : responsable
    users.create_user("marc", "Secret-02", pid)            # suivant : membre
    rachel, marc = TestClient(main.app), TestClient(main.app)
    assert rachel.post("/api/auth/login",
                       json={"username": "rachel", "password": "Secret-01"}).status_code == 200
    assert marc.post("/api/auth/login",
                     json={"username": "marc", "password": "Secret-02"}).status_code == 200
    r = rachel.put("/api/settings", json={
        "fs_roots": [{"path": str(secret / "Compta"), "label": "Comptabilité"},
                     str(secret / "Courrier")],
        "system_prompt": "Consigne interne de l'organisation.",
        "searxng_url": "http://serveur-interne:8888",
        "connectors": {
            "imap": {"enabled": True, "host": "imap.interne.fr", "user": "secretariat@interne.fr",
                     "password": "MDP-IMAP"},
            "calendar_ics": {"enabled": True, "path": str(secret / "agenda.ics")},
        },
    })
    assert r.status_code == 200, r.text
    yield {"rachel": rachel, "marc": marc, "secret": secret, "pid": pid}
    zones.dossiers_reserves.cache_clear()


def _texte(reponse) -> str:
    return json.dumps(reponse.json(), ensure_ascii=False)


def test_un_membre_ne_recoit_aucun_reglage_reserve(env):
    lu = env["marc"].get("/api/settings")
    assert lu.status_code == 200
    donnees = lu.json()
    for cle in main.CLES_RESERVEES_RESPONSABLE - {"fs_roots"}:
        assert cle not in donnees, cle
    texte = _texte(lu)
    for indice in ("Arborescence-secrete", "imap.interne.fr", "secretariat@interne.fr",
                   "serveur-interne", "Consigne interne"):
        assert indice not in texte, indice
    # Ses réglages de confort restent là.
    assert {"tone", "reasoning_style", "theme", "compute_device"} <= donnees.keys()


def test_un_membre_recoit_le_nom_des_dossiers_sans_leur_chemin(env):
    """L'explorateur du membre propose « Tous les dossiers / Comptabilité /
    Courrier » : il a besoin des noms, pas des chemins."""
    racines = env["marc"].get("/api/settings").json()["fs_roots"]
    assert [r["label"] for r in racines] == ["Comptabilité", "Courrier"]
    assert all(r["path"] == "" for r in racines)


def test_la_reponse_a_l_enregistrement_d_un_membre_est_filtree_aussi(env):
    r = env["marc"].put("/api/settings", json={"tone": "friendly"})
    assert r.status_code == 200
    assert "Arborescence-secrete" not in _texte(r)
    assert "connectors" not in r.json()


def test_le_membre_renvoie_sa_vue_telle_quelle_sans_refus(env):
    """Une interface qui renvoie tout ce qu'elle a reçu (dossiers sans chemin
    compris) n'est pas refusée et n'efface pas les vrais dossiers."""
    vue = env["marc"].get("/api/settings").json()
    vue["tone"] = "teacher"
    r = env["marc"].put("/api/settings", json=vue)
    assert r.status_code == 200, r.text
    vrais = settings.reglages(env["pid"]).get()
    assert [e["path"] for e in vrais["fs_roots"]] == [
        str(env["secret"] / "Compta"), str(env["secret"] / "Courrier")]
    assert vrais["tone"] == "teacher"


def test_un_membre_ne_peut_toujours_pas_changer_les_dossiers(env):
    r = env["marc"].put("/api/settings", json={"fs_roots": [{"path": "", "label": "Autre"}]})
    assert r.status_code == 403


def test_dossiers_homonymes_distingues_sans_chemin(env, tmp_path):
    """Deux dossiers de travail de même nom étaient distingués par le chemin
    COMPLET de leur dossier parent (« Courrier — C:\\…\\Lycée ») dans la liste
    des dossiers, lue par tout compte. Ils le sont désormais par le seul nom du
    dossier parent, puis par un numéro si ce nom ne suffit pas."""
    base = tmp_path / "Arborescence-secrete"
    for parent in ("Lycée", "Collège", "Annexe/Lycée"):
        (base / parent / "Courrier").mkdir(parents=True)
    racines = [str(base / p / "Courrier") for p in ("Lycée", "Collège", "Annexe/Lycée")]
    assert env["rachel"].put("/api/settings", json={"fs_roots": racines}).status_code == 200
    r = env["marc"].get("/api/fs/list")
    assert r.status_code == 200
    noms = [i["name"] for i in r.json()["items"]]
    assert noms == ["Courrier — Lycée", "Courrier — Collège", "Courrier — Lycée (2)"]
    assert len(set(noms)) == len(noms)
    assert "Arborescence-secrete" not in json.dumps([i["name"] for i in r.json()["items"]])


def test_la_liste_des_dossiers_ne_donne_aucun_chemin_du_disque(env):
    """`GET /api/fs/list` renvoyait le chemin complet du dossier de travail
    (champ `root`) et le recopiait dans ses erreurs (« Dossier introuvable :
    C:\\… »). Seuls restent le nom du dossier et le chemin virtuel `rN/…`."""
    dossier = env["secret"] / "Compta"
    (dossier / "bilan.txt").write_text("bilan", encoding="utf-8")
    assert env["rachel"].put("/api/settings",
                             json={"fs_roots": [str(dossier)]}).status_code == 200
    for client in (env["marc"], env["rachel"]):
        reponses = [client.get("/api/fs/list"),
                    client.get("/api/fs/list", params={"path": "r0"}),
                    client.get("/api/fs/list", params={"path": "r0/absent"}),
                    client.get("/api/fs/list", params={"path": "r0/bilan.txt"})]
        assert [r.status_code for r in reponses] == [200, 200, 404, 400]
        assert reponses[0].json()["root"] == "Compta"
        assert "r0/absent" in reponses[2].json()["detail"]
        for r in reponses:
            assert "Arborescence-secrete" not in r.text, r.text


def test_le_responsable_recoit_toujours_tout(env):
    lu = env["rachel"].get("/api/settings").json()
    assert lu["fs_roots"][0]["path"] == str(env["secret"] / "Compta")
    assert lu["connectors"]["imap"]["host"] == "imap.interne.fr"
    assert lu["connectors"]["imap"]["password"] != "MDP-IMAP"      # toujours masqué
