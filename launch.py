"""
Lanceur multi-plateforme du projet Olivia (assistante locale).

Deux modes :
  1) MODE SOURCE (python launch.py) — développement :
     - Crée le venv backend si nécessaire et installe les dépendances
     - Démarre FastAPI (uvicorn en sous-process, avec --reload)
     - Démarre Vite en parallèle si node_modules est présent
     - Ouvre le navigateur sur l'UI

  2) MODE GELÉ (.exe PyInstaller) — production :
     - AUCUN venv/pip (les dépendances sont embarquées dans le binaire)
     - Démarre FastAPI EN INTERNE (uvicorn.run dans ce process)
     - Sert l'UI buildée sous /ui, ouvre le navigateur

Usage :
  python launch.py                  # dev (Vite + FastAPI)
  python launch.py --no-dev         # backend seul, UI buildée sur /ui
  python launch.py --no-browser     # ne pas ouvrir le navigateur
  python launch.py --port 9000      # changer le port backend

Comptes (service informatique) — n'importe quel mode, sans rien démarrer :
  ai-webapp.exe init                # assistant : organisation + compte
  ai-webapp.exe create-user <identifiant> <profile_id>
  ai-webapp.exe list-profiles
  (python launch.py init, etc. depuis le dépôt source)
"""
import argparse
import os
import socket
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
SRC_ROOT = Path(__file__).resolve().parent
BACKEND_DIR = (ROOT if FROZEN else SRC_ROOT) / "backend"
FRONTEND_DIR = SRC_ROOT / "frontend"
IS_WINDOWS = sys.platform.startswith("win")

# Ollama portable installé DANS le projet (à côté de launch.py ou de l'.exe).
APP_DIR = Path(sys.executable).resolve().parent if FROZEN else SRC_ROOT
OLLAMA_DIR = APP_DIR / "ollama"
OLLAMA_EXE = OLLAMA_DIR / ("ollama.exe" if IS_WINDOWS else "ollama")
OLLAMA_MODELS_DIR = OLLAMA_DIR / "models"


def port_is_open(host: str, port: int, timeout: float = 0.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, ConnectionRefusedError):
        return False


def wait_for_port(host: str, port: int, max_wait: int = 30) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        if port_is_open(host, port):
            return True
        time.sleep(0.3)
    return False


# ---------------------------------------------------------- fermeture liée (Windows)
# Job Object avec KILL_ON_JOB_CLOSE : tous les processus enfants (Ollama, uvicorn,
# Vite) y sont rattachés. Si CE processus meurt — même tué brutalement — l'OS ferme
# le handle du job et tue toute la descendance. Aucun orphelin possible.
_JOB = None


def _create_job():
    if not IS_WINDOWS:
        return None
    import ctypes
    from ctypes import wintypes

    class _BasicLimits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", wintypes.LARGE_INTEGER),
            ("PerJobUserTimeLimit", wintypes.LARGE_INTEGER),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

    class _ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _BasicLimits),
            ("IoInfo", _IoCounters),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    KILL_ON_JOB_CLOSE = 0x2000
    EXTENDED_LIMIT_INFO = 9
    k32 = ctypes.windll.kernel32
    job = k32.CreateJobObjectW(None, None)
    if not job:
        return None
    info = _ExtendedLimits()
    info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(job, EXTENDED_LIMIT_INFO,
                                       ctypes.byref(info), ctypes.sizeof(info)):
        k32.CloseHandle(job)
        return None
    return job


def bind_child(proc: subprocess.Popen | None) -> None:
    """Rattache un processus enfant au job 'fermeture liée' (no-op hors Windows)."""
    global _JOB
    if proc is None or not IS_WINDOWS:
        return
    if _JOB is None:
        _JOB = _create_job()
    if not _JOB:
        return
    import ctypes
    handle = getattr(proc, "_handle", None)
    if handle is None:
        return
    try:
        ctypes.windll.kernel32.AssignProcessToJobObject(_JOB, int(handle))
    except Exception:
        pass  # best effort : le terminate() explicite reste le filet de sécurité


def dossier_modeles_ollama() -> Path:
    """Où le moteur embarqué range ses modèles (plusieurs Go).

    1. ./ollama/models s'il existe : disque portable et installeur Inno Setup,
       qui livrent les modèles avec le moteur ;
    2. sinon le dossier des données d'Oliv'IA (backend/emplacements.py),
       sous-dossier modeles-ia : c'est le cas de l'application de bureau, qui
       embarque le moteur SANS les modèles (téléchargés au premier lancement,
       depuis Oliv'IA). Son dossier d'installation (Program Files, Olivia.app)
       n'est pas modifiable par un utilisateur standard et serait remplacé à
       chaque mise à jour : les modèles n'y survivraient pas.
    """
    if OLLAMA_MODELS_DIR.is_dir():
        return OLLAMA_MODELS_DIR
    sys.path.insert(0, str(ROOT if FROZEN else SRC_ROOT))   # rend 'backend' importable
    from backend import emplacements
    return emplacements.dossier_donnees() / "modeles-ia"


def start_ollama():
    """Démarre le moteur Ollama portable (livré à côté de l'exécutable).

    - S'il tourne déjà sur :11434, on le réutilise.
    - Sinon, si ./ollama/ollama(.exe) existe, on le lance ; ses modèles vont
      dans le dossier donné par dossier_modeles_ollama(), sauf variable
      d'environnement OLLAMA_MODELS déjà définie.
    - Sinon, on avertit et l'app démarre quand même (sans inférence).
    Renvoie le sous-process démarré (à arrêter en sortie) ou None.
    """
    if port_is_open("127.0.0.1", 11434):
        print("✅ Ollama déjà démarré sur :11434 — réutilisé.")
        return None
    if not OLLAMA_EXE.exists():
        print("⚠️  Ollama introuvable dans ./ollama — aucune inférence possible.")
        print("   Installez la version portable dans ce dossier, ou lancez 'ollama serve'.")
        return None

    env = os.environ.copy()
    modeles = Path(env.get("OLLAMA_MODELS") or dossier_modeles_ollama())
    try:
        modeles.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"⚠️  Dossier des modèles inaccessible ({modeles}) : {e}")
    env["OLLAMA_MODELS"] = str(modeles)
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    print(f"→ Démarrage d'Ollama (portable) — modèles : {modeles}")
    proc = subprocess.Popen(
        [str(OLLAMA_EXE), "serve"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    bind_child(proc)  # fermeture liée : Ollama meurt avec le lanceur
    if wait_for_port("127.0.0.1", 11434, 20):
        print("✅ Ollama opérationnel sur :11434")
    else:
        print("⚠️  Ollama n'a pas répondu à temps — l'app démarre quand même.")
    return proc


def open_browser(url: str) -> None:
    print(f"→ Ouverture du navigateur : {url}")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"⚠️  Ouverture du navigateur échouée : {e}")


# ---------------------------------------------------------------- mode GELÉ (.exe)
def run_frozen(args) -> int:
    """Démarre uvicorn dans ce process — pas de venv, tout est embarqué."""
    sys.path.insert(0, str(BACKEND_DIR))          # rend 'backend' importable
    sys.path.insert(0, str(ROOT))
    import threading
    import uvicorn

    ui_url = f"http://{args.host}:{args.port}/ui/"

    def _serve():
        # On importe le package pour respecter les imports relatifs (from .settings ...).
        uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)

    server_thread = threading.Thread(target=_serve, daemon=True)
    server_thread.start()

    if not wait_for_port(args.host, args.port, args.max_wait):
        print(f"❌ Backend pas prêt après {args.max_wait}s — abandon.")
        return 1
    print(f"✅ Backend opérationnel sur http://{args.host}:{args.port}")
    if not args.no_browser:
        time.sleep(0.5)
        open_browser(ui_url)
    arret = threading.Event()
    if args.parent_stdin:
        # Lancé par l'application de bureau (desktop/main.js) : elle garde notre
        # entrée standard ouverte et la ferme pour nous arrêter. Si elle plante,
        # le système ferme le tube aussi : le backend — et Ollama, arrêté par le
        # `finally` de main() — ne survivent jamais à la fenêtre.
        threading.Thread(target=surveiller_parent, args=(sys.stdin, arret),
                         daemon=True).start()
    else:
        print("\n⏹  Fermez cette fenêtre pour arrêter le serveur.\n")
    try:
        while server_thread.is_alive() and not arret.is_set():
            server_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\n→ Arrêt demandé.")
    if arret.is_set():
        print("→ Application de bureau fermée : arrêt.")
    return 0


def surveiller_parent(flux, arret) -> None:
    """Lit `flux` jusqu'à sa fin, puis lève `arret`.

    La fin de flux (EOF) signifie que le processus parent a fermé le tube ou a
    disparu. Lire ligne à ligne plutôt qu'un `read()` global : rien n'est
    attendu sur ce canal, seule sa fermeture compte, et une ligne parasite ne
    doit pas l'arrêter.
    """
    try:
        for _ligne in flux:
            pass
    except (OSError, ValueError):
        pass
    arret.set()


# ------------------------------------------------------------- comptes (service informatique)
# Sous-commandes de backend/manage_users.py, relayées par le lanceur. Raison :
# une installation neuve (installeur, disque portable) démarre SANS aucun compte,
# puisque build.spec exclut backend/profiles/ du binaire — et l'écran de
# connexion est obligatoire. Sans ce relais, le seul moyen de créer un compte
# était de lancer manage_users.py depuis le dépôt source, qui écrit dans le
# backend/profiles/ du dépôt et non dans celui de l'installation : une
# installation neuve était inutilisable. Passer par l'exécutable lui-même
# garantit d'écrire au bon endroit (_internal/backend/profiles/ en mode gelé).
COMMANDES_COMPTES = {"init", "create-profile", "create-user", "list-profiles"}


def run_comptes(argv: list[str]) -> int:
    """Exécute une commande de comptes, sans démarrer ni Ollama ni le serveur."""
    sys.path.insert(0, str(ROOT if FROZEN else SRC_ROOT))   # rend 'backend' importable
    from backend import manage_users
    prog = Path(sys.executable).name if FROZEN else "python launch.py"
    code = manage_users.main(argv, prog=prog)
    # Ouvert dans sa propre fenêtre par l'application de bureau (menu « Créer un
    # compte… ») : sans cette pause, la fenêtre se fermerait aussitôt l'assistant
    # terminé, avant qu'on ait pu lire son compte rendu.
    if os.environ.get("OLIVIA_PAUSE_FIN") == "1":
        try:
            input("\nAppuyez sur Entrée pour fermer cette fenêtre…")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


def verifier_dossier_donnees() -> bool:
    """Affiche où sont les données et vérifie qu'on peut y écrire.

    Sur un poste installé, les données vivent dans C:\\ProgramData\\Olivia et non
    dans Program Files (voir backend/emplacements.py). Si ce dossier n'est pas
    modifiable, chaque connexion échouera : mieux vaut le dire ici, en clair,
    que laisser l'utilisatrice face à un écran de connexion qui refuse tout.
    N'empêche pas le démarrage — le message d'erreur de la connexion le redit.
    """
    sys.path.insert(0, str(ROOT if FROZEN else SRC_ROOT))   # rend 'backend' importable
    from backend import emplacements
    print(f"→ Données : {emplacements.description()}")
    dossier = emplacements.dossier_donnees()
    essai = dossier / ".olivia-essai-ecriture"
    try:
        dossier.mkdir(parents=True, exist_ok=True)
        essai.write_text("ok", encoding="utf-8")
        essai.unlink()
        return True
    except OSError as e:
        print(f"❌ Impossible d'écrire dans le dossier des données ({e}).")
        print("   Les connexions échoueront. Le service informatique doit donner le droit")
        print(f"   de modification sur {dossier} aux utilisateurs du poste,")
        print("   ou réinstaller Oliv'IA avec l'installeur.")
        return False


# ------------------------------------------------------------- mode SOURCE (dev)
def find_venv_python() -> str | None:
    candidate = (BACKEND_DIR / ".venv" / ("Scripts" if IS_WINDOWS else "bin")
                 / ("python.exe" if IS_WINDOWS else "python"))
    return str(candidate) if candidate.exists() else None


def ensure_venv() -> str:
    py = find_venv_python()
    if py:
        return py
    print("→ Création de l'environnement virtuel backend/.venv ...")
    subprocess.run([sys.executable, "-m", "venv", str(BACKEND_DIR / ".venv")], check=True)
    py = find_venv_python()
    print("→ Installation des dépendances backend ...")
    subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
    subprocess.run(
        [py, "-m", "pip", "install", "--quiet", "-r", str(BACKEND_DIR / "requirements.txt")],
        check=True,
    )
    return py


def start_backend(host: str, port: int) -> subprocess.Popen:
    py = ensure_venv()
    print(f"→ Démarrage du backend FastAPI sur {host}:{port} ...")
    # Lancé depuis la RACINE en ciblant 'backend.main:app' pour que les imports
    # relatifs du package (from .settings ...) fonctionnent.
    proc = subprocess.Popen(
        [py, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port), "--reload"],
        cwd=str(SRC_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    bind_child(proc)
    return proc


def start_npm_dev() -> subprocess.Popen | None:
    if not (FRONTEND_DIR / "node_modules").exists():
        print("⚠️  frontend/node_modules absent — exécutez d'abord : cd frontend && npm install")
        return None
    print("→ Démarrage de Vite (UI mode dev) ...")
    npm = "npm.cmd" if IS_WINDOWS else "npm"
    proc = subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    bind_child(proc)
    return proc


def stream_output(proc: subprocess.Popen, prefix: str = "") -> None:
    if proc.stdout is None:
        return
    for line in proc.stdout:
        print(f"{prefix}{line.rstrip()}")


def run_source(args) -> int:
    backend_proc = start_backend(args.host, args.port)
    vite_proc = None
    try:
        if not wait_for_port(args.host, args.port, args.max_wait):
            print(f"❌ Backend pas prêt après {args.max_wait}s — abandon.")
            return 1
        print(f"✅ Backend opérationnel sur http://{args.host}:{args.port}")

        ui_url = f"http://{args.host}:{args.port}/ui/"
        if not args.no_dev:
            vite_proc = start_npm_dev()
            if vite_proc and wait_for_port("127.0.0.1", 5173, 20):
                ui_url = "http://127.0.0.1:5173"
                print(f"✅ Frontend Vite opérationnel sur {ui_url}")
            else:
                print("⚠️  Vite indisponible — fallback sur l'UI buildée (/ui) ou /docs.")

        if not args.no_browser:
            time.sleep(0.5)
            open_browser(ui_url)

        print("\n⏹  Ctrl+C pour arrêter tout le serveur.\n")
        stream_output(backend_proc, prefix="[backend] ")
        if vite_proc:
            stream_output(vite_proc, prefix="[vite] ")
    except KeyboardInterrupt:
        print("\n→ Arrêt demandé par l'utilisateur ...")
    finally:
        for p in (backend_proc, vite_proc):
            if p and p.poll() is None:
                try:
                    p.terminate()
                    p.wait(timeout=5)
                except Exception:
                    p.kill()
    print("👋 Au revoir.")
    return 0


def main() -> int:
    # Console Windows : forcer l'UTF-8 pour ne pas planter sur les emojis (🌷, ✅, →…)
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

    if len(sys.argv) > 1 and sys.argv[1] in COMMANDES_COMPTES:
        return run_comptes(sys.argv[1:])

    parser = argparse.ArgumentParser(description="Lanceur Oliv'IA")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-dev", action="store_true", help="Ne pas lancer Vite (backend seul)")
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur")
    parser.add_argument("--no-ollama", action="store_true",
                        help="Ne pas démarrer Ollama automatiquement")
    parser.add_argument("--max-wait", type=int, default=30)
    parser.add_argument("--parent-stdin", action="store_true",
                        help="S'arrêter quand l'entrée standard se ferme "
                             "(usage interne : application de bureau)")
    args = parser.parse_args()

    print("=" * 60)
    print("🌷 Oliv'IA — lanceur" + ("  [.exe]" if FROZEN else ""))
    print("=" * 60)
    verifier_dossier_donnees()

    ollama_proc = None if args.no_ollama else start_ollama()
    try:
        return run_frozen(args) if FROZEN else run_source(args)
    finally:
        if ollama_proc and ollama_proc.poll() is None:
            print("→ Arrêt d'Ollama ...")
            try:
                ollama_proc.terminate()
                ollama_proc.wait(timeout=5)
            except Exception:
                ollama_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
