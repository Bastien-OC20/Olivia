"""
Emplacement des données hors du dossier de l'application (audit, point 6).

Sur un poste installé, l'application est dans Program Files, qu'un utilisateur
standard ne peut pas modifier : les données doivent vivre ailleurs — dans le
profil du compte Windows (%LOCALAPPDATA%\\Olivia, désigné par olivia.ini), et
plus dans C:\\ProgramData\\Olivia, commun au poste et ouvert à tous ses comptes
(audit du 15/11/2026). Sur un disque portable et en développement, rien ne change.

Les vérifications qui demandent un nouveau process (chemins calculés au
chargement des modules) passent par un sous-process Python : le process de test
garde ses propres chemins, et rien n'est écrit dans backend/profiles/ du dépôt.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import emplacements, main, sessions

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture
def sans_reglage(monkeypatch, tmp_path):
    """Ni variable d'environnement, ni olivia.ini (application dans tmp_path/app)."""
    monkeypatch.delenv(emplacements.VARIABLE_ENV, raising=False)
    app = tmp_path / "app"
    app.mkdir()
    monkeypatch.setattr(emplacements, "dossier_application", lambda: app)
    return app


def _ini(app: Path, dossier: str, encodage: str = "utf-8") -> None:
    (app / emplacements.NOM_INI).write_text(
        f"[{emplacements.SECTION_INI}]\n{emplacements.CLE_INI}={dossier}\n", encoding=encodage)


# ---------- Choix de l'emplacement ----------
def test_par_defaut_les_donnees_restent_dans_backend(sans_reglage):
    # Disque portable et développement : aucun changement d'emplacement.
    assert emplacements.dossier_donnees() == emplacements.DOSSIER_BACKEND


def test_olivia_ini_designe_le_dossier(sans_reglage, tmp_path):
    cible = tmp_path / "ProgramData" / "Olivia"
    _ini(sans_reglage, str(cible), encodage="utf-8-sig")    # BOM accepté
    assert emplacements.dossier_donnees() == cible
    assert "installation" in emplacements.description()


def test_variable_d_environnement_prioritaire(sans_reglage, tmp_path, monkeypatch):
    _ini(sans_reglage, str(tmp_path / "depuis-ini"))
    monkeypatch.setenv(emplacements.VARIABLE_ENV, str(tmp_path / "depuis-env"))
    assert emplacements.dossier_donnees() == tmp_path / "depuis-env"


def test_ini_illisible_retombe_sur_le_defaut(sans_reglage):
    (sans_reglage / emplacements.NOM_INI).write_text("pas un ini [[[", encoding="utf-8")
    assert emplacements.dossier_donnees() == emplacements.DOSSIER_BACKEND


# ---------- Migration depuis l'ancien emplacement (Program Files) ----------
def _anciens_profils(dossier: Path) -> None:
    (dossier / "abc").mkdir(parents=True)
    (dossier / "registry.json").write_text('{"profiles": []}', encoding="utf-8")
    (dossier / "users.json").write_text('{"users": [{"id": "u"}]}', encoding="utf-8")
    (dossier / "abc" / "settings.json").write_text("{}", encoding="utf-8")


def test_migration_recopie_sans_toucher_l_ancien(tmp_path):
    ancien, nouveau = tmp_path / "ancien", tmp_path / "data" / "profiles"
    _anciens_profils(ancien)
    assert emplacements.migrer_ancien_dossier(ancien, nouveau) is True
    assert json.loads((nouveau / "users.json").read_text())["users"][0]["id"] == "u"
    assert (nouveau / "abc" / "settings.json").is_file()
    assert (ancien / "users.json").is_file()                 # copie, pas déplacement
    assert not (tmp_path / "data" / "profiles.migration").exists()


def test_migration_n_ecrase_jamais_le_nouvel_emplacement(tmp_path):
    ancien, nouveau = tmp_path / "ancien", tmp_path / "data" / "profiles"
    _anciens_profils(ancien)
    nouveau.mkdir(parents=True)
    (nouveau / "users.json").write_text('{"users": []}', encoding="utf-8")
    assert emplacements.migrer_ancien_dossier(ancien, nouveau) is False
    assert json.loads((nouveau / "users.json").read_text()) == {"users": []}


def test_migration_ignoree_sans_ancien_registre(tmp_path):
    assert emplacements.migrer_ancien_dossier(tmp_path / "rien", tmp_path / "n") is False
    assert not (tmp_path / "n").exists()


def test_migration_reprend_apres_interruption(tmp_path):
    ancien, nouveau = tmp_path / "ancien", tmp_path / "data" / "profiles"
    _anciens_profils(ancien)
    reste = tmp_path / "data" / "profiles.migration"
    reste.mkdir(parents=True)
    (reste / "a-moitie.json").write_text("{", encoding="utf-8")
    assert emplacements.migrer_ancien_dossier(ancien, nouveau) is True
    assert not (nouveau / "a-moitie.json").exists()
    assert (nouveau / "users.json").is_file()


# ---------- Reprise de l'ancien dossier commun au poste ----------
def _ancien_commun(racine: Path) -> None:
    _anciens_profils(racine / "profiles")
    (racine / "ocr_cache").mkdir()
    (racine / "ocr_cache" / "abc.json").write_text('{"texte": "bulletin"}', encoding="utf-8")
    (racine / "modeles-ia").mkdir()
    (racine / "modeles-ia" / "blob").write_text("poids", encoding="utf-8")


def test_reprise_deplace_les_donnees_hors_du_dossier_commun(tmp_path):
    """Comptes, sessions et conversations ne doivent plus rester lisibles par
    les autres comptes Windows : ils sont repris PUIS retirés de l'ancien
    dossier. Les modèles d'IA, eux, restent partagés."""
    commun, perso = tmp_path / "ProgramData" / "Olivia", tmp_path / "Local" / "Olivia"
    _ancien_commun(commun)
    assert emplacements.reprendre_dossier_commun(commun, perso) is True
    assert json.loads((perso / "profiles" / "users.json").read_text())["users"][0]["id"] == "u"
    assert (perso / "profiles" / "abc" / "settings.json").is_file()
    assert not (commun / "profiles").exists()
    assert not (commun / "ocr_cache").exists()
    assert (commun / "modeles-ia" / "blob").is_file()


def test_reprise_ne_touche_a_rien_si_le_compte_a_deja_ses_donnees(tmp_path):
    """Le second compte Windows du poste a déjà son dossier : il ne reprend
    rien, n'écrase rien, et ne vide pas l'ancien dossier d'un autre."""
    commun, perso = tmp_path / "commun", tmp_path / "perso"
    _ancien_commun(commun)
    (perso / "profiles").mkdir(parents=True)
    (perso / "profiles" / "users.json").write_text('{"users": []}', encoding="utf-8")
    assert emplacements.reprendre_dossier_commun(commun, perso) is False
    assert json.loads((perso / "profiles" / "users.json").read_text()) == {"users": []}
    assert (commun / "profiles" / "users.json").is_file()


def test_reprise_sans_ancien_dossier(tmp_path):
    assert emplacements.reprendre_dossier_commun(tmp_path / "rien", tmp_path / "perso") is False
    assert not (tmp_path / "perso").exists()


def test_ancien_dossier_designe_par_la_variable_ou_par_olivia_ini(
        sans_reglage, tmp_path, monkeypatch):
    monkeypatch.delenv(emplacements.VARIABLE_REPRISE, raising=False)
    assert emplacements.ancien_dossier_commun() is None
    (sans_reglage / emplacements.NOM_INI).write_text(
        f"[{emplacements.SECTION_INI}]\n{emplacements.CLE_INI}={tmp_path / 'perso'}\n"
        f"{emplacements.CLE_INI_REPRISE}={tmp_path / 'commun'}\n", encoding="utf-8")
    assert emplacements.ancien_dossier_commun() == tmp_path / "commun"
    monkeypatch.setenv(emplacements.VARIABLE_REPRISE, str(tmp_path / "autre"))
    assert emplacements.ancien_dossier_commun() == tmp_path / "autre"


# ---------- Bout en bout, dans un process neuf ----------
def _python(code: str, env_extra: dict) -> str:
    env = {**os.environ, **env_extra}
    r = subprocess.run([sys.executable, "-c", code], cwd=RACINE, env=env,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_tous_les_chemins_suivent_le_dossier_des_donnees(tmp_path):
    sortie = _python(
        "import json; from backend import profiles, ocr, users, sessions, zones;"
        "print(json.dumps([str(profiles.PROFILES_DIR), str(ocr.DOSSIER_CACHE),"
        " str(users.USERS_PATH), str(sessions.SESSIONS_PATH),"
        " zones.est_reserve(profiles.PROFILES_DIR.parent)]))",
        {emplacements.VARIABLE_ENV: str(tmp_path / "data")})
    profils, cache, comptes, sess, reserve = json.loads(sortie)
    data = tmp_path / "data"
    assert Path(profils) == data / "profiles"
    assert Path(cache) == data / "ocr_cache"
    assert Path(comptes) == data / "profiles" / "users.json"
    assert Path(sess) == data / "profiles" / "sessions.json"
    assert reserve is True                      # le dossier des données est réservé


def test_reprise_au_demarrage_dans_un_process_neuf(tmp_path):
    """L'application de bureau désigne l'ancien dossier commun par
    OLIVIA_DATA_REPRISE : au chargement du backend, les comptes sont dans le
    dossier du compte Windows et plus dans l'ancien."""
    commun, perso = tmp_path / "commun", tmp_path / "perso"
    _ancien_commun(commun)
    sortie = _python(
        "from backend import users; print(users.existe_un_compte())",
        {emplacements.VARIABLE_ENV: str(perso), emplacements.VARIABLE_REPRISE: str(commun)})
    assert sortie == "True"
    assert (perso / "profiles" / "users.json").is_file()
    assert not (commun / "profiles").exists()


def test_creation_de_compte_ecrit_dans_le_dossier_des_donnees(tmp_path):
    data = tmp_path / "data"
    env = {**os.environ, emplacements.VARIABLE_ENV: str(data)}
    r = subprocess.run([sys.executable, "launch.py", "create-profile", "Org"], cwd=RACINE,
                       env=env, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    registre = json.loads((data / "profiles" / "registry.json").read_text(encoding="utf-8"))
    assert [p["name"] for p in registre["profiles"]] == ["Org"]


# ---------- Dossier non modifiable : message clair à la connexion ----------
def test_connexion_explique_un_dossier_non_modifiable(monkeypatch):
    monkeypatch.setattr(main.users, "verify_credentials",
                        lambda u, p: {"id": "u" * 32, "profile_id": "p" * 32})

    def _refus(*_a, **_k):
        raise PermissionError("Accès refusé")
    monkeypatch.setattr(sessions, "create_session", _refus)
    r = TestClient(main.app).post("/api/auth/login",
                                  json={"username": "marie", "password": "x"})
    assert r.status_code == 500
    assert "pas modifiable" in r.json()["detail"]
