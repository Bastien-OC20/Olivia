import { test } from 'node:test'
import assert from 'node:assert/strict'
import {
  estResponsable, onglets, ongletDisponible, reglagesAEnvoyer, texteExport, libelleRole,
} from '../src/roles.js'

const ids = (role, simple) => onglets(role, simple).map(t => t.id)

test('seul « responsable » est responsable ; rôle absent ou inconnu = membre', () => {
  assert.equal(estResponsable('responsable'), true)
  assert.equal(estResponsable('membre'), false)
  assert.equal(estResponsable(null), false)
  assert.equal(estResponsable(undefined), false)
  assert.equal(estResponsable('admin'), false)
  assert.equal(libelleRole('membre'), 'Membre')
})

test('un membre ne voit ni formules, ni recherche web, ni connexions, ni comptes', () => {
  assert.deepEqual(ids('membre', true), ['reasoning', 'documents', 'privacy', 'compte'])
  assert.deepEqual(ids('membre', false), ['reasoning', 'documents', 'privacy', 'compte'])
  assert.deepEqual(ids(null, false), ['reasoning', 'documents', 'privacy', 'compte'])
})

test('un responsable voit tout, les onglets avancés seulement en mode avancé', () => {
  assert.deepEqual(ids('responsable', true),
    ['reasoning', 'documents', 'formules', 'privacy', 'compte', 'comptes'])
  assert.deepEqual(ids('responsable', false), [
    'reasoning', 'documents', 'formules', 'search', 'connectors', 'privacy', 'compte', 'comptes',
  ])
})

test('ongletDisponible sert à retomber sur un onglet permis', () => {
  assert.equal(ongletDisponible('connectors', 'membre', false), false)
  assert.equal(ongletDisponible('connectors', 'responsable', true), false)
  assert.equal(ongletDisponible('connectors', 'responsable', false), true)
  assert.equal(ongletDisponible('compte', 'membre', true), true)
})

test('un membre n\'envoie que ses réglages de confort', () => {
  const data = {
    tone: 'formal', temperature: 0.5, fs_roots: [{ path: 'C:\\x' }], system_prompt: 'p',
    connectors: { imap: {} }, search_brave_api_key: '••••••••', simple_mode: false,
    etat_secrets: { chiffres: true },
  }
  assert.deepEqual(reglagesAEnvoyer(data, 'membre'),
    { tone: 'formal', temperature: 0.5, simple_mode: false })
})

test('un responsable envoie tout sauf l\'état des secrets, sans toucher à l\'original', () => {
  const data = { tone: 'formal', fs_roots: [], etat_secrets: { chiffres: false } }
  const out = reglagesAEnvoyer(data, 'responsable')
  assert.deepEqual(out, { tone: 'formal', fs_roots: [] })
  assert.ok('etat_secrets' in data)
})

test('un membre peut enregistrer son thème, pas les dossiers de l\'organisation', () => {
  const out = reglagesAEnvoyer({ theme: 'clair', fs_roots: [] }, 'membre')
  assert.equal(out.theme, 'clair')
  assert.ok(!('fs_roots' in out))
})

test('le texte d\'export dit ce qui est exporté selon le rôle', () => {
  assert.match(texteExport('responsable'), /toute votre organisation/)
  assert.match(texteExport('membre'), /vos conversations et vos tableaux/)
  assert.doesNotMatch(texteExport('membre'), /de tous les comptes/)
})
