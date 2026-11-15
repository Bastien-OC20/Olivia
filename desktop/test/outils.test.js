'use strict'
// Tests des fonctions pures de l'application de bureau : `npm test` (node --test).
const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const outils = require('../lib/outils')

test('choisirPort garde 8000 quand il est libre', async () => {
  assert.equal(await outils.choisirPort(async () => true), 8000)
})

test('choisirPort prend le suivant libre, ou null si tout est pris', async () => {
  const pris = new Set([8000, 8001])
  assert.equal(await outils.choisirPort(async (p) => !pris.has(p)), 8002)
  assert.equal(await outils.choisirPort(async () => false), null)
})

test('dossierDonnees : Windows → dossier du compte Windows, jamais ProgramData', () => {
  const d = outils.dossierDonnees({
    plateforme: 'win32',
    env: { PROGRAMDATA: 'C:\\ProgramData', LOCALAPPDATA: 'C:\\Users\\marie\\AppData\\Local' },
    dossierUtilisateur: 'C:\\Users\\marie\\AppData\\Roaming\\Olivia',
  })
  assert.equal(d, 'C:\\Users\\marie\\AppData\\Local\\Olivia')
})

test('dossierDonnees : Windows sans LOCALAPPDATA → dossier Electron de l\'utilisateur', () => {
  const d = outils.dossierDonnees({
    plateforme: 'win32',
    env: { PROGRAMDATA: 'C:\\ProgramData' },
    dossierUtilisateur: 'C:\\Users\\marie\\AppData\\Roaming\\Olivia',
  })
  assert.equal(d, 'C:\\Users\\marie\\AppData\\Roaming\\Olivia')
})

test('ancienDossierCommun : ProgramData sous Windows seulement, pas si le dossier est imposé', () => {
  const env = { PROGRAMDATA: 'C:\\ProgramData' }
  assert.equal(outils.ancienDossierCommun({ plateforme: 'win32', env }), 'C:\\ProgramData\\Olivia')
  assert.equal(outils.ancienDossierCommun({ plateforme: 'darwin', env }), '')
  assert.equal(outils.ancienDossierCommun({ plateforme: 'win32', env: {} }), '')
  assert.equal(outils.ancienDossierCommun({
    plateforme: 'win32', env: { ...env, OLIVIA_DATA_DIR: 'D:\\donnees' },
  }), '')
})

test('dossierModelesCommun : partagé sous Windows s\'il est inscriptible, sinon vide', () => {
  const base = { plateforme: 'win32', env: { PROGRAMDATA: 'C:\\ProgramData' } }
  assert.equal(outils.dossierModelesCommun({ ...base, estInscriptible: () => true }),
    'C:\\ProgramData\\Olivia\\modeles-ia')
  assert.equal(outils.dossierModelesCommun({ ...base, estInscriptible: () => false }), '')
  assert.equal(outils.dossierModelesCommun({
    ...base, plateforme: 'darwin', estInscriptible: () => true,
  }), '')
  // Un choix explicite de l'exploitant n'est jamais remplacé.
  assert.equal(outils.dossierModelesCommun({
    plateforme: 'win32', env: { ...base.env, OLLAMA_MODELS: 'E:\\modeles' }, estInscriptible: () => true,
  }), '')
})

test('envDonnees : seules les variables utiles sont transmises au backend', () => {
  assert.deepEqual(outils.envDonnees({ dossier: '/d' }), { OLIVIA_DATA_DIR: '/d' })
  assert.deepEqual(outils.envDonnees({ dossier: 'C:\\d', reprise: 'C:\\ancien', modeles: 'C:\\m' }), {
    OLIVIA_DATA_DIR: 'C:\\d', OLIVIA_DATA_REPRISE: 'C:\\ancien', OLLAMA_MODELS: 'C:\\m',
  })
})

test('dossierDonnees : macOS → dossier de l\'utilisateur ; variable explicite prioritaire', () => {
  const base = {
    plateforme: 'darwin',
    dossierUtilisateur: '/Users/marie/Library/Application Support/Olivia',
  }
  assert.equal(outils.dossierDonnees({ ...base, env: {} }), base.dossierUtilisateur)
  assert.equal(outils.dossierDonnees({ ...base, env: { OLIVIA_DATA_DIR: '/srv/olivia' } }),
    '/srv/olivia')
})

test('commandeBackend : exécutable embarqué, arrêt lié à l\'entrée standard', () => {
  const mac = outils.commandeBackend({
    empaquete: true, plateforme: 'darwin', ressources: '/A/Olivia.app/Contents/Resources', port: 8001,
  })
  assert.equal(mac.commande, path.join('/A/Olivia.app/Contents/Resources', 'backend', 'ai-webapp'))
  assert.deepEqual(mac.args, ['--no-browser', '--port', '8001', '--parent-stdin', '--max-wait', '110'])
  const win = outils.commandeBackend({
    empaquete: true, plateforme: 'win32', ressources: 'R', port: 8000,
  })
  assert.ok(win.commande.endsWith('ai-webapp.exe'))
})

test('commandeBackend : développement → uvicorn depuis le dépôt', () => {
  const dev = outils.commandeBackend({
    empaquete: false, plateforme: 'linux', depot: '/depot', port: 8000, pythonDev: '/venv/python',
  })
  assert.equal(dev.commande, '/venv/python')
  assert.deepEqual(dev.args.slice(0, 3), ['-m', 'uvicorn', 'backend.main:app'])
  assert.equal(dev.cwd, '/depot')
})

test('estAdresseInterne : même origine seulement', () => {
  const base = 'http://127.0.0.1:8000'
  assert.ok(outils.estAdresseInterne('http://127.0.0.1:8000/ui/', base))
  assert.ok(!outils.estAdresseInterne('http://127.0.0.1:8001/ui/', base))
  assert.ok(!outils.estAdresseInterne('https://exemple.org/', base))
  assert.ok(!outils.estAdresseInterne('file:///etc/passwd', base))
  assert.ok(!outils.estAdresseInterne('pas une url', base))
})

test('estLienExterneAutorise : web uniquement', () => {
  assert.ok(outils.estLienExterneAutorise('https://education.gouv.fr/'))
  assert.ok(outils.estLienExterneAutorise('http://exemple.org'))
  for (const url of ['javascript:alert(1)', 'file:///C:/Windows', 'smb://serveur/partage',
    'ms-msdt:/id', 'mauvaise url']) {
    assert.ok(!outils.estLienExterneAutorise(url), url)
  }
})

test('pythonDeveloppement : OLIVIA_PYTHON, puis venv, puis système', () => {
  const base = { plateforme: 'linux', depot: '/depot' }
  assert.equal(outils.pythonDeveloppement({ ...base, existe: () => true, env: { OLIVIA_PYTHON: '/py' } }), '/py')
  assert.equal(outils.pythonDeveloppement({ ...base, existe: () => true }),
    path.join('/depot', 'backend', '.venv', 'bin', 'python'))
  assert.equal(outils.pythonDeveloppement({ ...base, existe: () => false }), 'python3')
})

test('commandeBackend : l\'application empaquetée transmet --max-wait, sous le délai d\'Electron', () => {
  const win = outils.commandeBackend({
    empaquete: true, plateforme: 'win32', ressources: 'R', port: 8000,
  })
  const i = win.args.indexOf('--max-wait')
  assert.ok(i >= 0, '--max-wait absent : launch.py abandonnerait au bout de 30 s')
  const secondes = Number(win.args[i + 1])
  assert.equal(secondes, outils.delaiLanceurSecondes())
  assert.ok(Number.isInteger(secondes))
  assert.ok(secondes * 1000 < outils.DELAI_DEMARRAGE_MS, 'le lanceur doit abandonner avant Electron')
  assert.ok(secondes > 30)
  assert.equal(secondes, 110)
})

test('commandeBackend : en développement (uvicorn), pas de --max-wait', () => {
  const dev = outils.commandeBackend({
    empaquete: false, plateforme: 'linux', depot: '/depot', port: 8000, pythonDev: '/venv/python',
  })
  assert.ok(!dev.args.includes('--max-wait'))
})

test('delaiLanceurSecondes : arrondi à la seconde, jamais inférieur à 1', () => {
  assert.equal(outils.delaiLanceurSecondes(120_000, 10_000), 110)
  assert.equal(outils.delaiLanceurSecondes(5_500, 1_000), 4)
  assert.equal(outils.delaiLanceurSecondes(1_000, 5_000), 1)
})

test('lirePreferences : par défaut, aucune mise à jour automatique', () => {
  assert.deepEqual(outils.lirePreferences(undefined), { majAuto: false })
  assert.deepEqual(outils.lirePreferences(''), { majAuto: false })
  assert.deepEqual(outils.lirePreferences('{"majAuto": tru'), { majAuto: false })
  assert.deepEqual(outils.lirePreferences('null'), { majAuto: false })
  assert.deepEqual(outils.lirePreferences('[1]'), { majAuto: false })
  assert.deepEqual(outils.lirePreferences('{}'), { majAuto: false })
  // Seul un vrai booléen active l'option (pas "true" ni 1).
  assert.deepEqual(outils.lirePreferences('{"majAuto": "true"}'), { majAuto: false })
  assert.deepEqual(outils.lirePreferences('{"majAuto": 1}'), { majAuto: false })
})

test('preferencesVersTexte : aller-retour, clés connues seulement', () => {
  assert.deepEqual(outils.lirePreferences(outils.preferencesVersTexte({ majAuto: true })), { majAuto: true })
  assert.deepEqual(outils.lirePreferences(outils.preferencesVersTexte({ majAuto: false })), { majAuto: false })
  assert.deepEqual(JSON.parse(outils.preferencesVersTexte({ majAuto: true, autre: 1 })), { majAuto: true })
  assert.deepEqual(JSON.parse(outils.preferencesVersTexte(undefined)), { majAuto: false })
})

test('copierSaufModeles : écarte models/ (sans tenir compte de la casse), garde le reste', () => {
  const racine = path.join('/depot', 'ollama')
  const copie = (...p) => outils.copierSaufModeles(racine, path.join(racine, ...p))
  assert.ok(copie())
  assert.ok(copie('ollama.exe'))
  assert.ok(copie('lib', 'ollama', 'runner.dll'))
  assert.ok(copie('models-liste.txt'))
  assert.ok(!copie('models'))
  assert.ok(!copie('Models'))
  assert.ok(!copie('MODELS', 'blobs', 'sha256-abc'))
  // Un sous-dossier « models » plus profond n'est pas celui d'Ollama.
  assert.ok(copie('lib', 'models'))
})
