import { test } from 'node:test'
import assert from 'node:assert/strict'
import { salutation, nomAffiche, ACTIONS_ACCUEIL, recentes } from '../src/accueil.js'

// Dates locales fixes (le calcul se fait dans le fuseau du poste, le test aussi).
const a = (heure, minute = 0) => new Date(2026, 10, 15, heure, minute)

test('salutation : « Bonjour » de 5 h à 17 h 59, « Bonsoir » sinon', () => {
  assert.equal(salutation(a(4, 59)), 'Bonsoir')
  assert.equal(salutation(a(5, 0)), 'Bonjour')
  assert.equal(salutation(a(12, 0)), 'Bonjour')
  assert.equal(salutation(a(17, 59)), 'Bonjour')
  assert.equal(salutation(a(18, 0)), 'Bonsoir')
  assert.equal(salutation(a(0, 0)), 'Bonsoir')
  assert.equal(salutation(a(23, 59)), 'Bonsoir')
})

test('nomAffiche : première lettre en majuscule, accents compris', () => {
  assert.equal(nomAffiche('marie'), 'Marie')
  assert.equal(nomAffiche('élodie'), 'Élodie')
  assert.equal(nomAffiche('Anne'), 'Anne')
  assert.equal(nomAffiche('x'), 'X')
  // Caractère hors du plan de base : pas coupé en deux.
  assert.equal(nomAffiche('𝒶bc'), '𝒶bc')
})

test('nomAffiche : chaîne vide si l\'identifiant manque', () => {
  assert.equal(nomAffiche(undefined), '')
  assert.equal(nomAffiche(null), '')
  assert.equal(nomAffiche(''), '')
  assert.equal(nomAffiche('   '), '')
  assert.equal(nomAffiche(42), '')
})

test('ACTIONS_ACCUEIL : six actions complètes, identifiants uniques', () => {
  assert.equal(ACTIONS_ACCUEIL.length, 6)
  const ids = ACTIONS_ACCUEIL.map(x => x.id)
  assert.deepEqual(ids, ['courriel', 'ordre-du-jour', 'reformuler', 'compte-rendu', 'document', 'schema'])
  for (const action of ACTIONS_ACCUEIL) {
    assert.ok(['envoyer', 'preremplir', 'documents'].includes(action.type), action.id)
    for (const champ of ['icone', 'titre', 'description']) {
      assert.ok(typeof action[champ] === 'string' && action[champ].length > 0, `${action.id}.${champ}`)
    }
    assert.equal(typeof action.texte, 'string')
    // Une action qui envoie ou préremplit porte un texte ; l'action documents, non.
    if (action.type === 'documents') assert.equal(action.texte, '')
    else assert.ok(action.texte.length > 0, action.id)
  }
})

test('ACTIONS_ACCUEIL : textes repris des anciens exemples, schéma en /tableau', () => {
  const parId = Object.fromEntries(ACTIONS_ACCUEIL.map(x => [x.id, x]))
  assert.equal(parId.courriel.texte,
    'Rédige un courriel aux parents pour annoncer le prochain conseil de classe.')
  assert.equal(parId['ordre-du-jour'].texte,
    "Prépare un ordre du jour pour une réunion d'équipe pédagogique.")
  assert.equal(parId.reformuler.type, 'preremplir')
  assert.ok(parId.reformuler.texte.endsWith(':\n'))
  assert.equal(parId['compte-rendu'].type, 'preremplir')
  assert.equal(parId.schema.texte, '/tableau ')
  assert.equal(parId.document.type, 'documents')
})

test('recentes : tri décroissant, tronqué à 3 par défaut', () => {
  const liste = [
    { id: 'a', t: 10 }, { id: 'b', t: 40 }, { id: 'c', t: 30 }, { id: 'd', t: 20 },
  ]
  assert.deepEqual(recentes(liste, 't').map(x => x.id), ['b', 'c', 'd'])
  assert.deepEqual(recentes(liste, 't', 2).map(x => x.id), ['b', 'c'])
})

test('recentes : date absente ou invalide comptée comme 0, horodatage texte accepté', () => {
  const liste = [{ id: 'sans' }, { id: 'texte', t: '50' }, { id: 'bof', t: 'x' }, { id: 'n', t: 5 }]
  const ids = recentes(liste, 't', 4).map(x => x.id)
  assert.deepEqual(ids.slice(0, 2), ['texte', 'n'])
  assert.deepEqual([...ids.slice(2)].sort(), ['bof', 'sans'])
})

test('recentes : liste vide ou absente, n plus grand que la liste', () => {
  assert.deepEqual(recentes([], 't'), [])
  assert.deepEqual(recentes(undefined, 't'), [])
  assert.deepEqual(recentes(null, 't'), [])
  const liste = [{ id: 'a', t: 1 }, { id: 'b', t: 2 }]
  assert.deepEqual(recentes(liste, 't', 10).map(x => x.id), ['b', 'a'])
})

test('recentes : l\'entrée n\'est pas modifiée', () => {
  const liste = [{ id: 'a', t: 1 }, { id: 'b', t: 3 }, { id: 'c', t: 2 }]
  const copie = structuredClone(liste)
  const resultat = recentes(liste, 't')
  assert.deepEqual(liste, copie)
  assert.notEqual(resultat, liste)
  // Les éléments eux-mêmes sont ceux de la liste (pas de copie profonde).
  assert.equal(resultat[0], liste[1])
})
