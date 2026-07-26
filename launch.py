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


def start_ollama():
    """Démarre le moteur Ollama portable (modèles stockés dans le projet).

    - S'il tourne déjà sur :11434, on le réutilise.
    - Sinon, si ./ollama/ollama(.exe) existe, on le lance avec OLLAMA_MODELS
      pointant vers ./ollama/models.
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

    OLLAMA_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["OLLAMA_MODELS"] = str(OLLAMA_MODELS_DIR)
    env.setdefault("OLLAMA_HOST", "127.0.0.1:11434")
    print(f"→ Démarrage d'Ollama (portable) — modèles : {OLLAMA_MODELS_DIR}")
    proc = subprocess.Popen(
        [str(OLLAMA_EXE), "serve"], env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
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
    print("\n⏹  Fermez cette fenêtre pour arrêter le serveur.\n")
    try:
        while server_thread.is_alive():
            server_thread.join(timeout=1)
    except KeyboardInterrupt:
        print("\n→ Arrêt demandé.")
    return 0


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
    return subprocess.Popen(
        [py, "-m", "uvicorn", "backend.main:app", "--host", host, "--port", str(port), "--reload"],
        cwd=str(SRC_ROOT),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )


def start_npm_dev() -> subprocess.Popen | None:
    if not (FRONTEND_DIR / "node_modules").exists():
        print("⚠️  frontend/node_modules absent — exécutez d'abord : cd frontend && npm install")
        return None
    print("→ Démarrage de Vite (UI mode dev) ...")
    npm = "npm.cmd" if IS_WINDOWS else "npm"
    return subprocess.Popen(
        [npm, "run", "dev"],
        cwd=str(FRONTEND_DIR),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1,
    )


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

    parser = argparse.ArgumentParser(description="Lanceur Olivia")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-dev", action="store_true", help="Ne pas lancer Vite (backend seul)")
    parser.add_argument("--no-browser", action="store_true", help="Ne pas ouvrir le navigateur")
    parser.add_argument("--no-ollama", action="store_true",
                        help="Ne pas démarrer Ollama automatiquement")
    parser.add_argument("--max-wait", type=int, default=30)
    args = parser.parse_args()

    print("=" * 60)
    print("🌷 Olivia — lanceur" + ("  [.exe]" if FROZEN else ""))
    print("=" * 60)

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
