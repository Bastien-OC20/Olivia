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
const DELAI_DEMARRAGE_MS = 120_000    // premier lancement : PyInstaller + Ollama peuvent être lents
const DELAI_ARRET_MS = 8_000
const INTERVALLE_MAJ_MS = 6 * 3600 * 1000

let fenetre = null
let tray = null
let backend = null
let baseUrl = ''
let dossierDonnees = ''
let journal = null
let enFermeture = false
let avertiArrierePlan = false

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
  creerFenetre()
  creerMenu()
  creerTray()
  enregistrerRaccourci()
  enregistrerIpc()

  dossierDonnees = outils.dossierDonnees({
    plateforme: process.platform,
    env: process.env,
    dossierUtilisateur: app.getPath('userData'),
    estInscriptible,
  })
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
  verifierMisesAJour()
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
    throw new Error(`Le moteur d'Olivia est introuvable dans l'application (${commande}). `
      + 'Réinstallez Olivia.')
  }
  noter(`Lancement : ${commande} ${args.join(' ')}`)
  backend = spawn(commande, args, {
    cwd,
    env: { ...process.env, OLIVIA_DATA_DIR: dossierDonnees, PYTHONUNBUFFERED: '1' },
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
    if (inattendu) afficherErreur("Le moteur d'Olivia s'est arrêté de façon inattendue.")
  })
  backend.on('error', (e) => {
    noter(`Échec du lancement : ${e.message}`)
    backend = null
    afficherErreur(`Impossible de lancer le moteur d'Olivia : ${e.message}`)
  })
}

function attendreBackend () {
  const fin = Date.now() + DELAI_DEMARRAGE_MS
  return new Promise((resolve, reject) => {
    const essayer = () => {
      if (!backend) return reject(new Error("Le moteur d'Olivia n'a pas pu démarrer."))
      const req = http.get(`${baseUrl}/api/health`, (res) => {
        res.resume()
        if (res.statusCode === 200) return resolve()
        planifier()
      })
      req.on('error', planifier)
      req.setTimeout(2000, () => req.destroy())
    }
    const planifier = () => {
      if (Date.now() > fin) return reject(new Error("Olivia met trop de temps à démarrer."))
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
    title: 'Olivia',
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
        title: 'Olivia reste disponible',
        content: 'Olivia continue en arrière-plan. Clic sur son icône, ou Ctrl+Alt+O, '
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
function creerTray () {
  const image = nativeImage.createFromPath(path.join(__dirname, 'icons', 'tray.png'))
  tray = new Tray(image)
  tray.setToolTip('Olivia')
  tray.setContextMenu(Menu.buildFromTemplate([
    { label: 'Ouvrir Olivia', click: montrerFenetre },
    { label: 'Créer un compte…', click: creerCompte },
    { type: 'separator' },
    { label: 'Redémarrer Olivia', click: () => { app.relaunch(); app.quit() } },
    { label: 'Quitter Olivia', click: () => app.quit() },
  ]))
  // Windows : un clic sur l'icône ouvre la fenêtre (le menu est au clic droit).
  tray.on('click', basculerFenetre)
}

function creerMenu () {
  const surMac = process.platform === 'darwin'
  const modele = [
    ...(surMac ? [{
      label: 'Olivia',
      submenu: [
        { role: 'about', label: 'À propos d\'Olivia' },
        { type: 'separator' },
        { label: 'Créer un compte…', click: creerCompte },
        { type: 'separator' },
        { role: 'hide', label: 'Masquer Olivia' },
        { role: 'hideOthers', label: 'Masquer les autres' },
        { role: 'unhide', label: 'Tout afficher' },
        { type: 'separator' },
        { role: 'quit', label: 'Quitter Olivia' },
      ],
    }] : [{
      label: 'Fichier',
      submenu: [
        { label: 'Créer un compte…', click: creerCompte },
        { type: 'separator' },
        { role: 'quit', label: 'Quitter Olivia' },
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
  const env = { ...process.env, OLIVIA_DATA_DIR: dossierDonnees, OLIVIA_PAUSE_FIN: '1' }
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
 * Mises à jour automatiques (electron-updater, depuis les « releases » GitHub
 * du dépôt, voir package.json > build.publish). Désactivées en développement,
 * et sur macOS tant que l'application n'est pas signée : macOS refuse
 * d'installer une mise à jour non signée. Une erreur (pas de connexion, dépôt
 * privé) est seulement notée dans le journal.
 */
function verifierMisesAJour () {
  if (!app.isPackaged) return
  const config = require('./package.json')
  if (process.platform === 'darwin' && !config.olivia?.majAutoMac) return
  let autoUpdater
  try {
    ({ autoUpdater } = require('electron-updater'))
  } catch (e) {
    return noter(`Mises à jour indisponibles : ${e.message}`)
  }
  autoUpdater.on('error', (e) => noter(`Mise à jour : ${e.message}`))
  autoUpdater.on('update-downloaded', async (info) => {
    const { response } = await dialog.showMessageBox({
      type: 'info',
      buttons: ['Redémarrer maintenant', 'Plus tard'],
      defaultId: 0,
      message: `Une nouvelle version d'Olivia (${info.version}) est prête.`,
      detail: 'Elle sera installée au prochain redémarrage d\'Olivia.',
    })
    if (response === 0) {
      enFermeture = true
      await arreterBackend()
      autoUpdater.quitAndInstall()
    }
  })
  const verifier = () => autoUpdater.checkForUpdates().catch((e) => noter(`Mise à jour : ${e.message}`))
  verifier()
  setInterval(verifier, INTERVALLE_MAJ_MS).unref()
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
