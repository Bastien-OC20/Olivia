# -*- mode: python ; coding: utf-8 -*-
"""
Spec PyInstaller pour produire 'ai-webapp.exe' (Windows) ou 'ai-webapp' (Linux/Mac).

Prérequis AVANT de compiler : builder l'interface pour qu'elle soit embarquée.
    cd frontend && npm install && npm run build      # → frontend/dist
    cd ..
    pyinstaller build.spec --clean --noconfirm

Le binaire généré est dans :  dist/ai-webapp/ai-webapp(.exe)
Au lancement il démarre FastAPI EN INTERNE (pas de venv/pip requis) et ouvre
le navigateur sur http://127.0.0.1:8000/ui/.
"""
import os

from PyInstaller.utils.hooks import collect_submodules, collect_dynamic_libs

block_cipher = None

# Le backend est embarqué comme package importable au runtime (voir launch.py).
datas = [('backend', 'backend')]

# L'UI buildée n'est incluse que si elle existe (sinon PyInstaller échouerait).
if os.path.isdir(os.path.join('frontend', 'dist')):
    datas.append(('frontend/dist', 'frontend/dist'))
else:
    print("⚠️  frontend/dist absent — l'.exe n'embarquera pas l'UI. "
          "Lancez d'abord : cd frontend && npm run build")

# Le backend est chargé DYNAMIQUEMENT par uvicorn ("backend.main:app") : PyInstaller
# ne le voit pas à l'analyse statique de launch.py. Il faut donc collecter
# explicitement TOUS les sous-modules des frameworks (un simple 'fastapi' ne
# suffit pas : fastapi.middleware.cors, staticfiles, etc. manqueraient).
hiddenimports = (
    collect_submodules('uvicorn')
    + collect_submodules('fastapi')
    + collect_submodules('starlette')
    + [m for m in collect_submodules('pydantic') if '.mypy' not in m]
    + collect_submodules('faiss')
    + [
        'httpx', 'httpcore', 'anyio',
        'multipart',                   # python-multipart (uploads)
        'docx',                        # python-docx (preview .docx)
        'openpyxl',                    # preview .xlsx
        'pypdf',                       # extraction du texte des .pdf (recherche)
        'pypdfium2',                   # rendu des .pdf scannés avant OCR (ocr.py)
        'pypdfium2_raw',               # bibliothèque native livrée avec pypdfium2
        # Recherche par le sens (backend/docindex.py). faiss/loader.py choisit
        # AU RUNTIME, selon le jeu d'instructions du processeur détecté, entre
        # ces deux extensions compilées — un import conditionnel que l'analyse
        # statique de PyInstaller ne peut pas suivre seule.
        'faiss._swigfaiss', 'faiss._swigfaiss_avx2',
        'ics',                         # calendrier .ics
        'email.mime.text', 'email.mime.multipart',
        'imaplib', 'smtplib',
    ]
)

# `collect_submodules('faiss')` ne rapatrie que les modules PYTHON du paquet :
# l'extension native (`_swigfaiss*.pyd` et les DLL qu'elle charge) n'est pas un
# module importable au sens de l'analyse statique. Sans cette collecte, l'.exe
# se construirait sans erreur puis planterait à l'import de faiss.
binaries = collect_dynamic_libs('faiss')

a = Analysis(
    ['launch.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'numpy.tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)


# Le dossier `backend/` est embarqué en bloc (voir `datas`), ce qui y ferait entrer
# les DONNÉES de la machine de compilation : les réglages de l'utilisateur — clé
# d'API du moteur de recherche, mot de passe IMAP, chemins des dossiers de travail —
# et ses conversations. On les retire du binaire : une installation neuve (clé USB,
# autre poste) doit démarrer sur les valeurs par défaut, et le `.exe` ne doit jamais
# transporter de secret. `settings.json` est recréé au premier enregistrement.
# On retire aussi `backend/.venv` : l'environnement virtuel de développement n'a
# rien à faire dans le binaire (PyInstaller y embarque déjà les dépendances), il
# ne ferait que dupliquer ~65 Mo — d'autant plus pénalisant sur une clé USB.
def _est_donnee_utilisateur(dest: str) -> bool:
    d = dest.replace("\\", "/")
    return (
        d.startswith("backend/conversations/")
        # Comptes, organisations et sessions ouvertes de la machine de
        # compilation : dérivés de mots de passe et jetons de session vivants —
        # ce que le binaire ne doit surtout pas transporter (voir backend/users.py).
        # Les comptes se recréent sur le poste cible via backend/manage_users.py.
        or d.startswith("backend/profiles/")
        or d.startswith("backend/.venv/")
        or d.startswith("backend/ocr_cache/")
        or d.startswith("backend/docindex/")
        or d in ("backend/settings.json", "backend/settings.tmp", "backend/.env")
        or "/__pycache__/" in f"/{d}"
    )


_avant = len(a.datas)
a.datas = [entry for entry in a.datas if not _est_donnee_utilisateur(entry[0])]
print(f"build.spec : {_avant - len(a.datas)} fichier(s) de donnees utilisateur exclus du binaire")

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='ai-webapp',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='ai-webapp.ico',  # logo Olivia (généré depuis visuel/logo.png)
)

coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=True, upx_exclude=[], name='ai-webapp'
)
