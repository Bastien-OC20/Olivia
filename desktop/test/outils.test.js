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

test('dossierDonnees : Windows → ProgramData commun s\'il est inscriptible', () => {
  const d = outils.dossierDonnees({
    plateforme: 'win32',
    env: { PROGRAMDATA: 'C:\\ProgramData' },
    dossierUtilisateur: 'C:\\Users\\marie\\AppData\\Roaming\\Olivia',
    estInscriptible: () => true,
  })
  assert.equal(d, 'C:\\ProgramData\\Olivia')
})

test('dossierDonnees : Windows → repli utilisateur si ProgramData est verrouillé', () => {
  const d = outils.dossierDonnees({
    plateforme: 'win32',
    env: { PROGRAMDATA: 'C:\\ProgramData' },
    dossierUtilisateur: 'C:\\Users\\marie\\AppData\\Roaming\\Olivia',
    estInscriptible: () => false,
  })
  assert.equal(d, 'C:\\Users\\marie\\AppData\\Roaming\\Olivia')
})

test('dossierDonnees : macOS → dossier de l\'utilisateur ; variable explicite prioritaire', () => {
  const base = {
    plateforme: 'darwin',
    dossierUtilisateur: '/Users/marie/Library/Application Support/Olivia',
    estInscriptible: () => true,
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
  assert.deepEqual(mac.args, ['--no-browser', '--port', '8001', '--parent-stdin'])
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
