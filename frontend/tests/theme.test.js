import { test } from 'node:test'
import assert from 'node:assert/strict'
import { THEMES, themeEffectif, appliquerTheme } from '../src/theme.js'

test('les trois thèmes proposés, « systeme » en premier', () => {
  assert.deepEqual(THEMES, ['systeme', 'sombre', 'clair'])
})

test('« sombre » et « clair » s\'imposent, quelle que soit la préférence de Windows', () => {
  assert.equal(themeEffectif('sombre', false), 'sombre')
  assert.equal(themeEffectif('sombre', true), 'sombre')
  assert.equal(themeEffectif('clair', true), 'clair')
  assert.equal(themeEffectif('clair', false), 'clair')
})

test('« systeme » suit la préférence de Windows', () => {
  assert.equal(themeEffectif('systeme', true), 'sombre')
  assert.equal(themeEffectif('systeme', false), 'clair')
})

test('valeur absente ou inconnue : comme « systeme »', () => {
  for (const reglage of [undefined, null, '', 'bleu', 'Sombre', 42, {}]) {
    assert.equal(themeEffectif(reglage, true), 'sombre')
    assert.equal(themeEffectif(reglage, false), 'clair')
  }
})

test('appliquerTheme pose data-theme sur la racine', () => {
  const racine = { dataset: {} }
  appliquerTheme(racine, 'clair')
  assert.equal(racine.dataset.theme, 'clair')
  appliquerTheme(racine, 'sombre')
  assert.equal(racine.dataset.theme, 'sombre')
})
