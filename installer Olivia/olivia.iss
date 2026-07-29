; Script Inno Setup pour Olivia — installeur Windows classique (niveau 1),
; en complément de deploy-portable.ps1 (clé USB), pas en remplacement.
;
; Contrairement à la clé portable, celui-ci installe dans Program Files avec
; un raccourci Menu Démarrer et un désinstalleur — l'expérience attendue d'un
; « vrai logiciel » pour une structure sans compétence technique interne.
;
; PRÉREQUIS AVANT COMPILATION (identiques à deploy-portable.ps1) :
;   1. cd ..\frontend && npm run build
;   2. cd .. && backend\.venv\Scripts\python -m PyInstaller build.spec --clean --noconfirm
;   3. Vérifier que ..\ollama\, ..\tesseract\, ..\modeles\ contiennent les bons
;      fichiers (moteurs + modèles) — voir README pour leur mise en place.
;
; Tout est embarqué (comme la clé USB) : Ollama portable + les 3 modèles
; retenus (mistral-nemo, gemma2:2b, bge-m3 — voir backend/settings.py) +
; Tesseract + le modèle Word de l'établissement. Installeur volumineux
; (~10-11 Go) en conséquence : compression "fast" plutôt que maximale, les
; poids de modèles (GGUF, déjà denses) ne se compressent presque pas et LZMA
; maximal ferait juste perdre du temps de compilation pour rien.
;
; DONNÉES UTILISATEUR (conversations, réglages, caches) : jamais embarquées
; (déjà exclues par build.spec, voir _est_donnee_utilisateur()) et jamais
; supprimées à la désinstallation — Inno Setup ne retire que les fichiers
; qu'il a lui-même installés, donc les dossiers créés à l'usage (conversations\,
; ocr_cache\, docindex\, _uploads\, settings.json) ne sont ni installés ni
; jamais touchés par [UninstallDelete].

#define AppName "Olivia"
#define AppVersion "1.0.0"
#define AppPublisher "Lycee de l'Olivier"
#define AppExeName "ai-webapp.exe"
#define SourceRoot "..\"

[Setup]
; GUID fixe : permet à une future version de se reconnaitre comme mise à
; jour plutôt que comme une installation séparée. NE JAMAIS CHANGER.
AppId={{BA4CF2C7-E3E6-447A-843F-3F27607A204D}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=Sortie
OutputBaseFilename=Installer-Olivia-{#AppVersion}
SetupIconFile={#SourceRoot}ai-webapp.ico
UninstallDisplayIcon={app}\ai-webapp\{#AppExeName}
Compression=lzma2/fast
SolidCompression=yes
WizardStyle=modern
; ~10-11 Go de modèles : prévenir si le disque cible est trop petit plutôt
; que planter en cours d'installation.
ExtraDiskSpaceRequired=1073741824
; Un Setup.exe unique est plafonné à ~4,2 Go par Windows (limite du format
; PE) — largement dépassé ici. DiskSpanning fractionne la sortie en
; Setup.exe + plusieurs disk1.bin, disk2.bin, etc., à distribuer ENSEMBLE
; dans le même dossier (mécanisme natif Inno Setup, pas un support de
; disquette — le nom est historique).
DiskSpanning=yes
DiskSliceSize=2100000000

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le Bureau"; GroupDescription: "Raccourcis supplémentaires :"

[Files]
; Application (backend + frontend buildés par PyInstaller) — déjà nettoyée
; des données utilisateur par build.spec (_est_donnee_utilisateur).
Source: "{#SourceRoot}dist\ai-webapp\*"; DestDir: "{app}\ai-webapp"; Flags: ignoreversion recursesubdirs createallsubdirs

; Moteur Ollama portable + les 3 modèles retenus (mistral-nemo, gemma2:2b,
; bge-m3). Doit atterrir DANS ai-webapp\ : c'est là que launch.py le cherche
; (à côté de l'exécutable), même convention que deploy-portable.ps1.
Source: "{#SourceRoot}ollama\*"; DestDir: "{app}\ai-webapp\ollama"; Flags: ignoreversion recursesubdirs createallsubdirs

; Moteur de reconnaissance de caractères (OCR) portable.
Source: "{#SourceRoot}tesseract\*"; DestDir: "{app}\ai-webapp\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs

; Modèle Word de l'établissement (logo, en-tête) — voir backend/docmodele.py.
Source: "{#SourceRoot}modeles\*"; DestDir: "{app}\ai-webapp\modeles"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"; Tasks: desktopicon

[Run]
Filename: "{app}\ai-webapp\{#AppExeName}"; Description: "Lancer {#AppName} maintenant"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Purge explicitement le cache PyInstaller (dossier temporaire de
; décompression) si présent, MAIS jamais les données utilisateur — elles ne
; sont de toute façon jamais dans {app} puisque jamais installées là (voir
; l'en-tête du fichier). Aucune entrée ici ne doit viser conversations\,
; ocr_cache\, docindex\, _uploads\ ou settings.json.
Type: filesandordirs; Name: "{app}\ai-webapp\_internal\__pycache__"
