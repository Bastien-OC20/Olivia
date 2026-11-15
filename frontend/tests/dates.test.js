import { test } from 'node:test'
import assert from 'node:assert/strict'
import { dateRelative, grouperParDate } from '../src/dates.js'

// Dimanche 15 novembre 2026, 10 h, heure locale : le calcul des jours se fait
// dans le fuseau du poste, le test aussi.
const MAINTENANT = new Date(2026, 10, 15, 10, 0, 0).getTime()
/** Horodatage en SECONDES (format du backend) d'une date locale de novembre 2026. */
const s = (jour, heure = 12, minute = 0) => new Date(2026, 10, jour, heure, minute).getTime() / 1000

test('dateRelative : vide sans date, « à l\'instant » sous la minute', () => {
  assert.equal(dateRelative(null, MAINTENANT), '')
  assert.equal(dateRelative(0, MAINTENANT), '')
  assert.equal(dateRelative('pas une date', MAINTENANT), '')
  assert.equal(dateRelative(MAINTENANT / 1000 - 20, MAINTENANT), "à l'instant")
})

test('dateRelative : minutes, heures et jours en français', () => {
  assert.match(dateRelative(MAINTENANT / 1000 - 5 * 60, MAINTENANT), /il y a 5\sminutes/)
  assert.match(dateRelative(MAINTENANT / 1000 - 3 * 3600, MAINTENANT), /il y a 3\sheures/)
  assert.equal(dateRelative(MAINTENANT / 1000 - 86400, MAINTENANT), 'hier')
  // Horodatage passé en texte (JSON) : accepté.
  assert.equal(dateRelative(String(MAINTENANT / 1000 - 86400), MAINTENANT), 'hier')
})

test('grouperParDate : groupes dans l\'ordre, vides omis, ordre des éléments conservé', () => {
  const elements = [
    { id: 'a', t: s(15, 9) },
    { id: 'b', t: s(15, 0, 5) },
    { id: 'c', t: s(14, 23, 59) },
    { id: 'd', t: s(13) },
    { id: 'e', t: s(8, 0, 1) },
    { id: 'f', t: s(7, 23) },
    { id: 'g', t: s(1) },
  ]
  const groupes = grouperParDate(elements, 't', MAINTENANT)
  assert.deepEqual(groupes.map(g => g.id), ['aujourdhui', 'hier', 'semaine', 'ancien'])
  assert.deepEqual(groupes.map(g => g.libelle),
    ["Aujourd'hui", 'Hier', '7 derniers jours', 'Plus ancien'])
  assert.deepEqual(groupes.map(g => g.elements.map(e => e.id)),
    [['a', 'b'], ['c'], ['d', 'e'], ['f', 'g']])
})

test('grouperParDate : jours calendaires, pas des tranches de 24 h', () => {
  // Hier à 23 h 59 n'a que 10 h d'écart, mais c'est hier ; aujourd'hui à 0 h 01, aujourd'hui.
  const groupes = grouperParDate(
    [{ id: 'x', t: s(14, 23, 59) }, { id: 'y', t: s(15, 0, 1) }], 't', MAINTENANT)
  assert.deepEqual(groupes.map(g => [g.id, g.elements.map(e => e.id)]),
    [['aujourdhui', ['y']], ['hier', ['x']]])
})

test('grouperParDate : sans date → « Plus ancien », date future → « Aujourd\'hui »', () => {
  const groupes = grouperParDate([
    { id: 'sans' },
    { id: 'nul', t: null },
    { id: 'texte', t: 'abc' },
    { id: 'futur', t: s(20) },
  ], 't', MAINTENANT)
  assert.deepEqual(groupes.map(g => [g.id, g.elements.map(e => e.id)]),
    [['aujourdhui', ['futur']], ['ancien', ['sans', 'nul', 'texte']]])
})

test('grouperParDate : liste vide ou absente → aucun groupe', () => {
  assert.deepEqual(grouperParDate([], 't', MAINTENANT), [])
  assert.deepEqual(grouperParDate(undefined, 't', MAINTENANT), [])
})

test('grouperParDate : horodatage en texte accepté, éléments non recopiés', () => {
  const el = { id: 'z', t: String(s(15, 8)) }
  const [groupe] = grouperParDate([el], 't', MAINTENANT)
  assert.equal(groupe.id, 'aujourdhui')
  assert.equal(groupe.elements[0], el)
})
