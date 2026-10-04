"""
Points mineurs de l'audit.

  - aperçu cassé pour un nom de fichier contenant « & », « + » ou « # » ;
  - aperçu PDF transformé en téléchargement (servi en `attachment` dans une
    <iframe> : constaté dans Chromium) ;
  - choix GPU/CPU détecté perdu après un effacement RGPD ;
  - backend/.env jamais lu ;
  - API dépréciées (`on_event`).
"""
import os

import pytest
from fastapi.testclient import TestClient

import backend
from backend import hardware, main, profiles, sessions, settings, users, zones


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
    c.docs, c.pid = docs, pid
    yield c
    zones.dossiers_reserves.cache_clear()


# ---------- Aperçu ----------
@pytest.mark.parametrize("nom", ["C&A n°1+2.pdf", "compte rendu #3.pdf", "a=b?c.pdf"])
def test_apercu_pdf_avec_caracteres_speciaux(client, nom):
    (client.docs / nom).write_bytes(b"%PDF-1.4\n%%EOF")
    apercu = client.get("/api/fs/preview", params={"path": f"r0/{nom}"}).json()
    r = client.get(apercu["url"])                  # l'adresse telle que l'iframe l'utilise
    assert r.status_code == 200, apercu["url"]
    assert r.content.startswith(b"%PDF")
    assert r.headers["content-disposition"].startswith("inline")
    assert r.headers["content-type"] == "application/pdf"


def test_telechargement_reste_en_piece_jointe(client):
    (client.docs / "doc.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
    r = client.get("/api/fs/download", params={"path": "r0/doc.pdf"})
    assert r.headers["content-disposition"].startswith("attachment")


@pytest.mark.parametrize("nom", ["page.html", "dessin.svg", "notes.txt"])
def test_apercu_en_ligne_reserve_au_pdf(client, nom):
    # Un .html ou un .svg servi en ligne depuis l'origine d'Olivia y
    # exécuterait ses scripts : il reste en pièce jointe, même avec apercu=1.
    (client.docs / nom).write_text("<script>alert(1)</script>", encoding="utf-8")
    r = client.get("/api/fs/download", params={"path": f"r0/{nom}", "apercu": 1})
    assert r.headers["content-disposition"].startswith("attachment")


# ---------- Effacement RGPD : GPU/CPU re-détecté ----------
def test_effacement_redetecte_le_peripherique(client, monkeypatch):
    client.put("/api/settings", json={"compute_device": "gpu"})
    monkeypatch.setattr(hardware, "detect_default_device", lambda: "cpu")
    assert client.post("/api/privacy/delete").status_code == 200
    assert settings.reglages(client.pid).get()["compute_device"] == "cpu"


# ---------- backend/.env ----------
def test_env_charge_sans_ecraser_l_existant(tmp_path, monkeypatch):
    fichier = tmp_path / ".env"
    fichier.write_text("OLIVIA_TEST_NOUVELLE=depuis-fichier\n"
                       "OLIVIA_TEST_EXISTANTE=depuis-fichier\n", encoding="utf-8")
    monkeypatch.delenv("OLIVIA_TEST_NOUVELLE", raising=False)
    monkeypatch.setenv("OLIVIA_TEST_EXISTANTE", "depuis-environnement")
    assert backend.charger_env(fichier) is True
    assert os.environ["OLIVIA_TEST_NOUVELLE"] == "depuis-fichier"
    assert os.environ["OLIVIA_TEST_EXISTANTE"] == "depuis-environnement"
    monkeypatch.delenv("OLIVIA_TEST_NOUVELLE", raising=False)


def test_env_absent_sans_effet(tmp_path):
    assert backend.charger_env(tmp_path / "absent.env") is False


# ---------- Démarrage : lifespan (on_event est déprécié) ----------
def test_demarrage_par_lifespan(monkeypatch):
    appels = []
    monkeypatch.setattr(main, "_demarrer_indexation_semantique", lambda: appels.append(1))
    with TestClient(main.app):
        pass
    assert appels == [1]
