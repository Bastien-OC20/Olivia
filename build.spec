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

block_cipher = None

# Le backend est embarqué comme package importable au runtime (voir launch.py).
datas = [('backend', 'backend')]

# L'UI buildée n'est incluse que si elle existe (sinon PyInstaller échouerait).
if os.path.isdir(os.path.join('frontend', 'dist')):
    datas.append(('frontend/dist', 'frontend/dist'))
else:
    print("⚠️  frontend/dist absent — l'.exe n'embarquera pas l'UI. "
          "Lancez d'abord : cd frontend && npm run build")

hiddenimports = [
    'uvicorn', 'uvicorn.logging', 'uvicorn.loops', 'uvicorn.loops.auto',
    'uvicorn.protocols', 'uvicorn.protocols.http', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets', 'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan', 'uvicorn.lifespan.on',
    'fastapi', 'starlette', 'starlette.middleware', 'starlette.middleware.base',
    'pydantic', 'pydantic.fields', 'pydantic.main', 'pydantic.types',
    'httpx', 'httpcore', 'anyio',
    'multipart',                       # python-multipart (uploads)
    'docx',                            # python-docx (preview .docx)
    'openpyxl',                        # preview .xlsx
    'ics',                             # calendrier .ics
    'email.mime.text', 'email.mime.multipart',
    'imaplib', 'smtplib',
]

a = Analysis(
    ['launch.py'],
    pathex=[],
    binaries=[],
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
