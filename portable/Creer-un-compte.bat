@echo off
rem ============================================================
rem  Oliv'IA - creation d'un compte (service informatique)
rem  A lancer une premiere fois apres l'installation : Oliv'IA
rem  demande une connexion, et aucun compte n'existe au depart.
rem  Sert aussi, plus tard, a ajouter un compte.
rem ============================================================
title Oliv'IA - creation d'un compte

cd /d "%~dp0ai-webapp"

if not exist "ai-webapp.exe" (
    echo.
    echo   ERREUR : ai-webapp.exe est introuvable.
    echo   Le dossier "ai-webapp" doit se trouver a cote de ce fichier.
    echo.
    pause
    exit /b 1
)

"ai-webapp.exe" init

echo.
pause
