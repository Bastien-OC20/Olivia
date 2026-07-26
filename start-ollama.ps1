# Démarre Ollama en version PORTABLE, avec les modèles stockés DANS le projet.
# Usage : clic droit → « Exécuter avec PowerShell », ou dans un terminal : .\start-ollama.ps1
# Laisser cette fenêtre ouverte : elle fait tourner le moteur Ollama (port 11434).
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$exe  = Join-Path $root "ollama\ollama.exe"
$env:OLLAMA_MODELS = Join-Path $root "ollama\models"

if (-not (Test-Path $exe)) {
    Write-Error "ollama.exe introuvable dans '$root\ollama'. Installez d'abord Ollama (archive portable) dans ce dossier."
    exit 1
}

New-Item -ItemType Directory -Force -Path $env:OLLAMA_MODELS | Out-Null
Write-Host "Ollama portable — modeles : $env:OLLAMA_MODELS" -ForegroundColor Green
Write-Host "Ecoute sur http://127.0.0.1:11434  (Ctrl+C pour arreter)" -ForegroundColor Green
& $exe serve
