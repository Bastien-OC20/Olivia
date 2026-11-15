'use strict'
/**
 * Olivia — application de bureau (macOS, Windows).
 *
 * Une vraie fenêtre au lieu d'un onglet de navigateur, une icône dans la barre
 * des menus (macOS) ou la zone de notification (Windows), un raccourci clavier
 * global, des installeurs .dmg / .exe et les mises à jour automatiques.
 *
 * Architecture : ce processus lance le backend existant (FastAPI + interface
 * Vue, compilé par PyInstaller et embarqué dans les ressources), attend qu'il
 * réponde, puis affiche son interface dans la fenêtre. Rien n'est réécrit :
 * l'application de bureau ENVELOPPE Olivia, elle ne la remplace pas. Tout reste
 * local — la fenêtre ne charge que http://127.0.0.1, et aucune donnée ne sort
 * de la machine.
 */
const {
  app, BrowserWindow, Tray, Menu, globalShortcut, shell, dialog, ipcMain, nativeImage,
  session,
} = require('electron')
const { spawn } = require('node:child_process')
const fs = require('node:fs')
const http = require('node:http')
const net = require('node:net')
const path = require('node:path')
const outils = require('./lib/outils')

const RACCOURCI = 'CommandOrControl+Alt+O'
const DELAI_DEMARRAGE_MS = outils.DELAI_DEMARRAGE_MS   // le même que celui transmis à launch.py
const DELAI_ARRET_MS = 8_000
const INTERVALLE_MAJ_MS = 6 * 3600 * 1000

let fenetre = null
let tray = null
let backend = null
let baseUrl = ''
let dossierDonnees = ''
// Ancien dossier commun au poste, à reprendre une fois (voir lib/outils.js).
let repriseDonnees = ''
// Dossier des modèles d'IA partagé par les comptes Windows du poste (ou vide).
let modelesCommuns = ''
let journal = null
let enFermeture = false
let avertiArrierePlan = false
// Préférences du compte Windows (preferences.json) : voir chargerPreferences().
let preferences = { majAuto: false }
let minuterieMaj = null
let updater = null
let verificationEnCours = false

// Une seule instance : un second lancement ramène simplement la fenêtre.
if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => montrerFenetre())
  app.whenReady().then(demarrer)
}

if (process.platform === 'win32') app.setAppUserModelId('fr.olivia.assistante')

// ---------------------------------------------------------------- démarrage
async function demarrer () {
  ouvrirJournal()
  securiser()
  chargerPreferences()
  creerFenetre()
  creerMenu()
  creerTray()
  enregistrerRaccourci()
  enregistrerIpc()

  dossierDonnees = outils.dossierDonnees({
    plateforme: process.platform,
    env: process.env,
    dossierUtilisateur: app.getPath('userData'),
  })
  repriseDonnees = outils.ancienDossierCommun({ plateforme: process.platform, env: process.env })
  modelesCommuns = outils.dossierModelesCommun({ plateforme: process.platform, env: process.env, estInscriptible })
  noter(`Données : ${dossierDonnees}`)

  const port = await outils.choisirPort(portLibre)
  if (port === null) {
    return afficherErreur('Aucun port local libre entre 8000 et 8020.')
  }
  baseUrl = `http://127.0.0.1:${port}`
  try {
    lancerBackend(port)
    await attendreBackend()
  } catch (e) {
    return afficherErreur(e.message)
  }
  fenetre.loadURL(`${baseUrl}/ui/`)
  // Aucun contact avec GitHub tant que l'utilisatrice n'a pas activé l'option.
  if (preferences.majAuto) demarrerMajAuto()
}

function lancerBackend (port) {
  const empaquete = app.isPackaged
  const depot = path.resolve(__dirname, '..')
  const { commande, args, cwd } = outils.commandeBackend({
    empaquete,
    plateforme: process.platform,
    ressources: process.resourcesPath,
    depot,
    port,
    pythonDev: outils.pythonDeveloppement({ plateforme: process.platform, depot, existe: fs.existsSync, env: process.env }),
  })
  if (empaquete && !fs.existsSync(commande)) {
    throw new Error(`Le moteur d'Oliv'IA est introuvable dans l'application (${commande}). `
      + "Réinstallez Oliv'IA.")
  }
  noter(`Lancement : ${commande} ${args.join(' ')}`)
  backend = spawn(commande, args, {
    cwd,
    env: { ...process.env, ...outils.envDonnees({ dossier: dossierDonnees, reprise: repriseDonnees, modeles: modelesCommuns }), PYTHONUNBUFFERED: '1' },
    // stdin gardé ouvert : sa fermeture arrête le backend (--parent-stdin).
    stdio: ['pipe', 'pipe', 'pipe'],
    windowsHide: true,
  })
  backend.stdout.on('data', (d) => noter(d.toString().trimEnd()))
  backend.stderr.on('data', (d) => noter(d.toString().trimEnd()))
  backend.on('exit', (code, signal) => {
    noter(`Backend arrêté (code ${code}, signal ${signal})`)
    const inattendu = !enFermeture
    backend = null
    if (inattendu) afficherErreur("Le moteur d'Oliv'IA s'est arrêté de façon inattendue.")
  })
  backend.on('error', (e) => {
    noter(`Échec du lancement : ${e.message}`)
    backend = null
    afficherErreur(`Impossible de lancer le moteur d'Oliv'IA : ${e.message}`)
  })
}

function attendreBackend () {
  const fin = Date.now() + DELAI_DEMARRAGE_MS
  return new Promise((resolve, reject) => {
    const essayer = () => {
      if (!backend) return reject(new Error("Le moteur d'Oliv'IA n'a pas pu démarrer."))
      const req = http.get(`${baseUrl}/api/health`, (res) => {
        res.resume()
        if (res.statusCode === 200) return resolve()
        planifier()
      })
      req.on('error', planifier)
      req.setTimeout(2000, () => req.destroy())
    }
    const planifier = () => {
      if (Date.now() > fin) return reject(new Error("Oliv'IA met trop de temps à démarrer."))
      setTimeout(essayer, 500)
    }
    essayer()
  })
}

/** Arrête le backend proprement : fermeture de son entrée standard, puis
 *  arrêt forcé s'il ne s'est pas arrêté de lui-même dans le délai. */
function arreterBackend () {
  return new Promise((resolve) => {
    if (!backend) return resolve()
    const proc = backend
    const forcer = setTimeout(() => { try { proc.kill() } catch { /* déjà arrêté */ } }, DELAI_ARRET_MS)
    proc.once('exit', () => { clearTimeout(forcer); resolve() })
    try { proc.stdin.end() } catch { proc.kill() }
  })
}

app.on('before-quit', (event) => {
  enFermeture = true
  if (backend) {
    event.preventDefault()
    arreterBackend().then(() => app.quit())
  }
})
app.on('will-quit', () => globalShortcut.unregisterAll())
// Fenêtre fermée : Olivia reste dans la barre des menus / zone de notification.
app.on('window-all-closed', () => {})
app.on('activate', () => montrerFenetre())

// ---------------------------------------------------------------- fenêtre
function creerFenetre () {
  fenetre = new BrowserWindow({
    width: 1200,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: 'Oliv\'IA',
    icon: path.join(__dirname, 'icons', 'fenetre.png'),
    autoHideMenuBar: true,
    show: false,
    backgroundColor: '#0f1115',
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  })
  fenetre.once('ready-to-show', () => fenetre.show())
  fenetre.loadFile(path.join(__dirname, 'chargement.html'))
  fenetre.on('close', (event) => {
    if (enFermeture) return
    event.preventDefault()
    fenetre.hide()
    if (process.platform === 'win32' && tray && !avertiArrierePlan) {
      avertiArrierePlan = true
      tray.displayBalloon({
        title: 'Oliv\'IA reste disponible',
        content: 'Oliv\'IA continue en arrière-plan. Clic sur son icône, ou Ctrl+Alt+O, '
          + 'pour la rouvrir. Pour la quitter : clic droit sur l\'icône > Quitter.',
        iconType: 'info',
      })
    }
  })
}

function montrerFenetre () {
  if (!fenetre) return
  if (fenetre.isMinimized()) fenetre.restore()
  fenetre.show()
  fenetre.focus()
}

function basculerFenetre () {
  if (fenetre && fenetre.isVisible() && fenetre.isFocused()) fenetre.hide()
  else montrerFenetre()
}

function afficherErreur (message) {
  noter(`ERREUR : ${message}`)
  if (!fenetre) return
  fenetre.loadFile(path.join(__dirname, 'chargement.html'), {
    query: { erreur: message, journal: cheminJournal() },
  })
  montrerFenetre()
}

// ---------------------------------------------------------------- tray, menus, raccourci
function menuTray () {
  return Menu.buildFromTemplate([
    { label: 'Ouvrir Oliv\'IA', click: montrerFenetre },
    { label: 'Créer un compte…', click: creerCompte },
    { type: 'separator' },
    ...entreesMiseAJour(),
    { type: 'separator' },
    { label: 'Redémarrer Oliv\'IA', click: () => { app.relaunch(); app.quit() } },
    { label: 'Quitter Oliv\'IA', click: () => app.quit() },
  ])
}

function creerTray () {
  const image = nativeImage.createFromPath(path.join(__dirname, 'icons', 'tray.png'))
  tray = new Tray(image)
  tray.setToolTip('Oliv\'IA')
  tray.setContextMenu(menuTray())
  // Windows : un clic sur l'icône ouvre la fenêtre (le menu est au clic droit).
  tray.on('click', basculerFenetre)
}

/** Reconstruit les menus : la case « Mises à jour automatiques » doit
 *  refléter l'état réel dans le menu de l'application ET celui de l'icône. */
function rafraichirMenus () {
  creerMenu()
  if (tray) tray.setContextMenu(menuTray())
}

function creerMenu () {
  const surMac = process.platform === 'darwin'
  const modele = [
    ...(surMac ? [{
      label: 'Oliv\'IA',
      submenu: [
        { role: 'about', label: 'À propos d\'Oliv\'IA' },
        { type: 'separator' },
        { label: 'Créer un compte…', click: creerCompte },
        { type: 'separator' },
        ...entreesMiseAJour(),
        { type: 'separator' },
        { role: 'hide', label: 'Masquer Oliv\'IA' },
        { role: 'hideOthers', label: 'Masquer les autres' },
        { role: 'unhide', label: 'Tout afficher' },
        { type: 'separator' },
        { role: 'quit', label: 'Quitter Oliv\'IA' },
      ],
    }] : [{
      label: 'Fichier',
      submenu: [
        { label: 'Créer un compte…', click: creerCompte },
        { type: 'separator' },
        ...entreesMiseAJour(),
        { type: 'separator' },
        { role: 'quit', label: 'Quitter Oliv\'IA' },
      ],
    }]),
    // Indispensable sur macOS : sans menu Édition, Cmd+C / Cmd+V ne
    // fonctionnent pas dans les champs de saisie.
    {
      label: 'Édition',
      submenu: [
        { role: 'undo', label: 'Annuler' },
        { role: 'redo', label: 'Rétablir' },
        { type: 'separator' },
        { role: 'cut', label: 'Couper' },
        { role: 'copy', label: 'Copier' },
        { role: 'paste', label: 'Coller' },
        { role: 'selectAll', label: 'Tout sélectionner' },
      ],
    },
    {
      label: 'Affichage',
      submenu: [
        { role: 'reload', label: 'Recharger' },
        { type: 'separator' },
        { role: 'resetZoom', label: 'Taille réelle' },
        { role: 'zoomIn', label: 'Zoom avant' },
        { role: 'zoomOut', label: 'Zoom arrière' },
        { type: 'separator' },
        { role: 'togglefullscreen', label: 'Plein écran' },
        ...(app.isPackaged ? [] : [{ role: 'toggleDevTools', label: 'Outils de développement' }]),
      ],
    },
    { role: 'windowMenu', label: 'Fenêtre' },
  ]
  Menu.setApplicationMenu(Menu.buildFromTemplate(modele))
}

function enregistrerRaccourci () {
  if (!globalShortcut.register(RACCOURCI, basculerFenetre)) {
    // Déjà pris par une autre application : Olivia reste utilisable par
    // l'icône et le Dock / la barre des tâches.
    noter(`Raccourci ${RACCOURCI} indisponible (déjà utilisé par une autre application).`)
  }
}

// ---------------------------------------------------------------- création de compte
/**
 * Ouvre l'assistant de création de compte (`init`, backend/manage_users.py)
 * dans une fenêtre de terminal, avec le même dossier de données que
 * l'application. La création reste en ligne de commande, comme voulu dans le
 * projet (préparée par le service informatique, pas d'inscription dans
 * l'interface) : l'application ne fait que l'ouvrir au bon endroit.
 */
function creerCompte () {
  const empaquete = app.isPackaged
  const depot = path.resolve(__dirname, '..')
  let commande, args, cwd
  if (empaquete) {
    const nom = process.platform === 'win32' ? 'ai-webapp.exe' : 'ai-webapp'
    commande = path.join(process.resourcesPath, 'backend', nom)
    args = ['init']
    cwd = path.dirname(commande)
  } else {
    commande = outils.pythonDeveloppement({ plateforme: process.platform, depot, existe: fs.existsSync, env: process.env })
    args = [path.join(depot, 'launch.py'), 'init']
    cwd = depot
  }
  const env = { ...process.env, ...outils.envDonnees({ dossier: dossierDonnees, reprise: repriseDonnees, modeles: modelesCommuns }), OLIVIA_PAUSE_FIN: '1' }
  noter(`Création de compte : ${commande} ${args.join(' ')}`)

  if (process.platform === 'win32') {
    // `detached` : le programme console obtient sa propre fenêtre.
    spawn(commande, args, { cwd, env, detached: true, stdio: 'ignore', windowsHide: false }).unref()
  } else if (process.platform === 'darwin') {
    // Un script .command s'ouvre dans le Terminal de macOS.
    const script = path.join(app.getPath('temp'), 'olivia-creer-compte.command')
    const q = (s) => `'${String(s).replace(/'/g, "'\\''")}'`
    fs.writeFileSync(script, [
      '#!/bin/sh',
      `export OLIVIA_DATA_DIR=${q(dossierDonnees)}`,
      'export OLIVIA_PAUSE_FIN=1',
      `cd ${q(cwd)}`,
      [commande, ...args].map(q).join(' '),
      '',
    ].join('\n'), { mode: 0o755 })
    shell.openPath(script)
  } else {
    const proc = spawn('x-terminal-emulator', ['-e', commande, ...args],
      { cwd, env, detached: true, stdio: 'ignore' })
    proc.on('error', () => dialog.showMessageBox({
      type: 'info',
      message: 'Ouvrez un terminal et lancez :',
      detail: `OLIVIA_DATA_DIR="${dossierDonnees}" "${commande}" ${args.join(' ')}`,
    }))
    proc.unref()
  }
}

// ---------------------------------------------------------------- sécurité
function securiser () {
  // Olivia n'a besoin d'aucune permission du navigateur (caméra, micro,
  // localisation…) : tout est refusé, sauf l'écriture dans le presse-papiers.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, rappel) => {
    rappel(permission === 'clipboard-sanitized-write')
  })
  app.on('web-contents-created', (_e, contents) => {
    // La fenêtre ne quitte jamais l'interface d'Olivia…
    contents.on('will-navigate', (event, url) => {
      if (!baseUrl || !outils.estAdresseInterne(url, baseUrl)) event.preventDefault()
    })
    // … et les liens (sources web d'une réponse) s'ouvrent dans le
    // navigateur du système, jamais dans une fenêtre Electron.
    contents.setWindowOpenHandler(({ url }) => {
      if (outils.estLienExterneAutorise(url)) shell.openExternal(url)
      return { action: 'deny' }
    })
  })
}

function enregistrerIpc () {
  // Seule action exposée à l'interface (via preload.js) : ouvrir l'assistant
  // de création de compte. Aucune donnée, aucun argument ne transite.
  ipcMain.handle('olivia:creer-compte', (event) => {
    if (!baseUrl || !outils.estAdresseInterne(event.senderFrame.url, baseUrl)) return false
    creerCompte()
    return true
  })
}

// ---------------------------------------------------------------- mises à jour
/**
 * Mises à jour (electron-updater, depuis les « releases » GitHub du dépôt, voir
 * package.json > build.publish). DÉSACTIVÉES PAR DÉFAUT : la vérification
 * contacte GitHub (adresse de la machine, version installée), ce qui contredit
 * la promesse « rien ne sort du poste » tant que l'utilisatrice ne l'a pas
 * voulu. Le choix est mémorisé dans preferences.json (dossier userData).
 * Indisponibles en développement, et sur macOS tant que l'application n'est
 * pas signée (macOS refuse d'installer une mise à jour non signée).
 */
const PHRASE_GITHUB = "La vérification contacte le site GitHub : il reçoit l'adresse de cet "
  + "ordinateur et la version d'Oliv'IA installée. Aucun document ni aucune conversation n'est envoyé."

function cheminPreferences () {
  return path.join(app.getPath('userData'), 'preferences.json')
}

/** Lit les préférences ; un fichier absent ou illisible ne bloque jamais le démarrage. */
function chargerPreferences () {
  try {
    preferences = outils.lirePreferences(fs.readFileSync(cheminPreferences(), 'utf8'))
  } catch {
    preferences = outils.lirePreferences('')
  }
}

function enregistrerPreferences () {
  try {
    fs.mkdirSync(path.dirname(cheminPreferences()), { recursive: true })
    fs.writeFileSync(cheminPreferences(), outils.preferencesVersTexte(preferences))
  } catch (e) {
    noter(`Préférences non enregistrées : ${e.message}`)
  }
}

/** Raison pour laquelle la mise à jour est impossible ici, ou '' si elle l'est. */
function majIndisponible () {
  if (!app.isPackaged) {
    return "La mise à jour n'est pas disponible en développement."
  }
  const config = require('./package.json')
  if (process.platform === 'darwin' && !config.olivia?.majAutoMac) {
    return "Sur Mac, Oliv'IA se met à jour en la réinstallant : téléchargez la dernière "
      + "version, puis remplacez l'application par la nouvelle."
  }
  return ''
}

function obtenirUpdater () {
  if (updater) return updater
  ;({ autoUpdater: updater } = require('electron-updater'))
  updater.on('error', (e) => noter(`Mise à jour : ${e.message}`))
  updater.on('update-downloaded', async (info) => {
    const { response } = await dialog.showMessageBox({
      type: 'info',
      buttons: ['Redémarrer maintenant', 'Plus tard'],
      defaultId: 0,
      message: `Une nouvelle version d'Oliv'IA (${info.version}) est prête.`,
      detail: "Elle sera installée au prochain redémarrage d'Oliv'IA.",
    })
    if (response === 0) {
      enFermeture = true
      await arreterBackend()
      updater.quitAndInstall()
    }
  })
  return updater
}

/**
 * Une vérification. Rend { etat: 'a-jour' | 'telechargement' | 'impossible', version }.
 * Le téléchargement démarre tout seul ; le dialogue « prête, redémarrer ? » prend le relais.
 */
async function verifierUneFois () {
  if (verificationEnCours) return { etat: 'en-cours' }
  verificationEnCours = true
  noter('Mise à jour : vérification (contact avec GitHub)')
  try {
    const resultat = await obtenirUpdater().checkForUpdates()
    if (!resultat || !resultat.updateInfo) {
      noter('Mise à jour : aucune réponse exploitable')
      return { etat: 'impossible' }
    }
    const version = resultat.updateInfo.version
    const disponible = typeof resultat.isUpdateAvailable === 'boolean'
      ? resultat.isUpdateAvailable
      : version !== app.getVersion()
    noter(disponible ? `Mise à jour : version ${version} disponible` : 'Mise à jour : à jour')
    return { etat: disponible ? 'telechargement' : 'a-jour', version }
  } catch (e) {
    noter(`Mise à jour : ${e.message}`)
    return { etat: 'impossible' }
  } finally {
    verificationEnCours = false
  }
}

/** Active la vérification périodique : tout de suite, puis toutes les 6 h. */
function demarrerMajAuto () {
  if (minuterieMaj || majIndisponible()) return
  try {
    obtenirUpdater()
  } catch (e) {
    return noter(`Mises à jour indisponibles : ${e.message}`)
  }
  verifierUneFois()
  minuterieMaj = setInterval(verifierUneFois, INTERVALLE_MAJ_MS)
  minuterieMaj.unref()
}

function arreterMajAuto () {
  if (minuterieMaj) clearInterval(minuterieMaj)
  minuterieMaj = null
}

async function basculerMajAuto () {
  const raison = majIndisponible()
  if (raison) {
    await dialog.showMessageBox({ type: 'info', message: 'Mises à jour automatiques', detail: raison })
  } else if (!preferences.majAuto) {
    const { response } = await dialog.showMessageBox({
      type: 'question',
      buttons: ['Activer', 'Annuler'],
      defaultId: 1,
      cancelId: 1,
      message: 'Activer les mises à jour automatiques ?',
      detail: `Oliv'IA cherchera une nouvelle version au démarrage, puis toutes les 6 heures, `
        + `la téléchargera et vous proposera de redémarrer.\n\n${PHRASE_GITHUB}`,
    })
    if (response === 0) {
      preferences = { ...preferences, majAuto: true }
      enregistrerPreferences()
      noter('Mises à jour automatiques : activées')
      demarrerMajAuto()
    }
  } else {
    preferences = { ...preferences, majAuto: false }
    enregistrerPreferences()
    arreterMajAuto()
    noter('Mises à jour automatiques : désactivées')
  }
  rafraichirMenus()
}

async function rechercherMiseAJour () {
  const raison = majIndisponible()
  if (raison) {
    return dialog.showMessageBox({ type: 'info', message: 'Rechercher une mise à jour', detail: raison })
  }
  const message = 'Rechercher une mise à jour'
  const { etat, version } = await verifierUneFois()
  if (etat === 'en-cours') {
    return dialog.showMessageBox({ type: 'info', message, detail: 'Une recherche est déjà en cours. Patientez un instant.' })
  }
  if (etat === 'a-jour') {
    return dialog.showMessageBox({
      type: 'info', message: "Oliv'IA est à jour.", detail: `Vous utilisez la dernière version (${app.getVersion()}).\n\n${PHRASE_GITHUB}`,
    })
  }
  if (etat === 'telechargement') {
    return dialog.showMessageBox({
      type: 'info',
      message: `Une nouvelle version d'Oliv'IA (${version}) est disponible.`,
      detail: "Elle se télécharge en arrière-plan. Oliv'IA vous proposera de redémarrer dès qu'elle sera prête.",
    })
  }
  return dialog.showMessageBox({
    type: 'warning',
    message: 'Impossible de vérifier les mises à jour.',
    detail: "Vérifiez que cet ordinateur est connecté à Internet, puis réessayez. "
      + `Si le problème continue, contactez la personne qui s'occupe d'Oliv'IA.\n\n${PHRASE_GITHUB}`,
  })
}

/** Entrées de menu communes (menu de l'application et menu de l'icône). */
function entreesMiseAJour () {
  return [
    {
      label: 'Mises à jour automatiques',
      type: 'checkbox',
      checked: preferences.majAuto,
      click: basculerMajAuto,
    },
    { label: 'Rechercher une mise à jour…', click: rechercherMiseAJour },
  ]
}

// ---------------------------------------------------------------- utilitaires
function portLibre (port) {
  return new Promise((resolve) => {
    const serveur = net.createServer()
    serveur.once('error', () => resolve(false))
    serveur.once('listening', () => serveur.close(() => resolve(true)))
    serveur.listen(port, '127.0.0.1')
  })
}

// Sert au dossier COMMUN des modèles d'IA (voir lib/outils.js) : créé et ouvert
// en écriture par l'installeur, mais pas sur une installation manuelle.
function estInscriptible (dossier) {
  try {
    fs.mkdirSync(dossier, { recursive: true })
    const essai = path.join(dossier, '.olivia-essai-ecriture')
    fs.writeFileSync(essai, 'ok')
    fs.unlinkSync(essai)
    return true
  } catch {
    return false
  }
}

function cheminJournal () {
  return path.join(app.getPath('logs'), 'olivia.log')
}

function ouvrirJournal () {
  try {
    fs.mkdirSync(app.getPath('logs'), { recursive: true })
    journal = fs.createWriteStream(cheminJournal(), { flags: 'a' })
  } catch {
    journal = null
  }
}

function noter (texte) {
  const ligne = `[${new Date().toISOString()}] ${texte}\n`
  if (journal) journal.write(ligne)
  if (!app.isPackaged) process.stdout.write(ligne)
}
