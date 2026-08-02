<#
.SYNOPSIS
    Installe ou met à jour Olivia sur un disque portable (clé USB, disque externe).

.DESCRIPTION
    Enchaîne les étapes d'un déploiement portable :
      1. build du frontend (Vite)     -> frontend/dist, embarqué ensuite dans l'exe
      2. build de l'exe (PyInstaller) -> dist/ai-webapp
      3. copie du moteur Ollama + modèles, si absents de la destination
      4. synchronisation de l'application vers le disque

    DESTINATION
    Sans -Destination, le script liste les lecteurs disponibles et demande où
    installer. Avec -Destination, il travaille sans poser de question.

    INSTALLATION DÉJÀ PRÉSENTE
    Deux comportements, choisis interactivement ou via un paramètre :

      -Update   (défaut) Remplace l'application, CONSERVE le moteur, les modèles,
                les conversations et les réglages. C'est le mode d'une mise à jour :
                réécraser 9 Go de modèles à chaque déploiement n'aurait aucun sens.

      -Replace  Efface intégralement l'installation puis la reconstruit à neuf.
                DESTRUCTIF : les conversations et les réglages du disque sont perdus,
                et les modèles doivent être recopiés (plusieurs minutes).

    La synchronisation est un MIROIR : les fichiers d'anciennes versions sont
    supprimés de la destination. En mode -Update, plusieurs éléments en sont
    explicitement protégés car ils vivent sur le disque et n'existent pas
    dans le build :

      - ai-webapp\ollama\                          (moteur + modèles)
      - ai-webapp\_internal\backend\conversations\ (historique)
      - ai-webapp\_internal\backend\settings.json  (réglages, dont secrets)
      - ai-webapp\_internal\backend\profiles\      (comptes et organisations)

.PARAMETER Destination
    Racine de l'installation portable, par exemple G:\Olivia.
    Omis, le script propose de choisir parmi les lecteurs détectés.

.PARAMETER Update
    Mise à jour sans question : conserve modèles, conversations et réglages.

.PARAMETER Replace
    Réinstallation complète sans question. Efface tout le dossier de destination.

.PARAMETER SyncModeles
    Copie vers le disque portable les modèles de langue présents dans le projet
    et absents de la destination. Sans ce commutateur, l'écart est seulement
    signalé : la copie se compte en gigaoctets, elle ne doit pas être implicite.

.PARAMETER SkipFrontend
    Ne pas rebuilder l'interface (si frontend/dist est déjà à jour).

.PARAMETER SkipExe
    Ne pas rebuilder l'exe : synchronise le contenu actuel de dist/ai-webapp.

.PARAMETER Force
    Autorise l'écriture dans un dossier non vide qui ne ressemble pas à une
    installation Olivia (garde-fou contre une erreur de lettre de lecteur).

.EXAMPLE
    .\deploy-portable.ps1
    Demande le lecteur, puis quoi faire si une installation existe déjà.

.EXAMPLE
    .\deploy-portable.ps1 -Destination G:\Olivia -Update
    Mise à jour silencieuse, utilisable dans un script.

.EXAMPLE
    .\deploy-portable.ps1 -Destination E:\Olivia -Replace
    Réinstallation complète sur un disque neuf (recopie les modèles).
#>
[CmdletBinding()]
param(
    [string]$Destination,
    [switch]$Update,
    [switch]$Replace,
    [switch]$SyncModeles,
    [switch]$SkipFrontend,
    [switch]$SkipExe,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$dist = Join-Path $root 'dist\ai-webapp'
$ollamaSource = Join-Path $root 'ollama'
$tesseractSource = Join-Path $root 'tesseract'
$chrono = [System.Diagnostics.Stopwatch]::StartNew()

if ($Update -and $Replace) {
    throw 'Choisissez -Update OU -Replace, pas les deux.'
}


function Write-Etape([string]$texte) {
    Write-Host ''
    Write-Host "==> $texte" -ForegroundColor Cyan
}


function Get-TailleGo([string]$chemin) {
    if (-not (Test-Path $chemin)) { return $null }
    $octets = (Get-ChildItem $chemin -Recurse -File -ErrorAction SilentlyContinue |
               Measure-Object -Property Length -Sum).Sum
    return [math]::Round($octets / 1GB, 2)
}


function Read-Choix([string]$question, [string]$defaut) {
    # Read-Host echoue si le script tourne sans console (tache planifiee, CI) :
    # on retombe alors sur le defaut plutot que de planter.
    try { $reponse = Read-Host $question } catch { return $defaut }
    if ([string]::IsNullOrWhiteSpace($reponse)) { return $defaut }
    return $reponse.Trim()
}


$ESPACE_MINI_GO = 10   # application + moteur + modeles, avec un peu de marge


function Select-Destination {
    <#  Liste les lecteurs utilisables et demande ou installer.

        Deux pieges evites ici, constates en test :
          - les lecteurs de cartes vides apparaissent avec 0 Go : on les ecarte,
            sinon le script propose un emplacement qui n'existe pas ;
          - un disque USB externe est souvent vu comme 'Fixed' par Windows, pas
            'Removable' : se fier au type de bus donnerait une suggestion fausse.
        On classe donc par espace libre, et une installation Olivia deja presente
        l'emporte sur tout le reste. #>
    Write-Etape 'Choix du disque'
    $systeme = ($env:SystemDrive).TrimEnd(':')
    $volumes = Get-Volume -ErrorAction SilentlyContinue |
               Where-Object { $_.DriveLetter -and $_.SizeRemaining -gt 0 } |
               Sort-Object DriveLetter

    $candidats = @()
    foreach ($v in $volumes) {
        $libre = [math]::Round($v.SizeRemaining / 1GB, 1)
        $lettre = $v.DriveLetter
        $nom = if ($v.FileSystemLabel) { $v.FileSystemLabel } else { '(sans nom)' }
        $dejaInstalle = Test-Path "${lettre}:\Olivia\ai-webapp\ai-webapp.exe"
        $note = ''
        $couleur = 'Gray'
        if ($dejaInstalle) { $note = '  <- Olivia deja installee'; $couleur = 'Green' }
        elseif ($libre -lt $ESPACE_MINI_GO) { $note = '  (espace insuffisant)'; $couleur = 'DarkGray' }
        elseif ($lettre -eq $systeme) { $note = '  (disque systeme)'; $couleur = 'DarkGray' }
        Write-Host ("  {0}:  {1,7} Go libres   {2}{3}" -f $lettre, $libre, $nom, $note) `
                   -ForegroundColor $couleur
        $candidats += [pscustomobject]@{
            Lettre = $lettre; Libre = $libre; Installe = $dejaInstalle
            Systeme = ($lettre -eq $systeme)
        }
    }
    Write-Host ''
    Write-Host "  Il faut environ $ESPACE_MINI_GO Go (application + moteur + modeles)." `
               -ForegroundColor DarkGray

    # Priorite : installation existante, puis le disque non systeme le plus libre.
    $choix = $candidats | Where-Object { $_.Installe } | Select-Object -First 1
    if (-not $choix) {
        $choix = $candidats |
                 Where-Object { $_.Libre -ge $ESPACE_MINI_GO -and -not $_.Systeme } |
                 Sort-Object Libre -Descending | Select-Object -First 1
    }
    if (-not $choix) {
        throw ("Aucun disque ne dispose de $ESPACE_MINI_GO Go libres hors disque systeme. " +
               'Branchez le disque portable, ou indiquez -Destination explicitement.')
    }
    $defaut = "$($choix.Lettre):\Olivia"
    return Read-Choix "Ou installer Olivia ? [$defaut]" $defaut
}


Write-Host ''
Write-Host 'Olivia - deploiement portable' -ForegroundColor Green
Write-Host "Source : $root"

if (-not $ollamaSource -or -not (Test-Path $ollamaSource)) {
    Write-Host "  Attention : '$ollamaSource' est absent du projet." -ForegroundColor Yellow
    Write-Host '  Une premiere installation ne pourra pas embarquer le moteur.' -ForegroundColor Yellow
}
if (-not (Test-Path $tesseractSource)) {
    Write-Host "  Attention : '$tesseractSource' est absent du projet." -ForegroundColor Yellow
    Write-Host '  Les PDF scannes ne seront pas cherchables sur le disque portable.' -ForegroundColor Yellow
}

if ([string]::IsNullOrWhiteSpace($Destination)) {
    $Destination = Select-Destination
}
$Destination = $Destination.Trim().TrimEnd('\')
Write-Host ''
Write-Host "Destination : $Destination"

# --- Garde-fous ------------------------------------------------------------
# Verification du lecteur AVANT tout Join-Path sur la destination : Join-Path
# resout le qualifieur et leve lui-meme un "Cannot find drive" peu parlant si le
# disque n'est pas branche. On veut un message comprehensible.
$racineDest = Split-Path $Destination -Qualifier
if ($racineDest -and -not [System.IO.Directory]::Exists("$racineDest\")) {
    throw "Le lecteur $racineDest est introuvable. Le disque portable est-il branche ?"
}
$app = [System.IO.Path]::Combine($Destination, 'ai-webapp')

$installExistante = Test-Path (Join-Path $app 'ai-webapp.exe')

# Le miroir supprime ce qui n'est pas dans la source : on refuse de le lancer
# sur un dossier qui n'est pas (ou pas encore) une installation Olivia.
if (-not $installExistante -and -not $Force) {
    $contenu = if (Test-Path $Destination) { @(Get-ChildItem $Destination -Force) } else { @() }
    if ($contenu.Count -gt 0) {
        throw ("'$Destination' existe, n'est pas vide, et ne contient pas " +
               "ai-webapp\ai-webapp.exe. Par securite, rien n'a ete touche. " +
               'Verifiez la lettre de lecteur, ou relancez avec -Force.')
    }
}

# --- Mise a jour ou reinstallation ? ---------------------------------------
$modeReplace = [bool]$Replace
if ($installExistante -and -not $Update -and -not $Replace) {
    Write-Etape 'Installation existante detectee'
    $conv = Join-Path $app '_internal\backend\conversations'
    $nb = if (Test-Path $conv) {
        @(Get-ChildItem $conv -Filter '*.json' -ErrorAction SilentlyContinue).Count
    } else { 0 }
    Write-Host ("  Modeles       : {0}" -f
                $(if (Get-TailleGo (Join-Path $app 'ollama')) {
                    "$(Get-TailleGo (Join-Path $app 'ollama')) Go" } else { 'absents' }))
    Write-Host "  Conversations : $nb enregistrees"
    Write-Host ''
    Write-Host '  [M] Mettre a jour  - remplace l''application, garde modeles et donnees'
    Write-Host '  [R] Reinstaller    - efface TOUT le dossier et repart a neuf' -ForegroundColor Yellow
    Write-Host '  [A] Annuler'
    switch (Read-Choix 'Votre choix [M]' 'M') {
        { $_ -match '^[Rr]' } { $modeReplace = $true }
        { $_ -match '^[Aa]' } { Write-Host 'Annule, rien n''a ete modifie.'; exit 0 }
        default { $modeReplace = $false }
    }
}

if ($modeReplace -and $installExistante) {
    # Confirmation explicite : cette branche detruit des donnees irrecuperables.
    if (-not $Replace) {
        $reponse = Read-Choix "Confirmer l'effacement de '$Destination' ? (oui/non) [non]" 'non'
        if ($reponse -notmatch '^(o|oui|y|yes)$') {
            Write-Host 'Annule, rien n''a ete modifie.'
            exit 0
        }
    }
    Write-Etape "Effacement de l'installation existante"
    Remove-Item $Destination -Recurse -Force
    $installExistante = $false
}

# --- 1. Frontend -----------------------------------------------------------
if ($SkipFrontend) {
    Write-Etape 'Frontend : ignore (-SkipFrontend)'
} else {
    Write-Etape 'Build du frontend (Vite)'
    Push-Location (Join-Path $root 'frontend')
    try {
        & npm run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build a echoue (code $LASTEXITCODE)." }
    } finally { Pop-Location }
}

# --- 2. Exe ----------------------------------------------------------------
if ($SkipExe) {
    Write-Etape 'Exe : ignore (-SkipExe)'
    if (-not (Test-Path (Join-Path $dist 'ai-webapp.exe'))) {
        throw 'dist\ai-webapp\ai-webapp.exe est absent : impossible de synchroniser.'
    }
} else {
    Write-Etape 'Build de l''exe (PyInstaller)'
    $python = Join-Path $root 'backend\.venv\Scripts\python.exe'
    if (-not (Test-Path $python)) {
        throw "Venv backend introuvable ($python). Lancez d'abord : python launch.py"
    }
    $env:PYTHONIOENCODING = 'utf-8'   # console Windows cp1252 : evite un plantage
    # PyInstaller DOIT etre lance depuis la racine : build.spec designe ses
    # sources en relatif ('backend', 'frontend/dist'), et ces chemins sont
    # resolus par rapport au repertoire COURANT, pas a l'emplacement du .spec.
    # Lance d'ailleurs, il produit un exe sans interface et deverse son build
    # dans le dossier courant — panne silencieuse, constatee en conditions
    # reelles : la synchronisation copiait alors l'ancien build sans rien signaler.
    Push-Location $root
    try {
        & $python -m PyInstaller 'build.spec' --clean --noconfirm
        if ($LASTEXITCODE -ne 0) { throw "PyInstaller a echoue (code $LASTEXITCODE)." }
    } finally { Pop-Location }
    if (-not (Test-Path (Join-Path $dist '_internal\frontend\dist\index.html'))) {
        throw ("Le binaire produit n'embarque pas l'interface. Verifiez que " +
               "frontend\dist existe (npm run build) et relancez.")
    }
}

New-Item -ItemType Directory -Force -Path $app | Out-Null

# --- 3. Moteur Ollama ------------------------------------------------------
# Le moteur et les modeles ne sont PAS dans le build : ils viennent du projet.
# On ne les copie que s'ils manquent a destination — c'est le cas d'une premiere
# installation ou d'une reinstallation. Une mise a jour n'y touche pas.
# Ils doivent atterrir DANS ai-webapp\ : le lanceur cherche .\ollama a cote de
# l'executable, pas a cote du .bat.
$ollamaDest = Join-Path $app 'ollama'
if (Test-Path (Join-Path $ollamaDest 'ollama.exe')) {
    Write-Etape 'Moteur Ollama : deja present, conserve'
} elseif (Test-Path (Join-Path $ollamaSource 'ollama.exe')) {
    $taille = Get-TailleGo $ollamaSource
    Write-Etape "Copie du moteur Ollama et des modeles ($taille Go) - patientez"
    & robocopy $ollamaSource $ollamaDest /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy (ollama) a echoue (code $LASTEXITCODE)." }
} else {
    Write-Etape 'Moteur Ollama : introuvable dans le projet, etape ignoree'
    Write-Host '  Olivia demarrera, mais ne pourra pas repondre sans moteur.' -ForegroundColor Yellow
}

# --- 3 bis. Moteur de reconnaissance de caracteres (OCR) -------------------
# Meme logique que pour Ollama : binaire portable absent du build, copie depuis
# le projet uniquement s'il manque a destination. Il doit lui aussi atterrir
# DANS ai-webapp\, backend/ocr.py le cherchant a cote de l'executable.
# Sans lui, les PDF scannes restent introuvables dans la recherche — mais tout
# le reste fonctionne : son absence n'est pas bloquante.
# --- 3 ter. Modeles de langue ----------------------------------------------
# Le dossier ollama\ etant PRESERVE d'une mise a jour a l'autre (on ne recopie
# pas 9 Go a chaque fois), un modele telecharge depuis dans le projet n'atteint
# JAMAIS le disque portable. La cle proposerait alors un modele qui n'y est pas
# installe. On compare donc les modeles presents de part et d'autre, et on
# signale l'ecart — la copie reste explicite (-SyncModeles), car elle se compte
# en gigaoctets.
$modelesSource = Join-Path $ollamaSource 'models\manifests\registry.ollama.ai\library'
$modelesDest = Join-Path $ollamaDest 'models\manifests\registry.ollama.ai\library'
function Get-Modeles([string]$chemin) {
    if (-not (Test-Path $chemin)) { return @() }
    return @(Get-ChildItem $chemin -Directory -ErrorAction SilentlyContinue |
             Select-Object -Expand Name)
}
$modelesManquants = @(Get-Modeles $modelesSource |
                      Where-Object { $_ -notin (Get-Modeles $modelesDest) })
if ($modelesManquants.Count -gt 0) {
    if ($SyncModeles) {
        $taille = Get-TailleGo (Join-Path $ollamaSource 'models')
        Write-Etape ("Synchronisation des modeles ({0}) - {1} Go au total, patientez" -f
                     ($modelesManquants -join ', '), $taille)
        & robocopy (Join-Path $ollamaSource 'models') (Join-Path $ollamaDest 'models') `
            /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy (modeles) a echoue (code $LASTEXITCODE)." }
    } else {
        Write-Etape 'Modeles : ecart detecte'
        Write-Host ("  Absents du disque portable : {0}" -f ($modelesManquants -join ', ')) `
                   -ForegroundColor Yellow
        Write-Host '  Relancez avec -SyncModeles pour les copier.' -ForegroundColor Yellow
    }
}

$tesseractDest = Join-Path $app 'tesseract'
$exeOcr = if ($IsLinux -or $IsMacOS) { 'tesseract' } else { 'tesseract.exe' }
if (Test-Path (Join-Path $tesseractDest $exeOcr)) {
    Write-Etape 'Moteur OCR : deja present, conserve'
} elseif (Test-Path (Join-Path $tesseractSource $exeOcr)) {
    $taille = Get-TailleGo $tesseractSource
    Write-Etape "Copie du moteur OCR ($taille Go)"
    & robocopy $tesseractSource $tesseractDest /E /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy (tesseract) a echoue (code $LASTEXITCODE)." }
} else {
    Write-Etape 'Moteur OCR : absent du projet, etape ignoree'
    Write-Host '  Les PDF scannes ne seront pas cherchables sur ce disque.' -ForegroundColor Yellow
}

# --- 3 quater. Modele Word de l'etablissement -------------------------------
# Contrairement a ollama/tesseract (gros fichiers statiques, copies une seule
# fois), ce modele est petit (quelques dizaines de Ko) et peut changer d'une
# fabrication a l'autre (nouvelle charte, nouveau logo) : on le MIROIRE a
# chaque deploiement plutot que de le copier une seule fois. Absent du build
# PyInstaller (voir build.spec) : le logo appartient a l'etablissement, il n'a
# pas a etre embarque dans un binaire qui pourrait circuler hors de cet usage.
# Sans lui, backend/docgen.py degrade proprement : les documents sont quand
# meme crees, sans logo ni en-tete, avec un avertissement explicite renvoye
# a l'interface — ce n'est donc jamais une raison d'echouer le deploiement.
$modeleWordSource = Join-Path $root 'modeles'
$modeleWordDest = Join-Path $app 'modeles'
if (Test-Path $modeleWordSource) {
    Write-Etape 'Modele Word de l''etablissement : synchronisation'
    & robocopy $modeleWordSource $modeleWordDest /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "robocopy (modele etablissement) a echoue (code $LASTEXITCODE)." }
} else {
    Write-Etape 'Modele Word de l''etablissement : absent du projet, etape ignoree'
    Write-Host '  Les documents seront generes sans logo ni en-tete.' -ForegroundColor Yellow
}

# --- 4. Application --------------------------------------------------------
Write-Etape "Synchronisation de l'application vers $app"

$dossierConv = Join-Path $app '_internal\backend\conversations'
$nbConversations = if (Test-Path $dossierConv) {
    @(Get-ChildItem $dossierConv -Filter '*.json' -ErrorAction SilentlyContinue).Count
} else { 0 }

# Caches derives du contenu des documents (texte OCR, index vectoriel de la
# recherche par le sens) : absents du build PyInstaller (voir build.spec), et
# reconstructibles, mais un /MIR sans exclusion les effacerait a CHAQUE mise a
# jour de l'application, forcant une re-reconnaissance OCR ou une reindexation
# complete pour rien. Meme logique de protection que conversations/settings.
$ocrCacheDest = Join-Path $app '_internal\backend\ocr_cache'
$docindexDest = Join-Path $app '_internal\backend\docindex'

# Comptes, organisations et sessions (backend/profiles/) : absents du build
# (voir build.spec), crees sur le poste cible via backend/manage_users.py, et
# surtout PAS reconstructibles - un /MIR sans exclusion deconnecterait tout le
# monde et supprimerait les comptes a chaque mise a jour de l'application.
$profilesDest = Join-Path $app '_internal\backend\profiles'

if ($installExistante) {
    Write-Host "  Preserve : conversations\ ($nbConversations enregistrees)"
    Write-Host '  Preserve : settings.json'
    Write-Host '  Preserve : profiles\ (comptes et organisations)'
    Write-Host '  Preserve : ocr_cache\ et docindex\ (caches reconstructibles)'
}

# /MIR purge les fichiers des anciennes versions ; /XD et /XF sanctuarisent
# les donnees du disque portable, absentes du build (voir en-tete).
$exclusionsDossiers = @(
    $ollamaDest,
    $tesseractDest,
    $modeleWordDest,
    $dossierConv,
    $profilesDest,
    $ocrCacheDest,
    $docindexDest
)
$exclusionsFichiers = @(
    (Join-Path $app '_internal\backend\settings.json')
)

& robocopy $dist $app /MIR /NFL /NDL /NJH /NJS /NP /R:1 /W:1 `
    /XD $exclusionsDossiers /XF $exclusionsFichiers | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy a echoue (code $LASTEXITCODE)." }

# Lanceur et notice : versionnes dans portable\, toujours reecrits.
Copy-Item (Join-Path $root 'portable\*') -Destination $Destination -Force

# --- Verification ----------------------------------------------------------
Write-Etape 'Verification'
$controles = [ordered]@{
    'ai-webapp.exe'     = Join-Path $app 'ai-webapp.exe'
    'interface buildee' = Join-Path $app '_internal\frontend\dist\index.html'
    'moteur ollama'     = Join-Path $ollamaDest 'ollama.exe'
    'modeles'           = Join-Path $ollamaDest 'models'
    'moteur OCR'        = Join-Path $tesseractDest $exeOcr
    'langue OCR (fra)'  = Join-Path $tesseractDest 'tessdata\fra.traineddata'
    'lanceur (.bat)'    = Join-Path $Destination 'Lancer-Olivia.bat'
}
$manquants = @()
foreach ($c in $controles.GetEnumerator()) {
    if (Test-Path $c.Value) {
        Write-Host ('  OK      {0}' -f $c.Key) -ForegroundColor Green
    } else {
        Write-Host ('  MANQUE  {0}  ({1})' -f $c.Key, $c.Value) -ForegroundColor Red
        $manquants += $c.Key
    }
}

$convApres = if (Test-Path $dossierConv) {
    @(Get-ChildItem $dossierConv -Filter '*.json' -ErrorAction SilentlyContinue).Count
} else { 0 }
if ($convApres -ne $nbConversations) {
    Write-Host ('  ALERTE  conversations : {0} avant, {1} apres' -f `
                $nbConversations, $convApres) -ForegroundColor Red
    $manquants += 'conversations'
}

$chrono.Stop()
Write-Host ''
if ($manquants.Count -gt 0) {
    Write-Host ('Termine avec des manques : {0}' -f ($manquants -join ', ')) -ForegroundColor Red
    exit 1
}
Write-Host ('Deploiement termine en {0:N0}s. Total sur le disque : {1} Go.' -f `
            $chrono.Elapsed.TotalSeconds, (Get-TailleGo $Destination)) -ForegroundColor Green
Write-Host "Pour demarrer : double-clic sur $Destination\Lancer-Olivia.bat"

# Sortie explicite : sans elle, PowerShell propage le code de robocopy, dont les
# valeurs de succes vont de 0 a 7 (2 = elements presents en destination et absents
# de la source — exactement le cas de nos dossiers proteges). Un appelant y verrait
# un echec.
exit 0
