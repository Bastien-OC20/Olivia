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
 * - Windows : %LOCALAPPDATA%\Olivia, PROPRE AU COMPTE WINDOWS. Les versions
 *   précédentes utilisaient C:\ProgramData\Olivia, commun au poste et rendu
 *   modifiable par tous : sur un poste partagé, un autre compte Windows
 *   pouvait y lire les conversations, copier un jeton de session ou remplacer
 *   un mot de passe (audit du 15/11/2026). « Local » et non « Roaming »
 *   (userData d'Electron) : l'index et le cache OCR sont volumineux, et un
 *   profil itinérant les recopierait à chaque ouverture de session Windows.
 * - macOS / Linux : dossier de l'application propre à l'utilisateur
 *   (~/Library/Application Support/Olivia), l'usage normal sur ces systèmes.
 */
function dossierDonnees ({ plateforme, env, dossierUtilisateur }) {
  if (env.OLIVIA_DATA_DIR) return env.OLIVIA_DATA_DIR
  if (plateforme === 'win32' && env.LOCALAPPDATA) {
    return path.win32.join(env.LOCALAPPDATA, 'Olivia')
  }
  return dossierUtilisateur
}

/**
 * Ancien dossier commun au poste (C:\ProgramData\Olivia), que le backend
 * reprend au premier démarrage dans le dossier du compte Windows puis retire
 * (variable OLIVIA_DATA_REPRISE, voir backend/emplacements.py). Chaîne vide
 * hors Windows, ou quand l'exploitant a choisi lui-même le dossier des données.
 */
function ancienDossierCommun ({ plateforme, env }) {
  if (plateforme !== 'win32' || env.OLIVIA_DATA_DIR || !env.PROGRAMDATA) return ''
  return path.win32.join(env.PROGRAMDATA, 'Olivia')
}

/**
 * Dossier des modèles d'IA COMMUN au poste (C:\ProgramData\Olivia\modeles-ia),
 * ou chaîne vide pour laisser le backend les ranger avec les données.
 *
 * Les modèles pèsent plusieurs Go et ne contiennent aucune donnée personnelle :
 * les ranger dans le dossier de chaque compte Windows ferait retélécharger
 * (et stocker) le tout pour chaque personne du poste. Ils restent donc partagés,
 * dans un sous-dossier que l'installeur ouvre en écriture (build/installer.nsh)
 * — et lui seul : comptes et conversations n'y sont plus.
 */
function dossierModelesCommun ({ plateforme, env, estInscriptible }) {
  if (plateforme !== 'win32' || env.OLLAMA_MODELS || env.OLIVIA_DATA_DIR || !env.PROGRAMDATA) return ''
  const commun = path.win32.join(env.PROGRAMDATA, 'Olivia', 'modeles-ia')
  return estInscriptible(commun) ? commun : ''
}

/** Variables d'environnement qui désignent ses dossiers au backend. */
function envDonnees ({ dossier, reprise = '', modeles = '' }) {
  const env = { OLIVIA_DATA_DIR: dossier }
  if (reprise) env.OLIVIA_DATA_REPRISE = reprise
  if (modeles) env.OLLAMA_MODELS = modeles
  return env
}

// Premier lancement : PyInstaller (décompression), antivirus et Ollama peuvent être lents.
const DELAI_DEMARRAGE_MS = 120_000
// Marge laissée au lanceur : il abandonne un peu AVANT Electron, pour que l'échec
// soit déclaré par le lanceur (qui arrête proprement Ollama) plutôt que par une
// attente d'Electron qui se terminerait au même instant.
const MARGE_LANCEUR_MS = 10_000

/** Valeur de `--max-wait` (secondes entières) transmise à launch.py. */
function delaiLanceurSecondes (delaiMs = DELAI_DEMARRAGE_MS, margeMs = MARGE_LANCEUR_MS) {
  return Math.max(1, Math.floor((delaiMs - margeMs) / 1000))
}

/**
 * Préférences de l'utilisatrice (fichier JSON du compte Windows). Un fichier
 * absent, vide ou abîmé ne doit jamais gêner le démarrage : valeurs par défaut.
 * Par défaut, AUCUN contact avec GitHub (majAuto: false).
 */
function lirePreferences (texte) {
  const defaut = { majAuto: false }
  if (typeof texte !== 'string' || !texte.trim()) return defaut
  try {
    const donnees = JSON.parse(texte)
    if (donnees && typeof donnees === 'object') {
      return { majAuto: donnees.majAuto === true }
    }
  } catch { /* fichier abîmé : valeurs par défaut */ }
  return defaut
}

/** Texte du fichier de préférences (seules les clés connues sont écrites). */
function preferencesVersTexte (preferences) {
  return JSON.stringify({ majAuto: preferences?.majAuto === true }, null, 2) + '\n'
}

/**
 * Filtre de copie de `ollama/` vers l'application (option `filter` de
 * fs.cpSync) : écarte le dossier `models` et tout ce qu'il contient. Les modèles
 * pèsent plusieurs Go (limite de 2 Gio par fichier de release) et Program Files
 * n'est pas inscriptible : ils sont téléchargés au premier lancement.
 * Insensible à la casse (Windows). Rend true pour copier.
 */
function copierSaufModeles (racine, chemin, chemins = path) {
  const relatif = chemins.relative(racine, chemin)
  if (!relatif) return true
  return chemins.normalize(relatif).split(/[\\/]/)[0].toLowerCase() !== 'models'
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
    // Sans cela, launch.py abandonne au bout de 30 s (son défaut) alors
    // qu'Electron patiente DELAI_DEMARRAGE_MS : au premier lancement lent
    // (antivirus), le moteur mourait avant que la fenêtre ait fini d'attendre.
    args.push('--max-wait', String(delaiLanceurSecondes()))
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

/**
 * Couleur de fond de la fenêtre, visible avant que l'interface ne s'affiche.
 * Elle reprend `--fond` des deux thèmes de frontend/src/style.css (à tenir
 * alignée) : sans cela, en thème clair, un éclair sombre précédait l'interface.
 * Le réglage « theme » de l'organisation n'est pas encore connu à ce stade :
 * on suit le thème de Windows, comme l'écran de connexion.
 * @param {boolean} sombre thème sombre de Windows (nativeTheme.shouldUseDarkColors)
 * @returns {string}
 */
function couleurFondFenetre(sombre) {
  return sombre ? '#0b1020' : '#f5f7fc'
}

module.exports = {
  couleurFondFenetre,
  PORT_PREFERE,
  PORT_MAX,
  choisirPort,
  dossierDonnees,
  ancienDossierCommun,
  dossierModelesCommun,
  envDonnees,
  DELAI_DEMARRAGE_MS,
  MARGE_LANCEUR_MS,
  delaiLanceurSecondes,
  lirePreferences,
  preferencesVersTexte,
  copierSaufModeles,
  commandeBackend,
  pythonDeveloppement,
  estAdresseInterne,
  estLienExterneAutorise,
}
