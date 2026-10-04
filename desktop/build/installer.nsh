; Ajouts à l'installeur Windows (NSIS, généré par electron-builder).
;
; Les données d'Olivia (comptes, réglages, conversations) vivent dans
; C:\ProgramData\Olivia, COMMUN à toutes les sessions Windows du poste : les
; comptes créés par le service informatique doivent servir à l'assistante de
; direction, qui travaille dans une autre session. Ce dossier n'est pas
; modifiable par un utilisateur standard par défaut : on y donne le droit de
; modification au groupe Utilisateurs (SID S-1-5-32-545, indépendant de la
; langue de Windows), hérité par les sous-dossiers et fichiers — l'équivalent
; de « Permissions: users-modify » de l'ancien installeur Inno Setup.
;
; Le dossier n'est JAMAIS supprimé à la désinstallation (conversations et
; comptes de l'établissement) : voir aussi deleteAppDataOnUninstall dans
; package.json.

!macro customInstall
  ReadEnvStr $0 PROGRAMDATA
  CreateDirectory "$0\Olivia"
  nsExec::ExecToLog 'icacls "$0\Olivia" /grant *S-1-5-32-545:(OI)(CI)M'
  Pop $1
!macroend
