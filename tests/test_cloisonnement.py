"""
Tests de cloisonnement entre organisations (audit, section « Critique :
sécurité et cloisonnement »).

Chaque test rejoue un scénario d'attaque constaté lors de l'audit, avec deux
organisations et un compte chacune. Tout se passe dans un dossier temporaire :
le registre des profils, les comptes et les sessions sont redirigés vers
`tmp_path`, rien n'est écrit dans backend/profiles/ du dépôt.

À lancer depuis la racine du dépôt :
    pip install pytest
    python -m pytest tests
"""
import io
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import docmodele, main, ocr, profiles, sessions, settings, users, zones


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Deux organisations isolées (A et B), un client connecté pour chacune."""
    dossier_profils = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier_profils)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier_profils / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier_profils / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier_profils / "sessions.json")
    # Réglages : cache d'instances neuf, pour ne pas hériter d'un autre test.
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    # Les dossiers réservés sont mémorisés : on les recalcule avec le dossier
    # des profils temporaire, puis on vide le cache en sortie.
    zones.dossiers_reserves.cache_clear()

    docs_a = tmp_path / "docsA"
    docs_b = tmp_path / "docsB"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "a.txt").write_text("document de A", encoding="utf-8")
    (docs_b / "b.txt").write_text("document de B", encoding="utf-8")

    pa = profiles.create_profile("Org A")
    pb = profiles.create_profile("Org B")
    users.create_user("alice", "PassA-001", pa["id"])
    users.create_user("bob", "PassB-001", pb["id"])

    alice = TestClient(main.app)
    bob = TestClient(main.app)
    assert alice.post("/api/auth/login",
                      json={"username": "alice", "password": "PassA-001"}).status_code == 200
    assert bob.post("/api/auth/login",
                    json={"username": "bob", "password": "PassB-001"}).status_code == 200
    assert alice.put("/api/settings", json={"fs_roots": [str(docs_a)]}).status_code == 200
    assert bob.put("/api/settings", json={
        "fs_roots": [str(docs_b)],
        "connectors": {"imap": {"password": "MDP-IMAP-DE-BOB"}},
    }).status_code == 200

    yield {"tmp": tmp_path, "profils": dossier_profils, "docs_a": docs_a, "docs_b": docs_b,
           "pa": pa, "pb": pb, "alice": alice, "bob": bob}
    zones.dossiers_reserves.cache_clear()


# ---------- 1. Dossiers de travail : les données internes restent inaccessibles ----------
def test_dossier_des_profils_refuse_comme_dossier_de_travail(env):
    for interdit in (env["profils"], env["profils"] / env["pb"]["id"], zones.DOSSIER_BACKEND):
        r = env["alice"].put("/api/settings", json={"fs_roots": [str(interdit)]})
        assert r.status_code == 400, interdit
        assert "réservé" in r.json()["detail"]


def test_racine_large_masque_et_refuse_les_dossiers_reserves(env):
    # tmp_path CONTIENT le dossier des profils : racine autorisée (comme D:\),
    # mais le dossier réservé y est invisible et inaccessible.
    alice = env["alice"]
    assert alice.put("/api/settings", json={"fs_roots": [str(env["tmp"])]}).status_code == 200
    noms = [i["name"] for i in alice.get("/api/fs/list").json()["items"]]
    assert "profiles" not in noms
    assert "docsA" in noms
    for chemin in ("r0/profiles", "r0/profiles/sessions.json", "r0/profiles/users.json",
                   f"r0/profiles/{env['pb']['id']}/settings.json"):
        for route in ("/api/fs/list", "/api/fs/read", "/api/fs/preview",
                      "/api/fs/download", "/api/fs/text"):
            r = alice.get(route, params={"path": chemin})
            assert r.status_code == 403, (route, chemin, r.status_code)
    r = alice.post("/api/fs/upload", params={"path": "r0/profiles"},
                   files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 403


def test_recherche_ne_parcourt_pas_les_dossiers_reserves(env):
    alice = env["alice"]
    alice.put("/api/settings", json={"fs_roots": [str(env["tmp"])]})
    # Le mot de passe IMAP de B est en clair dans son settings.json.
    resultats = alice.get("/api/fs/search", params={"q": "MDP-IMAP-DE-BOB"}).json()["results"]
    assert resultats == []
    trouves = alice.get("/api/fs/search", params={"q": "document"}).json()["results"]
    assert {r["name"] for r in trouves} == {"a.txt", "b.txt"}


def test_racine_reservee_deja_enregistree_est_ignoree(env):
    # Réglage écrit par une version antérieure, qui ne refusait rien.
    settings.reglages(env["pa"]["id"]).update({"fs_roots": [{"path": str(env["profils"]),
                                                             "label": ""}]})
    racines = main.get_fs_roots(env["pa"]["id"])
    assert env["profils"].resolve() not in racines


@pytest.mark.skipif(os.name == "nt", reason="liens symboliques : droits requis sous Windows")
def test_lien_symbolique_vers_les_profils_refuse(env):
    (env["docs_a"] / "raccourci").symlink_to(env["profils"], target_is_directory=True)
    alice = env["alice"]
    assert alice.get("/api/fs/read",
                     params={"path": "r0/raccourci/sessions.json"}).status_code == 403
    noms = [i["name"] for i in alice.get("/api/fs/list").json()["items"]]
    assert "raccourci" not in noms


def test_session_et_secrets_de_b_hors_de_portee(env):
    """Le scénario complet de l'audit ne mène plus nulle part."""
    alice = env["alice"]
    alice.put("/api/settings", json={"fs_roots": [str(env["tmp"])]})
    r = alice.get("/api/fs/read", params={"path": "r0/profiles/sessions.json"})
    assert r.status_code == 403
    assert "MDP-IMAP-DE-BOB" not in json.dumps(alice.get("/api/settings").json())


def test_calendrier_ne_lit_pas_un_fichier_reserve(env):
    alice = env["alice"]
    cible = env["profils"] / env["pb"]["id"] / "settings.json"
    alice.put("/api/settings", json={"connectors": {"calendar_ics": {
        "enabled": True, "path": str(cible)}}})
    evenements = alice.get("/api/connectors/calendar/preview").json()["events"]
    assert "MDP-IMAP-DE-BOB" not in json.dumps(evenements)
    assert "réservé" in evenements[0]["error"]


# ---------- 2 et 3. Modèle Word : plus d'écriture libre, un modèle par organisation ----------
def test_emplacement_du_modele_n_est_plus_un_reglage(env):
    hors_sandbox = env["tmp"] / "hors_sandbox" / "ecrit_ici.docx"
    r = env["alice"].put("/api/settings", json={"docgen_template_path": str(hors_sandbox)})
    assert r.status_code == 200
    assert "docgen_template_path" not in r.json()
    assert docmodele.chemin_modele(env["pa"]["id"]) == docmodele.chemin_modele_commun()


def test_fabrication_du_modele_reste_dans_l_organisation(env):
    from docx import Document
    Document().save(env["docs_a"] / "source.docx")
    hors_sandbox = env["tmp"] / "hors_sandbox" / "ecrit_ici.docx"
    env["alice"].put("/api/settings", json={"docgen_template_path": str(hors_sandbox)})

    r = env["alice"].post("/api/documents/modele", json={"source": "r0/source.docx"})
    assert r.status_code == 200, r.text
    assert not hors_sandbox.exists()

    propre_a = docmodele.chemin_modele_organisation(env["pa"]["id"])
    assert propre_a.is_file()
    assert propre_a.parent == env["profils"] / env["pa"]["id"]
    assert docmodele.chemin_modele(env["pa"]["id"]) == propre_a
    # B n'est pas touchée : elle garde le modèle commun.
    assert docmodele.chemin_modele(env["pb"]["id"]) == docmodele.chemin_modele_commun()


def test_dossier_modeles_commun_est_reserve():
    assert zones.est_reserve(docmodele.chemin_modele_commun())


# ---------- 4. Moteur OCR : seul un exécutable nommé « tesseract » est accepté ----------
@pytest.mark.parametrize("chemin", ["/bin/sh", "C:/Windows/System32/cmd.exe",
                                    "/usr/bin/python3", "/tmp/tesseract-pas-vraiment"])
def test_chemin_tesseract_quelconque_refuse(env, chemin):
    r = env["alice"].put("/api/settings", json={"ocr_tesseract_path": chemin})
    assert r.status_code == 400
    assert ocr.chemin_tesseract_acceptable(Path(chemin)) is None


def test_chemin_tesseract_legitime_accepte(env):
    exe = env["tmp"] / "Tesseract-OCR" / ocr.NOM_EXE
    exe.parent.mkdir()
    exe.write_bytes(b"")
    for valeur in (str(exe), str(exe.parent), ""):
        r = env["alice"].put("/api/settings", json={"ocr_tesseract_path": valeur})
        assert r.status_code == 200, valeur
        assert r.json()["ocr_tesseract_path"] == valeur


def test_reglage_tesseract_deja_enregistre_n_est_pas_execute(env, monkeypatch):
    # Moteur livré et moteur du PATH absents : seul le réglage compte.
    monkeypatch.setattr(ocr, "_dossier_application", lambda: env["tmp"] / "aucun")
    monkeypatch.setattr(ocr.shutil, "which", lambda _nom: None)
    settings.reglages(env["pa"]["id"]).update({"ocr_tesseract_path": "/bin/sh"})
    assert ocr.chemin_moteur(env["pa"]["id"]) is None


def test_moteur_desinstalle_ne_bloque_pas_l_enregistrement(env):
    dossier = env["tmp"] / "Tesseract-OCR"
    dossier.mkdir()
    alice = env["alice"]
    assert alice.put("/api/settings",
                     json={"ocr_tesseract_path": str(dossier)}).status_code == 200
    dossier.rmdir()                                  # moteur désinstallé
    # L'interface renvoie tous les réglages, ancienne valeur comprise.
    r = alice.put("/api/settings", json={"ocr_tesseract_path": str(dossier), "temperature": 0.5})
    assert r.status_code == 200
    assert r.json()["temperature"] == 0.5
