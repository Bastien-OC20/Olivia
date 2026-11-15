; Ajouts à l'installeur Windows (NSIS, généré par electron-builder).
;
; Les DONNÉES d'Olivia (comptes, sessions, réglages, conversations, index) ne
; vivent plus dans C:\ProgramData\Olivia : ce dossier commun, que l'installeur
; ouvrait en écriture à tous les utilisateurs du poste, laissait n'importe quel
; autre compte Windows lire les conversations, copier un jeton de session ou
; remplacer un mot de passe (audit du 15/11/2026). Elles sont désormais dans le
; profil du compte Windows (%LOCALAPPDATA%\Olivia, voir lib/outils.js), et
; l'ancien dossier est repris au premier démarrage (backend/emplacements.py).
;
; Seuls les MODÈLES D'IA restent communs au poste : plusieurs Go, aucune donnée
; personnelle, et les retélécharger pour chaque compte Windows n'aurait aucun
; sens. On ne donne donc le droit de modification au groupe Utilisateurs (SID
; S-1-5-32-545, indépendant de la langue de Windows) que sur le sous-dossier
; modeles-ia — plus sur C:\ProgramData\Olivia lui-même.
;
; Ce dossier n'est jamais supprimé à la désinstallation (modèles longs à
; retélécharger) ; les données, elles, sont dans le profil de chacun.

!macro customInstall
  ReadEnvStr $0 PROGRAMDATA
  CreateDirectory "$0\Olivia\modeles-ia"
  nsExec::ExecToLog 'icacls "$0\Olivia\modeles-ia" /grant *S-1-5-32-545:(OI)(CI)M'
  Pop $1
!macroend
