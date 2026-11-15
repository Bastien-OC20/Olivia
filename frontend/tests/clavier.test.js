import { test } from 'node:test'
import assert from 'node:assert/strict'
import { indexApresTouche } from '../src/clavier.js'

test('Haut et Bas passent au précédent et au suivant en bouclant', () => {
  assert.equal(indexApresTouche('ArrowDown', 0, 3), 1)
  assert.equal(indexApresTouche('ArrowDown', 2, 3), 0)
  assert.equal(indexApresTouche('ArrowUp', 1, 3), 0)
  assert.equal(indexApresTouche('ArrowUp', 0, 3), 2)
})

test('Début et Fin vont au premier et au dernier', () => {
  assert.equal(indexApresTouche('Home', 2, 3), 0)
  assert.equal(indexApresTouche('End', 0, 3), 2)
})

test('Gauche et Droite ne comptent que si la liste est aussi horizontale', () => {
  assert.equal(indexApresTouche('ArrowRight', 0, 3), null)
  assert.equal(indexApresTouche('ArrowLeft', 0, 3), null)
  assert.equal(indexApresTouche('ArrowRight', 2, 3, { horizontal: true }), 0)
  assert.equal(indexApresTouche('ArrowLeft', 0, 3, { horizontal: true }), 2)
})

test('sans élément ciblé, Bas mène au premier et Haut au dernier', () => {
  assert.equal(indexApresTouche('ArrowDown', -1, 4), 0)
  assert.equal(indexApresTouche('ArrowUp', -1, 4), 3)
})

test('autre touche ou liste vide : null', () => {
  assert.equal(indexApresTouche('Enter', 0, 3), null)
  assert.equal(indexApresTouche('a', 0, 3), null)
  assert.equal(indexApresTouche('ArrowDown', 0, 0), null)
  assert.equal(indexApresTouche('Home', -1, 0), null)
})
