"""
Lanceur (launch.py) piloté par l'application de bureau.

L'application Electron garde l'entrée standard du backend ouverte et la ferme
pour l'arrêter (--parent-stdin) ; si elle plante, le système ferme le tube. Le
backend — et Ollama avec lui — ne doit jamais survivre à la fenêtre.
"""
import io
import subprocess
import sys
import threading
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))
import launch  # noqa: E402


def test_fin_d_entree_leve_l_arret():
    arret = threading.Event()
    launch.surveiller_parent(io.StringIO("ligne parasite\nautre\n"), arret)
    assert arret.is_set()


def test_entree_ouverte_ne_declenche_rien():
    lecture, ecriture = __import__("os").pipe()
    flux = open(lecture, encoding="utf-8")
    arret = threading.Event()
    fil = threading.Thread(target=launch.surveiller_parent, args=(flux, arret), daemon=True)
    fil.start()
    fil.join(timeout=0.5)
    assert not arret.is_set()                  # tant que le parent tient le tube
    __import__("os").close(ecriture)           # le parent ferme (ou disparaît)
    fil.join(timeout=5)
    assert arret.is_set()


def test_option_parent_stdin_reconnue():
    r = subprocess.run([sys.executable, "launch.py", "--help"], cwd=RACINE,
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and "--parent-stdin" in r.stdout


def test_modeles_ollama_livres_avec_le_moteur(tmp_path, monkeypatch):
    # Disque portable, installeur Inno Setup : modèles livrés dans ./ollama/models.
    livres = tmp_path / "ollama" / "models"
    livres.mkdir(parents=True)
    monkeypatch.setattr(launch, "OLLAMA_MODELS_DIR", livres)
    assert launch.dossier_modeles_ollama() == livres


def test_modeles_ollama_dans_le_dossier_des_donnees(tmp_path, monkeypatch):
    # Application de bureau : moteur embarqué sans modèles ; son dossier
    # d'installation n'est pas modifiable, les modèles vont avec les données.
    from backend import emplacements
    monkeypatch.setattr(launch, "OLLAMA_MODELS_DIR", tmp_path / "absent" / "models")
    monkeypatch.setattr(emplacements, "dossier_donnees", lambda: tmp_path / "donnees")
    assert launch.dossier_modeles_ollama() == tmp_path / "donnees" / "modeles-ia"
