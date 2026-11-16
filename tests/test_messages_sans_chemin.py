"""
Messages d'erreur des routes de fichiers : jamais un chemin du disque.

Ces routes sont ouvertes à tout compte de l'organisation, membre compris. Leurs
erreurs recopiaient pourtant le chemin complet du fichier (« Fichier
introuvable : C:\\… »), celui du dossier de travail (« … sort du périmètre
autorisé (C:\\…) ») ou le texte brut d'une exception système, qui le contient
(« [Errno 13] Permission denied: 'C:\\…' »). Un membre y lisait l'arborescence
du poste (corrigé le 16/11/2026). Les messages citent désormais le chemin
VIRTUEL (`r0/…`) envoyé par l'interface, ou rien.
"""
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import docgen, docmodele, main, profiles, sessions, settings, users, zones

SECRET = "Arborescence-secrete"


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    docs = tmp_path / SECRET / "Compta"
    docs.mkdir(parents=True)
    (docs / "bilan.txt").write_text("bilan de l'année", encoding="utf-8")
    pid = profiles.create_profile("Org")["id"]
    users.create_user("rachel", "Secret-01", pid)          # premier : responsable
    users.create_user("marc", "Secret-02", pid)            # suivant : membre
    rachel, marc = TestClient(main.app), TestClient(main.app)
    assert rachel.post("/api/auth/login",
                       json={"username": "rachel", "password": "Secret-01"}).status_code == 200
    assert marc.post("/api/auth/login",
                     json={"username": "marc", "password": "Secret-02"}).status_code == 200
    assert rachel.put("/api/settings", json={"fs_roots": [str(docs)]}).status_code == 200
    # Le serveur ne doit pas lever : on veut lire ses réponses d'erreur.
    rachel = TestClient(main.app, raise_server_exceptions=False, cookies=rachel.cookies)
    marc = TestClient(main.app, raise_server_exceptions=False, cookies=marc.cookies)
    yield {"rachel": rachel, "marc": marc, "docs": docs}
    zones.dossiers_reserves.cache_clear()


def _sans_chemin(reponse) -> None:
    assert SECRET not in reponse.text, reponse.text


@pytest.mark.parametrize("route", ["/api/fs/read", "/api/fs/preview", "/api/fs/text",
                                   "/api/fs/download"])
def test_fichier_introuvable_cite_le_chemin_virtuel(env, route):
    r = env["marc"].get(route, params={"path": "r0/absent.txt"})
    assert r.status_code == 404
    assert "r0/absent.txt" in r.json()["detail"]
    _sans_chemin(r)


def test_sortie_du_perimetre_ne_cite_pas_le_dossier_de_travail(env):
    r = env["marc"].get("/api/fs/read", params={"path": "r0/../../.."})
    assert r.status_code == 403
    _sans_chemin(r)


def _erreur_systeme(chemin):
    """Exception système comme Windows la produit : elle cite le chemin."""
    def lever(*_a, **_k):
        raise PermissionError(13, "Permission denied", str(chemin))
    return lever


def test_lecture_en_echec_sans_texte_d_exception(env, monkeypatch):
    monkeypatch.setattr(Path, "read_text", _erreur_systeme(env["docs"] / "bilan.txt"))
    r = env["marc"].get("/api/fs/read", params={"path": "r0/bilan.txt"})
    assert r.status_code == 500
    _sans_chemin(r)


def test_import_en_echec_sans_texte_d_exception(env, monkeypatch):
    monkeypatch.setattr(main, "_ouvrir_fichier_neuf", _erreur_systeme(env["docs"] / "x.txt"))
    r = env["marc"].post("/api/fs/upload", params={"path": "r0"},
                         files={"file": ("x.txt", io.BytesIO(b"x"), "text/plain")})
    assert r.status_code == 500
    _sans_chemin(r)


def test_creation_de_document_en_echec_sans_texte_d_exception(env, monkeypatch):
    monkeypatch.setattr(docgen, "generer", _erreur_systeme(env["docs"] / "doc.docx"))
    r = env["marc"].post("/api/documents/generate",
                         json={"type": "circulaire", "titre": "Essai", "texte": "Bonjour."})
    assert r.status_code == 500
    _sans_chemin(r)


def test_modele_word_en_echec_sans_texte_d_exception(env, monkeypatch):
    (env["docs"] / "modele.docx").write_bytes(b"pas un vrai docx")
    monkeypatch.setattr(docmodele, "construire_modele",
                        _erreur_systeme(env["docs"] / "modele.docx"))
    r = env["rachel"].post("/api/documents/modele", json={"source": "r0/modele.docx"})
    assert r.status_code == 500
    _sans_chemin(r)


def test_modele_word_illisible_sans_chemin(env, tmp_path):
    """Les messages de docmodele remontent tels quels à l'interface (400)."""
    source = env["docs"] / "abime.docx"
    source.write_bytes(b"pas un vrai docx")
    for chemin in (source, env["docs"] / "absent.docx"):
        with pytest.raises(ValueError) as erreur:
            docmodele.construire_modele(chemin, destination=tmp_path / "sortie.docx")
        assert SECRET not in str(erreur.value), str(erreur.value)
