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


def test_toutes_les_commandes_de_comptes_sont_relayees():
    """Chaque sous-commande de manage_users.py doit passer par le lanceur, seul
    point d'entrée sur un poste installé (ai-webapp.exe <commande>)."""
    from backend import manage_users
    vues = manage_users.sous_commandes()
    assert "init" in vues and "set-role" in vues
    assert vues <= launch.COMMANDES_COMPTES, vues - launch.COMMANDES_COMPTES


def test_modeles_ollama_livres_avec_le_moteur(tmp_path, monkeypatch):
    # Disque portable : modèles livrés dans ./ollama/models.
    from backend import emplacements
    livres = tmp_path / "ollama" / "models"
    livres.mkdir(parents=True)
    monkeypatch.setattr(launch, "OLLAMA_MODELS_DIR", livres)
    monkeypatch.setattr(emplacements, "dossier_modeles_ini", lambda: None)
    assert launch.dossier_modeles_ollama() == livres


def test_modeles_ollama_designes_par_l_installeur(tmp_path, monkeypatch):
    """Installeur Inno Setup : olivia.iss range les modèles dans un dossier
    commun inscriptible (clé `modeles` de olivia.ini), prioritaire sur
    ./ollama/models, qui serait sous Program Files."""
    from backend import emplacements
    app = tmp_path / "app"
    app.mkdir()
    (app / emplacements.NOM_INI).write_text(
        f"[{emplacements.SECTION_INI}]\n{emplacements.CLE_INI_MODELES}={tmp_path / 'commun'}\n",
        encoding="utf-8")
    monkeypatch.setattr(emplacements, "dossier_application", lambda: app)
    livres = tmp_path / "ollama" / "models"
    livres.mkdir(parents=True)
    monkeypatch.setattr(launch, "OLLAMA_MODELS_DIR", livres)
    assert launch.dossier_modeles_ollama() == tmp_path / "commun"


def test_ollama_toujours_limite_au_poste(tmp_path, monkeypatch):
    """Un OLLAMA_HOST=0.0.0.0 hérité du poste ne doit pas exposer le moteur."""
    monkeypatch.setenv("OLLAMA_HOST", "0.0.0.0:11434")
    exe = tmp_path / "ollama.exe"
    exe.write_text("", encoding="utf-8")
    monkeypatch.setattr(launch, "OLLAMA_EXE", exe)
    monkeypatch.setattr(launch, "port_is_open", lambda *a, **k: False)
    monkeypatch.setattr(launch, "wait_for_port", lambda *a, **k: True)
    monkeypatch.setattr(launch, "bind_child", lambda proc: None)
    monkeypatch.setattr(launch, "dossier_modeles_ollama", lambda: tmp_path / "modeles")
    vu = {}

    def faux_popen(args, env=None, **kw):
        vu["env"] = env
        return object()

    monkeypatch.setattr(launch.subprocess, "Popen", faux_popen)
    launch.start_ollama()
    assert vu["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"


def test_modeles_ollama_dans_le_dossier_des_donnees(tmp_path, monkeypatch):
    # Application de bureau : moteur embarqué sans modèles ; son dossier
    # d'installation n'est pas modifiable, les modèles vont avec les données.
    from backend import emplacements
    monkeypatch.setattr(launch, "OLLAMA_MODELS_DIR", tmp_path / "absent" / "models")
    monkeypatch.setattr(emplacements, "dossier_modeles_ini", lambda: None)
    monkeypatch.setattr(emplacements, "dossier_donnees", lambda: tmp_path / "donnees")
    assert launch.dossier_modeles_ollama() == tmp_path / "donnees" / "modeles-ia"
