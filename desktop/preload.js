'use strict'
/**
 * Pont minimal entre l'interface d'Olivia et l'application de bureau.
 *
 * L'interface reste une page web ordinaire (contextIsolation, sandbox, pas de
 * Node) : elle ne reçoit QUE ce qui est exposé ici. Sa présence permet à
 * l'interface de savoir qu'elle tourne dans l'application de bureau, et d'y
 * proposer d'ouvrir l'assistant de création de compte (écran de connexion
 * d'une installation neuve).
 */
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('oliviaBureau', {
  plateforme: process.platform,
  creerCompte: () => ipcRenderer.invoke('olivia:creer-compte'),
})
