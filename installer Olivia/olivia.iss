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
; DONNÉES UTILISATEUR (comptes, sessions, réglages, conversations, index, cache
; OCR) : HORS de Program Files, dans {commonappdata}\Olivia (C:\ProgramData\Olivia).
; Program Files n'est pas modifiable par un utilisateur standard : avec les
; données à côté du code, chaque connexion échouait (écriture de la session)
; sauf à lancer Olivia en administrateur. L'installeur :
;   - crée ce dossier en le rendant modifiable par les utilisateurs du poste
;     ([Dirs], users-modify) — les comptes sont créés par le service
;     informatique et servent à toutes les sessions Windows du poste, d'où un
;     dossier commun et non %LOCALAPPDATA%, propre à chaque session ;
;   - écrit {app}\ai-webapp\olivia.ini pour le désigner ([INI]) : c'est ce
;     fichier que lit backend/emplacements.py.
; Une installation antérieure qui avait écrit ses données dans Program Files
; est recopiée automatiquement au premier démarrage (emplacements.py).
; Les données ne sont jamais embarquées (build.spec, _est_donnee_utilisateur())
; ni supprimées à la désinstallation (uninsneveruninstall, aucune entrée dans
; [UninstallDelete]).

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

[Dirs]
; Données d'Olivia, communes au poste et modifiables par ses utilisateurs (voir
; l'en-tête). Jamais supprimées à la désinstallation.
Name: "{commonappdata}\Olivia"; Permissions: users-modify; Flags: uninsneveruninstall

[INI]
; Désigne le dossier des données à l'application (backend/emplacements.py).
Filename: "{app}\ai-webapp\olivia.ini"; Section: "donnees"; Key: "dossier"; String: "{commonappdata}\Olivia"; Flags: uninsdeletesection

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"
; Assistant de création de compte (backend/manage_users.py, commande init) :
; une installation neuve n'a aucun compte, et la connexion est obligatoire.
Name: "{group}\Créer un compte {#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; Parameters: "init"; WorkingDir: "{app}\ai-webapp"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"; Tasks: desktopicon

[Run]
; Proposé seulement s'il n'existe encore aucun compte (voir AucunCompte) : sur
; une mise à jour, les comptes sont déjà là.
Filename: "{app}\ai-webapp\{#AppExeName}"; Parameters: "init"; WorkingDir: "{app}\ai-webapp"; Description: "Créer le premier compte (service informatique)"; Flags: postinstall skipifsilent; Check: AucunCompte
Filename: "{app}\ai-webapp\{#AppExeName}"; Description: "Lancer {#AppName} maintenant"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Purge explicitement le cache PyInstaller (dossier temporaire de
; décompression) si présent, MAIS jamais les données utilisateur — elles
; vivent dans {commonappdata}\Olivia (voir l'en-tête du fichier). Aucune entrée
; ici ne doit viser ce dossier, ni profiles\, ocr_cache\ ou _uploads\.
Type: filesandordirs; Name: "{app}\ai-webapp\_internal\__pycache__"

[Code]
// Vrai tant qu'aucun compte n'a été créé : la case « Créer le premier compte »
// n'apparaît alors qu'à la première installation, pas à chaque mise à jour.
// Le second emplacement est celui d'une version antérieure, qui écrivait les
// comptes dans Program Files : ils seront recopiés au premier démarrage
// (backend/emplacements.py), il ne faut donc pas inviter à en recréer.
function AucunCompte: Boolean;
begin
  Result := not FileExists(ExpandConstant('{commonappdata}\Olivia\profiles\users.json'))
    and not FileExists(ExpandConstant('{app}\ai-webapp\_internal\backend\profiles\users.json'));
end;
