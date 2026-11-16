import { test } from 'node:test'
import assert from 'node:assert/strict'
import { analyserLigne, appliquerEvenement, champsOutils } from '../src/fluxChat.js'
import { CLES_MEMBRE, reglagesAEnvoyer } from '../src/roles.js'

const neuf = () => ({ role: 'assistant', content: '', erreur: '', etapes: [], proposition: null })
const ligne = (o) => `data: ${JSON.stringify(o)}`

test('analyserLigne ignore les lignes étrangères, vides ou cassées', () => {
  assert.equal(analyserLigne(''), null)
  assert.equal(analyserLigne(': ping'), null)
  assert.equal(analyserLigne('data: {"message":'), null)
  assert.equal(analyserLigne('data: 42'), null)
  assert.deepEqual(analyserLigne('data: {"done": true}'), { done: true })
})

test('le texte reçu s\'ajoute au contenu', () => {
  const m = neuf()
  assert.equal(appliquerEvenement(m, analyserLigne(ligne({ message: { content: 'Bon' } }))), false)
  appliquerEvenement(m, { message: { content: 'jour' } })
  assert.equal(m.content, 'Bonjour')
})

test('une erreur du moteur termine le flux et s\'affiche', () => {
  const m = neuf()
  assert.equal(appliquerEvenement(m, { error: 'Ollama éteint' }), true)
  assert.equal(m.erreur, 'Ollama éteint')
})

test('done termine le flux ; done_reason length signale une réponse coupée', () => {
  const m = neuf()
  assert.equal(appliquerEvenement(m, { done: true, done_reason: 'stop' }), true)
  assert.equal(m.erreur, '')
  assert.equal(appliquerEvenement(m, { done: true, done_reason: 'length' }), true)
  assert.match(m.erreur, /Réponse coupée/)
})

test('le texte du dernier évènement done est conservé', () => {
  const m = neuf()
  appliquerEvenement(m, { message: { content: 'fin' }, done: true })
  assert.equal(m.content, 'fin')
})

test('une étape en_cours puis fini est fusionnée sous le même id', () => {
  const m = neuf()
  appliquerEvenement(m, { etape: { id: 1, outil: 'chercher_documents', etat: 'en_cours', libelle: 'Recherche' } })
  assert.equal(m.etapes.length, 1)
  appliquerEvenement(m, {
    etape: { id: 1, etat: 'fini', resume: '3 documents trouvés', documents: [{ path: 'r0/a', name: 'a' }] },
  })
  assert.equal(m.etapes.length, 1)
  assert.deepEqual(m.etapes[0], {
    id: 1, outil: 'chercher_documents', etat: 'fini', libelle: 'Recherche',
    resume: '3 documents trouvés', documents: [{ path: 'r0/a', name: 'a' }],
  })
})

test('une étape terminée sans en_cours préalable est créée quand même', () => {
  const m = neuf()
  appliquerEvenement(m, { etape: { id: 2, etat: 'echec', resume: 'agenda illisible' } })
  assert.equal(m.etapes.length, 1)
  assert.equal(m.etapes[0].etat, 'echec')
})

test('une étape sans identifiant est ignorée', () => {
  const m = neuf()
  appliquerEvenement(m, { etape: { etat: 'fini' } })
  assert.equal(m.etapes.length, 0)
})

test('une proposition est enregistrée, et la dernière reçue l\'emporte', () => {
  const m = neuf()
  appliquerEvenement(m, { proposition: { type: 'document_word', type_document: 'convocation', titre: 'A', texte: 'x' } })
  assert.equal(m.proposition.titre, 'A')
  assert.equal(m.proposition.objet, '')
  appliquerEvenement(m, { proposition: { type: 'document_word', type_document: 'courrier', titre: 'B', texte: 'y' } })
  assert.equal(m.proposition.titre, 'B')
  assert.equal(m.proposition.type_document, 'courrier')
})

test('une proposition d\'un autre type est ignorée', () => {
  const m = neuf()
  appliquerEvenement(m, { proposition: { type: 'autre' } })
  assert.equal(m.proposition, null)
})

test('champsOutils garde les étapes non vides et la proposition, rien sinon', () => {
  assert.deepEqual(champsOutils({ etapes: [], proposition: null }), {})
  assert.deepEqual(champsOutils({}), {})
  const etapes = [{ id: 1 }]
  const proposition = { type: 'document_word' }
  assert.deepEqual(champsOutils({ etapes, proposition }), { etapes, proposition })
})

test('outils_actifs est un réglage du responsable, pas du membre', () => {
  assert.ok(!CLES_MEMBRE.includes('outils_actifs'))
  assert.deepEqual(Object.keys(reglagesAEnvoyer({ outils_actifs: false, theme: 'clair' }, 'membre')), ['theme'])
  assert.ok('outils_actifs' in reglagesAEnvoyer({ outils_actifs: false }, 'responsable'))
})
