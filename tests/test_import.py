"""
Import de fichiers : un document existant n'est jamais écrasé (audit, point 7).

Un import portant le nom d'un fichier déjà présent le remplaçait sans prévenir.
Le fichier reçu est désormais rangé sous « nom (2).ext », et la réponse le dit.
Tout se passe dans un dossier temporaire.
"""
import io

import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users, zones


@pytest.fixture
def client(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    docs = tmp_path / "docs"
    docs.mkdir()
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", "Secret-01", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    assert c.put("/api/settings", json={"fs_roots": [str(docs)]}).status_code == 200
    c.docs = docs
    yield c
    zones.dossiers_reserves.cache_clear()


def _importer(client, nom, contenu=b"x", path="r0"):
    return client.post("/api/fs/upload", params={"path": path},
                       files={"file": (nom, io.BytesIO(contenu), "text/plain")})


def test_import_d_un_fichier_neuf(client):
    r = _importer(client, "rapport.txt", b"neuf")
    assert r.status_code == 200
    corps = r.json()
    assert corps["name"] == "rapport.txt"
    assert corps["renamed"] is False
    assert (client.docs / "rapport.txt").read_bytes() == b"neuf"


def test_un_homonyme_ne_remplace_jamais_l_original(client):
    (client.docs / "rapport.txt").write_bytes(b"VERSION ORIGINALE")
    r2 = _importer(client, "rapport.txt", b"deuxieme")
    r3 = _importer(client, "rapport.txt", b"troisieme")
    assert (client.docs / "rapport.txt").read_bytes() == b"VERSION ORIGINALE"
    assert r2.json() == {
        "path": "r0/rapport (2).txt", "name": "rapport (2).txt", "size": len(b"deuxieme"),
        "requested_name": "rapport.txt", "renamed": True,
    }
    assert r3.json()["name"] == "rapport (3).txt"
    assert (client.docs / "rapport (2).txt").read_bytes() == b"deuxieme"
    assert (client.docs / "rapport (3).txt").read_bytes() == b"troisieme"


def test_nom_a_plusieurs_points(client):
    (client.docs / "CR 2026.09.12.pdf").write_bytes(b"%PDF")
    r = _importer(client, "CR 2026.09.12.pdf")
    assert r.json()["name"] == "CR 2026.09.12 (2).pdf"


def test_zone_d_import_par_defaut_protegee_aussi(client):
    assert _importer(client, "a.txt", b"1", path="").json()["name"] == "a.txt"
    r = _importer(client, "a.txt", b"2", path="")
    assert r.json()["name"] == "a (2).txt"
    assert (client.docs / "_uploads" / "a.txt").read_bytes() == b"1"


def test_fichier_trop_gros_ne_laisse_rien_et_ne_touche_pas_l_original(client, monkeypatch):
    monkeypatch.setattr(main, "MAX_UPLOAD_SIZE", 10)
    (client.docs / "rapport.txt").write_bytes(b"ORIGINAL")
    r = _importer(client, "rapport.txt", b"y" * 50)
    assert r.status_code == 413
    assert (client.docs / "rapport.txt").read_bytes() == b"ORIGINAL"
    assert not (client.docs / "rapport (2).txt").exists()


def test_creations_simultanees_du_meme_nom(tmp_path):
    # Deux imports en cours en même temps : fichiers encore ouverts, aucun des
    # deux ne doit obtenir l'emplacement de l'autre.
    p1, f1 = main._ouvrir_fichier_neuf(tmp_path, "doc.txt")
    p2, f2 = main._ouvrir_fichier_neuf(tmp_path, "doc.txt")
    with f1, f2:
        f1.write(b"un")
        f2.write(b"deux")
    assert (p1.name, p2.name) == ("doc.txt", "doc (2).txt")
    assert p1.read_bytes() == b"un" and p2.read_bytes() == b"deux"
