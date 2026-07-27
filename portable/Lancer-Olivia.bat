@echo off
rem ============================================================
rem  Olivia - version portable
rem  Double-cliquez sur ce fichier pour demarrer l'assistante.
rem  Tout (application, moteur, modeles, reglages, conversations)
rem  reste sur ce disque : rien n'est installe sur l'ordinateur.
rem ============================================================
title Olivia - assistante locale

cd /d "%~dp0ai-webapp"

if not exist "ai-webapp.exe" (
    echo.
    echo   ERREUR : ai-webapp.exe est introuvable.
    echo   Le dossier "ai-webapp" doit se trouver a cote de ce fichier.
    echo.
    pause
    exit /b 1
)

echo.
echo   Demarrage d'Olivia... la fenetre du navigateur s'ouvre toute seule.
echo   Laissez cette fenetre noire ouverte pendant l'utilisation.
echo   Pour quitter : fermez cette fenetre.
echo.

"ai-webapp.exe"
