import { test } from 'node:test'
import assert from 'node:assert/strict'
import { nomIconeFichier, cheminLisible } from '../src/typesFichier.js'
import { ICONES } from '../src/icones.js'

test('un dossier a l\'icône dossier, quelle que soit l\'extension', () => {
  assert.equal(nomIconeFichier('', true), 'dossier')
  assert.equal(nomIconeFichier('.pdf', true), 'dossier')
})

test('les images, les tableurs et les autres fichiers', () => {
  assert.equal(nomIconeFichier('.png'), 'image')
  assert.equal(nomIconeFichier('.JPG'), 'image')
  assert.equal(nomIconeFichier('.xlsx'), 'grille')
  assert.equal(nomIconeFichier('.csv'), 'grille')
  assert.equal(nomIconeFichier('.pdf'), 'document')
  assert.equal(nomIconeFichier('.docx'), 'document')
  assert.equal(nomIconeFichier(''), 'document')
  assert.equal(nomIconeFichier(undefined), 'document')
})

test('chaque nom renvoyé existe dans les icônes', () => {
  for (const ext of ['.png', '.xlsx', '.pdf', '']) {
    assert.ok(Object.hasOwn(ICONES, nomIconeFichier(ext)))
  }
  assert.ok(Object.hasOwn(ICONES, nomIconeFichier('', true)))
})

test('le chemin affiché ne montre pas l\'identifiant interne de la racine', () => {
  assert.equal(cheminLisible('r0/Conseils de classe/calendrier.txt'), 'Conseils de classe/calendrier.txt')
  assert.equal(cheminLisible('r12/note.txt'), 'note.txt')
  assert.equal(cheminLisible('r0'), '')
  assert.equal(cheminLisible('rapports/r0/note.txt'), 'rapports/r0/note.txt')
  assert.equal(cheminLisible(undefined), '')
})
