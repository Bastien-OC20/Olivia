import { test } from 'node:test'
import assert from 'node:assert/strict'
import { ICONES, NOMS_ICONES } from '../src/icones.js'

const REQUISES = [
  'maison', 'bulle', 'dossier', 'document', 'tableau', 'engrenage', 'utilisateur',
  'utilisateurs', 'sortie', 'plus', 'envoyer', 'stop', 'globe', 'trombone', 'crayon',
  'corbeille', 'telecharger', 'oeil', 'fermer', 'loupe', 'eclair', 'puce', 'plume', 'cloche',
  'mail', 'calendrier', 'cadenas', 'alerte', 'coche', 'chevron-bas', 'chevron-droite',
  'chevron-gauche', 'menu', 'points', 'soleil', 'lune', 'ecran', 'etincelles', 'panneau',
  'actualiser', 'copier', 'livre', 'image',
]

// Seuls les caractères des commandes de chemin SVG : pas de balise, pas d'attribut glissé.
const CHEMIN_SVG = /^[MmLlHhVvCcSsQqTtAaZz0-9.,\s-]+$/

test('chaque icône requise existe', () => {
  for (const nom of REQUISES) {
    assert.ok(Object.hasOwn(ICONES, nom), `icône manquante : ${nom}`)
  }
})

test('NOMS_ICONES liste exactement les clés de ICONES', () => {
  assert.deepEqual(NOMS_ICONES, Object.keys(ICONES))
})

test('chaque icône est une liste non vide de chemins SVG valides', () => {
  for (const [nom, chemins] of Object.entries(ICONES)) {
    assert.ok(Array.isArray(chemins) && chemins.length > 0, `${nom} : liste vide`)
    for (const d of chemins) {
      assert.equal(typeof d, 'string', `${nom} : chemin qui n'est pas du texte`)
      assert.ok(d.trim().length > 0, `${nom} : chemin vide`)
      assert.match(d, CHEMIN_SVG, `${nom} : caractère interdit dans « ${d} »`)
      assert.match(d, /^\s*[Mm]/, `${nom} : un chemin commence par M`)
    }
  }
})
