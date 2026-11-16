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
; retenus (ministral-3:8b, gemma2:2b, bge-m3 — voir backend/settings.py) +
; Tesseract + le modèle Word de l'établissement. Installeur volumineux
; (~10-11 Go) en conséquence : compression "fast" plutôt que maximale, les
; poids de modèles (GGUF, déjà denses) ne se compressent presque pas et LZMA
; maximal ferait juste perdre du temps de compilation pour rien.
;
; DONNÉES UTILISATEUR (comptes, sessions, réglages, conversations, index, cache
; OCR) : HORS de Program Files, dans %LOCALAPPDATA%\Olivia, le profil du COMPTE
; WINDOWS de la personne qui lance Olivia.
; Program Files n'est pas modifiable par un utilisateur standard : avec les
; données à côté du code, chaque connexion échouait (écriture de la session)
; sauf à lancer Olivia en administrateur.
; Les versions précédentes utilisaient {commonappdata}\Olivia
; (C:\ProgramData\Olivia), commun au poste et rendu modifiable par tous ses
; utilisateurs : n'importe quel autre compte Windows pouvait y lire les
; conversations, copier un jeton de session ou remplacer un mot de passe (audit
; du 15/11/2026). Olivia tournant sous la session Windows de la personne, seul
; un dossier de SON profil est protégé des autres comptes par le système.
; L'installeur écrit {app}\ai-webapp\olivia.ini ([INI]), lu par
; backend/emplacements.py :
;   - `dossier` désigne %LOCALAPPDATA%\Olivia — la variable est écrite telle
;     quelle et développée au lancement, pour chaque compte Windows ;
;   - `reprise` désigne l'ancien dossier commun : au premier démarrage après la
;     mise à jour, le compte Windows qui lance Olivia en reprend les données,
;     qui sont alors retirées de l'ancien dossier.
; Une installation plus ancienne encore, qui avait écrit ses données dans
; Program Files, est recopiée automatiquement au premier démarrage.
; Les données ne sont jamais embarquées (build.spec, _est_donnee_utilisateur())
; ni supprimées à la désinstallation (aucune entrée dans [UninstallDelete]).

; Nom affiché (assistant d'installation, menu Démarrer, Programmes et
; fonctionnalités). Les noms techniques restent « Olivia » : dossier
; d'installation, dossier des données, olivia.ini — les changer ferait perdre
; à une mise à jour les comptes et conversations déjà enregistrés.
#define AppName "Oliv'IA"
#define AppDirName "Olivia"
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
DefaultDirName={autopf}\{#AppDirName}
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

; Moteur Ollama portable, SANS ses modèles. Doit atterrir DANS ai-webapp\ :
; c'est là que launch.py le cherche (à côté de l'exécutable).
Source: "{#SourceRoot}ollama\*"; DestDir: "{app}\ai-webapp\ollama"; Excludes: "\models"; Flags: ignoreversion recursesubdirs createallsubdirs

; Les 3 modèles retenus (ministral-3:8b, gemma2:2b, bge-m3), HORS de Program Files :
; dans {commonappdata}\Olivia\modeles-ia, commun au poste et inscriptible (voir
; [Dirs]). Sous Program Files, un modèle à télécharger plus tard (passage en
; mode Léger, par exemple) ne pouvait pas s'écrire. Désigné à launch.py par la
; clé `modeles` de olivia.ini.
; Les fichiers de blobs/ portent l'empreinte de leur contenu : déjà présents,
; ils sont identiques, et onlyifdoesntexist évite de réécrire ~9 Go à chaque
; mise à jour. Les manifestes, minuscules, sont toujours réécrits.
Source: "{#SourceRoot}ollama\models\blobs\*"; DestDir: "{commonappdata}\Olivia\modeles-ia\blobs"; Flags: onlyifdoesntexist uninsneveruninstall recursesubdirs createallsubdirs
Source: "{#SourceRoot}ollama\models\manifests\*"; DestDir: "{commonappdata}\Olivia\modeles-ia\manifests"; Flags: ignoreversion uninsneveruninstall recursesubdirs createallsubdirs

; Moteur de reconnaissance de caractères (OCR) portable.
Source: "{#SourceRoot}tesseract\*"; DestDir: "{app}\ai-webapp\tesseract"; Flags: ignoreversion recursesubdirs createallsubdirs

; Modèle Word de l'établissement (logo, en-tête) — voir backend/docmodele.py.
Source: "{#SourceRoot}modeles\*"; DestDir: "{app}\ai-webapp\modeles"; Flags: ignoreversion recursesubdirs createallsubdirs skipifsourcedoesntexist

[Dirs]
; Seul dossier commun au poste ouvert en écriture aux utilisateurs : les modèles
; d'IA (plusieurs Go, aucune donnée personnelle), pour qu'Oliv'IA puisse en
; télécharger un depuis n'importe quel compte Windows. Comptes et conversations
; n'y sont pas (voir l'en-tête). Jamais supprimé à la désinstallation.
Name: "{commonappdata}\Olivia\modeles-ia"; Permissions: users-modify; Flags: uninsneveruninstall

[InstallDelete]
; Mise à jour : un module Python retiré d'une version à l'autre resterait sinon
; dans _internal\ et pourrait encore être chargé. Le dossier est entièrement
; recopié juste après.
Type: filesandordirs; Name: "{app}\ai-webapp\_internal"
; Modèles d'une version antérieure, rangés dans Program Files : ils sont
; désormais dans {commonappdata}\Olivia\modeles-ia (~9 Go libérés).
Type: filesandordirs; Name: "{app}\ai-webapp\ollama\models"

[INI]
; Désigne le dossier des données à l'application (backend/emplacements.py) :
; propre au compte Windows, plus aucun dossier commun ouvert à tous (voir
; l'en-tête). %LOCALAPPDATA% n'est PAS une constante Inno Setup : la chaîne est
; écrite telle quelle, et développée par l'application au lancement.
Filename: "{app}\ai-webapp\olivia.ini"; Section: "donnees"; Key: "dossier"; String: "%LOCALAPPDATA%\Olivia"; Flags: uninsdeletesection
; Ancien dossier commun, repris une fois puis vidé de ses données.
Filename: "{app}\ai-webapp\olivia.ini"; Section: "donnees"; Key: "reprise"; String: "{commonappdata}\Olivia"
; Dossier des modèles d'IA (launch.py, dossier_modeles_ollama).
Filename: "{app}\ai-webapp\olivia.ini"; Section: "donnees"; Key: "modeles"; String: "{commonappdata}\Olivia\modeles-ia"

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"
; Assistant de création de compte (backend/manage_users.py, commande init) :
; une installation neuve n'a aucun compte, et la connexion est obligatoire.
Name: "{group}\Créer un compte {#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; Parameters: "init"; WorkingDir: "{app}\ai-webapp"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\ai-webapp\{#AppExeName}"; WorkingDir: "{app}\ai-webapp"; Tasks: desktopicon

[Run]
; Proposé seulement s'il n'existe encore aucun compte (voir AucunCompte) : sur
; une mise à jour, les comptes sont déjà là. runasoriginaluser : le compte est
; créé dans le profil de la personne qui a lancé l'installation, pas dans celui
; de l'administrateur qui l'a autorisée — les données sont propres à chaque
; compte Windows. Installé par quelqu'un d'autre que l'utilisatrice, ne pas
; cocher : elle créera son compte depuis le menu Démarrer, dans sa session.
Filename: "{app}\ai-webapp\{#AppExeName}"; Parameters: "init"; WorkingDir: "{app}\ai-webapp"; Description: "Créer le premier compte (pour ce compte Windows)"; Flags: postinstall skipifsilent runasoriginaluser; Check: AucunCompte
Filename: "{app}\ai-webapp\{#AppExeName}"; Description: "Lancer {#AppName} maintenant"; Flags: postinstall nowait skipifsilent unchecked

[UninstallDelete]
; Purge explicitement le cache PyInstaller (dossier temporaire de
; décompression) si présent, MAIS jamais les données utilisateur — elles
; vivent dans le profil de chaque compte Windows (voir l'en-tête du fichier),
; et l'ancien dossier commun {commonappdata}\Olivia peut en contenir tant
; qu'elles n'ont pas été reprises. Aucune entrée
; ici ne doit viser ce dossier, ni profiles\, ocr_cache\ ou _uploads\.
Type: filesandordirs; Name: "{app}\ai-webapp\_internal\__pycache__"

[Code]
// Vrai tant qu'aucun compte n'a été créé : la case « Créer le premier compte »
// n'apparaît alors qu'à la première installation, pas à chaque mise à jour.
// Trois emplacements : le profil du compte Windows (emplacement actuel), puis
// ceux de versions antérieures — dossier commun au poste, Program Files —
// dont les comptes seront repris au premier démarrage (backend/emplacements.py) :
// il ne faut donc pas inviter à en recréer.
function AucunCompte: Boolean;
begin
  Result := not FileExists(ExpandConstant('{localappdata}\Olivia\profiles\users.json'))
    and not FileExists(ExpandConstant('{commonappdata}\Olivia\profiles\users.json'))
    and not FileExists(ExpandConstant('{app}\ai-webapp\_internal\backend\profiles\users.json'));
end;
