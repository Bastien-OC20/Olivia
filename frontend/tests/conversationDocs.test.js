// Tests des fonctions pures des conversations et des réglages : `npm test` (node --test).
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  DOC_MAX, reponseApplicable, idAAppliquerApresEnregistrement, normaliserDocuments,
  documentsPourEnvoi, documentDepuisTexte, avisDocumentsIndisponibles, fusionnerDocuments,
} from '../src/conversationDocs.js'
import { copier, fusionner, restaurer } from '../src/reglages.js'

test('une réponse tardive de A ne s\'applique pas quand B est à l\'écran', () => {
  const a = { id: 'A' }
  const b = { id: 'B' }
  assert.equal(reponseApplicable(a, b), false)
  assert.equal(reponseApplicable(a, a), true)
  assert.equal(reponseApplicable(null, null), false)
})

test('l\'identifiant d\'un POST tardif ne détourne pas la conversation affichée', () => {
  const nouvelleA = { id: null }
  const b = { id: 'B' }
  assert.equal(idAAppliquerApresEnregistrement(nouvelleA, b, 'conv-A'), null)
  assert.equal(idAAppliquerApresEnregistrement(nouvelleA, nouvelleA, 'conv-A'), 'conv-A')
  assert.equal(idAAppliquerApresEnregistrement(nouvelleA, nouvelleA, undefined), null)
})

test('deux clics rapides : seule la dernière ouverture est applicable', () => {
  const clicA = {}
  const clicB = {}
  const derniere = clicB       // le second clic remplace le jeton du premier
  assert.equal(reponseApplicable(clicA, derniere), false)
  assert.equal(reponseApplicable(clicB, derniere), true)
})

test('normaliserDocuments : champ absent, doublons, entrées invalides, limite', () => {
  assert.deepEqual(normaliserDocuments(undefined), [])
  assert.deepEqual(normaliserDocuments(null), [])
  assert.deepEqual(normaliserDocuments('x'), [])
  assert.deepEqual(
    normaliserDocuments([
      { path: 'r0/a.docx', name: 'a.docx' },
      { path: 'r0/a.docx', name: 'doublon' },
      { path: '', name: 'vide' },
      { name: 'sans chemin' },
      null,
      { path: 'r0/b.pdf' },
    ]),
    [{ path: 'r0/a.docx', name: 'a.docx' }, { path: 'r0/b.pdf', name: 'r0/b.pdf' }],
  )
  const beaucoup = Array.from({ length: 15 }, (_, i) => ({ path: `r0/${i}.txt`, name: `${i}` }))
  assert.equal(normaliserDocuments(beaucoup).length, DOC_MAX)
})

test('documentsPourEnvoi n\'envoie jamais le contenu', () => {
  const envoi = documentsPourEnvoi([
    { path: 'r0/a.docx', name: 'a.docx', content: 'secret', sourceTruncated: true },
  ])
  assert.deepEqual(envoi, [{ path: 'r0/a.docx', name: 'a.docx' }])
})

test('documentDepuisTexte produit le même objet que FileExplorer', () => {
  assert.deepEqual(
    documentDepuisTexte('r0/a.docx', 'a.docx', { name: 'A.docx', content: 'texte', truncated: true }),
    { path: 'r0/a.docx', name: 'A.docx', content: 'texte', sourceTruncated: true },
  )
  assert.deepEqual(
    documentDepuisTexte('r0/a.docx', 'a.docx', { content: 'x' }),
    { path: 'r0/a.docx', name: 'a.docx', content: 'x', sourceTruncated: false },
  )
  assert.throws(() => documentDepuisTexte('r0/a', 'a', { empty: true }), /aucun texte lisible/)
  assert.throws(() => documentDepuisTexte('r0/a', 'a', null))
})

test('avis des documents devenus indisponibles', () => {
  assert.equal(avisDocumentsIndisponibles([]), '')
  assert.match(avisDocumentsIndisponibles(['a.docx']), /^1 document joint n'est plus disponible : a\.docx/)
  assert.match(avisDocumentsIndisponibles(['a', 'b']),
    /^2 documents joints ne sont plus disponibles : a, b/)
})

test('fusionnerDocuments : sans doublon, dans la limite', () => {
  const actuels = [{ path: 'p1', name: '1' }]
  const out = fusionnerDocuments(actuels, [{ path: 'p1', name: '1' }, { path: 'p2', name: '2' }])
  assert.deepEqual(out.map((d) => d.path), ['p1', 'p2'])
  assert.equal(actuels.length, 1, 'l\'entrée n\'est pas modifiée')
  const pleins = Array.from({ length: DOC_MAX }, (_, i) => ({ path: `d${i}`, name: `${i}` }))
  assert.equal(fusionnerDocuments(pleins, [{ path: 'extra', name: 'x' }]).length, DOC_MAX)
})

test('restaurer rétablit les réglages enregistrés sans les lier à l\'écran', () => {
  const defauts = { tone: 'neutral', connectors: { imap: { host: '' } } }
  const enregistre = fusionner(defauts, { tone: 'formal', connectors: { imap: { host: 'h' } } })
  const ecran = copier(enregistre)
  ecran.tone = 'friendly'
  ecran.connectors.imap.host = 'modifie'
  const apresAnnulation = restaurer(enregistre)
  assert.equal(apresAnnulation.tone, 'formal')
  assert.equal(apresAnnulation.connectors.imap.host, 'h')
  apresAnnulation.tone = 'autre'
  assert.equal(enregistre.tone, 'formal', 'la copie restaurée est indépendante')
})

test('fusionner : valeurs par défaut conservées pour les champs absents', () => {
  const defauts = { a: 1, connectors: { imap: { host: '', folder: 'INBOX' } } }
  const out = fusionner(defauts, { connectors: { imap: { host: 'x' } } })
  assert.deepEqual(out.connectors.imap, { host: 'x', folder: 'INBOX' })
  assert.equal(out.a, 1)
})
