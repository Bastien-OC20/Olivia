"""
Création des comptes sur une installation neuve (audit, point 5).

Une installation neuve démarre sans aucun compte (build.spec n'embarque pas
backend/profiles/) alors que la connexion est obligatoire. Ces tests vérifient
que l'exécutable lui-même permet de créer le premier compte (`init`, relayé par
launch.py), que le mot de passe n'a plus à passer en argument, et que l'écran de
connexion sait qu'aucun compte n'existe.

Tout se passe dans un dossier temporaire : rien n'est écrit dans
backend/profiles/ du dépôt.
"""
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend import main, manage_users, profiles, sessions, settings, users

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
import launch  # noqa: E402


@pytest.fixture
def stockage(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    return dossier


def _clavier(monkeypatch, lignes, mots_de_passe):
    """Simule les saisies : `input` pour les lignes, `getpass` pour les mots de passe."""
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


def _connexion(identifiant, mot_de_passe):
    return TestClient(main.app).post(
        "/api/auth/login", json={"username": identifiant, "password": mot_de_passe})


# ---------- L'écran de connexion sait qu'aucun compte n'existe ----------
def test_etat_sans_compte_puis_avec(stockage):
    client = TestClient(main.app)
    assert client.get("/api/auth/etat").json() == {"comptes": False}
    pid = profiles.create_profile("Org")["id"]
    assert client.get("/api/auth/etat").json() == {"comptes": False}   # profil seul
    users.create_user("marie", "secret1", pid)
    assert client.get("/api/auth/etat").json() == {"comptes": True}


def test_etat_fichier_illisible_n_invite_pas_a_creer(stockage):
    stockage.mkdir(parents=True)
    (stockage / "users.json").write_text("{pas du json", encoding="utf-8")
    assert TestClient(main.app).get("/api/auth/etat").json() == {"comptes": None}


# ---------- Assistant `init` ----------
def test_init_installation_neuve(stockage, monkeypatch, capsys):
    _clavier(monkeypatch, ["Lycée de l'Olivier", "marie"], ["secret1", "secret1"])
    assert manage_users.main(["init"]) == 0
    noms = [p["name"] for p in profiles.list_profiles()]
    assert noms == ["Lycée de l'Olivier"]
    assert _connexion("marie", "secret1").status_code == 200
    assert "Compte « marie » créé" in capsys.readouterr().out


def test_init_abandon_ne_laisse_aucune_organisation_vide(stockage, monkeypatch):
    # Mot de passe confirmé de travers trois fois : abandon.
    _clavier(monkeypatch, ["Org fantôme", "marie"],
             ["secret1", "autre1"] * manage_users.ESSAIS_MOT_DE_PASSE)
    assert manage_users.main(["init"]) == 1
    assert profiles.list_profiles() == []
    assert not users.existe_un_compte()


def test_init_rattache_a_une_organisation_existante(stockage, monkeypatch):
    org = profiles.create_profile("Mairie")
    users.create_user("paul", "secret1", org["id"])
    # « x » : choix invalide ; « paul » : déjà pris ; « abc » : mot de passe trop court.
    _clavier(monkeypatch, ["x", "1", "paul", "julie"], ["abc", "secret2", "secret2"])
    assert manage_users.main(["init"]) == 0
    assert len(profiles.list_profiles()) == 1          # aucune organisation ajoutée
    julie = users.get_user_by_username("julie")
    assert julie["profile_id"] == org["id"]
    assert _connexion("julie", "secret2").status_code == 200


# ---------- create-user : mot de passe demandé, plus en argument ----------
def test_create_user_demande_le_mot_de_passe(stockage, monkeypatch):
    pid = profiles.create_profile("Org")["id"]
    _clavier(monkeypatch, [], ["secret1", "secret1"])
    assert manage_users.main(["create-user", "marie", pid]) == 0
    assert _connexion("marie", "secret1").status_code == 200


def test_create_user_profil_inconnu_avant_toute_saisie(stockage, monkeypatch):
    _clavier(monkeypatch, [], [])          # aucune saisie ne doit être demandée
    assert manage_users.main(["create-user", "marie", "0" * 32]) == 1
    assert not users.existe_un_compte()


def test_create_user_ancienne_forme_acceptee_avec_avertissement(stockage, capsys):
    pid = profiles.create_profile("Org")["id"]
    assert manage_users.main(["create-user", "marie", "secret1", pid]) == 0
    assert "historique du terminal" in capsys.readouterr().err
    assert _connexion("marie", "secret1").status_code == 200


# ---------- Relais par le lanceur (ai-webapp.exe init) ----------
def test_lanceur_relaie_les_commandes_sans_rien_demarrer(stockage, monkeypatch):
    def _interdit(*_a, **_k):
        raise AssertionError("une commande de comptes ne doit rien démarrer")
    monkeypatch.setattr(launch, "start_ollama", _interdit)
    monkeypatch.setattr(launch, "run_source", _interdit)
    monkeypatch.setattr(launch, "run_frozen", _interdit)
    _clavier(monkeypatch, ["Org", "marie"], ["secret1", "secret1"])
    monkeypatch.setattr(sys, "argv", ["launch.py", "init"])
    assert launch.main() == 0
    assert _connexion("marie", "secret1").status_code == 200
