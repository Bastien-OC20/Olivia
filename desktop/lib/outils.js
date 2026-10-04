'use strict'
/**
 * Fonctions pures de l'application de bureau (sans Electron), testées par
 * desktop/test/outils.test.js : choix du port, du dossier des données, du
 * backend à lancer, et filtrage des adresses autorisées dans la fenêtre.
 */
const path = require('node:path')

// Port préféré : celui de toujours (8000), pour que l'origine de l'interface —
// donc son stockage local et ses cookies — reste la même d'un lancement à
// l'autre. On n'en change que s'il est déjà pris.
const PORT_PREFERE = 8000
const PORT_MAX = 8020

/**
 * Premier port libre entre `debut` et `fin` (inclus), ou null.
 * `estLibre(port)` est asynchrone (voir main.js) : injecté pour les tests.
 */
async function choisirPort (estLibre, debut = PORT_PREFERE, fin = PORT_MAX) {
  for (let port = debut; port <= fin; port++) {
    if (await estLibre(port)) return port
  }
  return null
}

/**
 * Dossier des données d'Olivia (comptes, réglages, conversations), transmis au
 * backend par la variable OLIVIA_DATA_DIR (voir backend/emplacements.py).
 *
 * - Windows : C:\ProgramData\Olivia, COMMUN au poste, comme l'installeur
 *   historique — les comptes créés par le service informatique servent à
 *   toutes les sessions Windows. L'installeur le rend modifiable par les
 *   utilisateurs (build/installer.nsh). S'il ne l'est pas (installation
 *   manuelle, droits retirés), repli sur le dossier propre à l'utilisateur.
 * - macOS / Linux : dossier de l'application propre à l'utilisateur
 *   (~/Library/Application Support/Olivia), l'usage normal sur ces systèmes.
 */
function dossierDonnees ({ plateforme, env, dossierUtilisateur, estInscriptible }) {
  if (env.OLIVIA_DATA_DIR) return env.OLIVIA_DATA_DIR
  if (plateforme === 'win32' && env.PROGRAMDATA) {
    const commun = path.win32.join(env.PROGRAMDATA, 'Olivia')
    if (estInscriptible(commun)) return commun
  }
  return dossierUtilisateur
}

/**
 * Commande qui lance le backend.
 * - Application empaquetée : l'exécutable PyInstaller embarqué dans les
 *   ressources (resources/backend/ai-webapp[.exe]), avec Ollama et Tesseract
 *   éventuels à côté de lui — là où launch.py les cherche.
 * - Développement : uvicorn depuis le dépôt, avec le Python du venv backend.
 */
function commandeBackend ({ empaquete, plateforme, ressources, depot, port, pythonDev }) {
  const args = ['--no-browser', '--port', String(port), '--parent-stdin']
  if (empaquete) {
    const nom = plateforme === 'win32' ? 'ai-webapp.exe' : 'ai-webapp'
    const exe = path.join(ressources, 'backend', nom)
    return { commande: exe, args, cwd: path.dirname(exe) }
  }
  return {
    commande: pythonDev,
    args: ['-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', String(port)],
    cwd: depot,
  }
}

/** Python du développement : OLIVIA_PYTHON s'il est défini, sinon celui du
 *  venv backend, sinon celui du système. */
function pythonDeveloppement ({ plateforme, depot, existe, env = {} }) {
  if (env.OLIVIA_PYTHON) return env.OLIVIA_PYTHON
  const venv = plateforme === 'win32'
    ? path.join(depot, 'backend', '.venv', 'Scripts', 'python.exe')
    : path.join(depot, 'backend', '.venv', 'bin', 'python')
  if (existe(venv)) return venv
  return plateforme === 'win32' ? 'python' : 'python3'
}

/** La fenêtre ne navigue QUE vers l'interface d'Olivia (même origine). */
function estAdresseInterne (url, base) {
  try {
    return new URL(url).origin === new URL(base).origin
  } catch {
    return false
  }
}

/** Liens ouverts dans le navigateur du système : web uniquement. */
function estLienExterneAutorise (url) {
  try {
    const { protocol } = new URL(url)
    return protocol === 'https:' || protocol === 'http:'
  } catch {
    return false
  }
}

module.exports = {
  PORT_PREFERE,
  PORT_MAX,
  choisirPort,
  dossierDonnees,
  commandeBackend,
  pythonDeveloppement,
  estAdresseInterne,
  estLienExterneAutorise,
}
