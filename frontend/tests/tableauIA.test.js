// Tests des fonctions pures de la commande /tableau : `npm test` (node --test).
import test from 'node:test'
import assert from 'node:assert/strict'
import {
  analyserSchema, versMermaid, schemaExploitable, titreTableau, sujetCommandeTableau,
  messagesTableau,
  MAX_NOEUDS, MAX_ARETES, LIBELLE_MAX,
} from '../src/tableauIA.js'

const libelles = (s) => s.noeuds.map((n) => n.libelle)
// Arêtes lisibles : « A > B [étiquette] ».
const fleches = (s) => s.aretes.map((a) => {
  const nom = (id) => s.noeuds.find((n) => n.id === id).libelle
  return `${nom(a.de)} > ${nom(a.vers)}${a.etiquette ? ` [${a.etiquette}]` : ''}`
})

test('format de référence : titre, flèches et étiquettes', () => {
  const s = analyserSchema([
    "TITRE: Inscription d'un élève",
    'Demande des parents -> Dossier complet ?',
    'Dossier complet ? -> Validation [oui]',
    'Dossier complet ? -> Relance des parents [non]',
  ].join('\n'))
  assert.equal(s.titre, "Inscription d'un élève")
  assert.deepEqual(libelles(s),
    ['Demande des parents', 'Dossier complet ?', 'Validation', 'Relance des parents'])
  assert.deepEqual(fleches(s), [
    'Demande des parents > Dossier complet ?',
    'Dossier complet ? > Validation [oui]',
    'Dossier complet ? > Relance des parents [non]',
  ])
  assert.deepEqual(s.noeuds.map((n) => n.id), ['n0', 'n1', 'n2', 'n3'])
  assert.ok(schemaExploitable(s))
})

test("une chaîne A -> B -> C donne deux flèches ; l'étiquette va à la dernière", () => {
  const s = analyserSchema('Accueil -> Dossier -> Décision [signée]')
  assert.deepEqual(fleches(s), ['Accueil > Dossier', 'Dossier > Décision [signée]'])
})

test('flèches alternatives : -->, =>, →, ==>', () => {
  const s = analyserSchema('A --> B\nB => C\nC → D\nD ==> E')
  assert.deepEqual(fleches(s), ['A > B', 'B > C', 'C > D', 'D > E'])
})

test("un trait d'union dans un libellé n'est pas une flèche", () => {
  const s = analyserSchema('Pré-inscription -> Rendez-vous')
  assert.deepEqual(fleches(s), ['Pré-inscription > Rendez-vous'])
})

test('titre : insensible à la casse, espace avant les deux-points, absent toléré', () => {
  assert.equal(analyserSchema('Titre : Rentrée\nA -> B').titre, 'Rentrée')
  assert.equal(analyserSchema('titre:   Rentrée   scolaire \nA -> B').titre, 'Rentrée scolaire')
  assert.equal(analyserSchema('**TITRE:** Gras\nA -> B').titre, 'Gras')
  assert.equal(analyserSchema('A -> B').titre, '')
  // Un seul titre : le premier l'emporte.
  assert.equal(analyserSchema('TITRE: Un\nTITRE: Deux\nA -> B').titre, 'Un')
})

test('le bavardage du modèle (lignes sans flèche) est ignoré', () => {
  const s = analyserSchema([
    'Bien sûr ! Voici le schéma demandé :',
    '',
    'A -> B',
    "J'espère que cela vous aidera.",
  ].join('\n'))
  assert.deepEqual(fleches(s), ['A > B'])
})

test('réflexion <think>, clôtures ``` et puces sont retirées', () => {
  const s = analyserSchema([
    '<think>Je dois faire A -> Z puis réfléchir.</think>',
    '```mermaid',
    '- Demande -> Dossier',
    '* Dossier -> Décision',
    '• Décision -> Courrier',
    '1. Courrier -> Archivage',
    '2) Archivage -> Fin',
    '```',
  ].join('\n'))
  assert.deepEqual(fleches(s), [
    'Demande > Dossier', 'Dossier > Décision', 'Décision > Courrier',
    'Courrier > Archivage', 'Archivage > Fin',
  ])
  assert.ok(!libelles(s).includes('Z'))
})

test('une réflexion jamais refermée est entièrement ignorée', () => {
  const s = analyserSchema('<think>A -> B\nB -> C')
  assert.equal(s.noeuds.length, 0)
  assert.ok(!schemaExploitable(s))
})

test('le gras Markdown est retiré des libellés', () => {
  const s = analyserSchema('**Demande** -> **Dossier** [**oui**]')
  assert.deepEqual(fleches(s), ['Demande > Dossier [oui]'])
})

test('même élément : espaces compactés, casse ignorée, première graphie conservée', () => {
  const s = analyserSchema('Dossier  complet -> Validation\ndossier COMPLET -> Archivage')
  assert.deepEqual(libelles(s), ['Dossier complet', 'Validation', 'Archivage'])
  assert.equal(s.aretes[1].de, s.aretes[0].de)
})

test('flèches dédoublonnées ; une étiquette tardive complète la flèche', () => {
  const s = analyserSchema('A -> B\nA -> B\na -> b [oui]\nA -> B [non]')
  assert.equal(s.aretes.length, 1)
  assert.equal(s.aretes[0].etiquette, 'oui')
})

test('boucle sur soi-même et libellés vides ignorés', () => {
  // (« -> B » seul en début de ligne est une suite de liste : voir plus bas.)
  const s = analyserSchema('A -> A\nA -> \nA ->  -> B\nC -> D')
  assert.deepEqual(fleches(s), ['C > D'])
  assert.deepEqual(libelles(s), ['C', 'D'])
})

test('guillemets et point final autour des libellés retirés', () => {
  const s = analyserSchema('"Demande" -> « Dossier ».')
  assert.deepEqual(fleches(s), ['Demande > Dossier'])
})

test('plafond de nœuds : les flèches qui en créeraient trop sont ignorées', () => {
  const lignes = []
  for (let i = 0; i < 100; i++) lignes.push(`Étape ${i} -> Étape ${i + 1}`)
  const s = analyserSchema(lignes.join('\n'))
  assert.equal(s.noeuds.length, MAX_NOEUDS)
  assert.equal(s.aretes.length, MAX_NOEUDS - 1)
  // Les flèches entre nœuds déjà connus restent acceptées.
  const t = analyserSchema(`${lignes.join('\n')}\nÉtape 3 -> Étape 0`)
  assert.equal(t.aretes.length, MAX_NOEUDS)
})

test("plafond d'arêtes", () => {
  const lignes = []
  for (let i = 0; i < 20; i++) {
    for (let j = 0; j < 20; j++) if (i !== j) lignes.push(`N${i} -> N${j}`)
  }
  const s = analyserSchema(lignes.join('\n'))
  assert.equal(s.aretes.length, MAX_ARETES)
  assert.ok(s.noeuds.length <= MAX_NOEUDS)
})

test('libellé trop long tronqué', () => {
  const s = analyserSchema(`${'x'.repeat(200)} -> B`)
  assert.equal(s.noeuds[0].libelle.length, LIBELLE_MAX)
  assert.ok(s.noeuds[0].libelle.endsWith('…'))
})

test("entrée vide ou absurde : schéma vide, jamais d'erreur", () => {
  for (const x of ['', null, undefined, 42, 'Je ne sais pas.', '->', '[oui]']) {
    const s = analyserSchema(x)
    assert.equal(s.noeuds.length, 0)
    assert.ok(!schemaExploitable(s))
  }
})

test('titreTableau : titre du modèle, sinon sujet avec majuscule, borné à 80', () => {
  assert.equal(titreTableau({ titre: 'Rentrée' }, 'sujet'), 'Rentrée')
  assert.equal(titreTableau({ titre: '' }, 'étapes de la rentrée'), 'Étapes de la rentrée')
  assert.equal(titreTableau({ titre: '' }, 'a'.repeat(200)).length, 80)
})

test('versMermaid : identifiants générés, libellés toujours entre guillemets', () => {
  const m = versMermaid(analyserSchema([
    'Demande -> Dossier complet ?',
    'Dossier complet ? -> Validation [oui]',
  ].join('\n')))
  assert.equal(m, [
    'flowchart TD',
    '  n0["Demande"]',
    '  n1["Dossier complet ?"]',
    '  n2["Validation"]',
    '  n0 --> n1',
    '  n1 -->|"oui"| n2',
  ].join('\n'))
})

test('versMermaid : guillemets échappés en #quot; et caractères spéciaux neutralisés', () => {
  const m = versMermaid(analyserSchema('Le "grand" oral -> Salle #3 <B> `x` fin [dit "non" net]'))
  assert.match(m, /n0\["Le #quot;grand#quot; oral"\]/)
  assert.match(m, /n1\["Salle #35;3 #lt;B#gt; 'x' fin"\]/)
  assert.match(m, /n0 -->\|"dit #quot;non#quot; net"\| n1/)
  // Aucun guillemet « nu » à l'intérieur d'un libellé : 2 par libellé exactement.
  for (const ligne of m.split('\n').filter((l) => l.includes('["'))) {
    assert.equal(ligne.split('"').length - 1, 2)
  }
})

test('sujetCommandeTableau : commande reconnue, sujet extrait', () => {
  assert.equal(sujetCommandeTableau("/tableau étapes de l'inscription"), "étapes de l'inscription")
  assert.equal(sujetCommandeTableau('  /TABLEAU   Rentrée   2026 '), 'Rentrée 2026')
  assert.equal(sujetCommandeTableau('/Tableau\nsur deux lignes'), 'sur deux lignes')
  assert.equal(sujetCommandeTableau('/tableau'), '')
  assert.equal(sujetCommandeTableau('/tableau   '), '')
})

test("sujetCommandeTableau : le reste n'est pas la commande", () => {
  for (const x of ['/tableaux', '/tableauX rentrée', 'fais un /tableau', 'tableau', '', null]) {
    assert.equal(sujetCommandeTableau(x), null)
  }
})

test('messagesTableau : exemple en échange précédent, sujet en dernier', () => {
  for (const strict of [false, true]) {
    const msgs = messagesTableau('la rentrée', strict)
    assert.deepEqual(msgs.map((m) => m.role), ['user', 'assistant', 'user'])
    assert.ok(msgs[0].content.includes('TITRE:'))
    assert.ok(schemaExploitable(analyserSchema(msgs[1].content)), "l'exemple respecte le format")
    assert.ok(msgs[2].content.trimEnd().endsWith('Sujet : la rentrée'))
    assert.equal(msgs[2].content.includes('ATTENTION'), strict)
  }
})

test('gabarit recopié (« Élément A -> Élément B ») : schéma inexploitable', () => {
  const recopie = analyserSchema('TITRE: X\nÉlément A -> Élément B\nÉlément B -> Élément C')
  assert.ok(!schemaExploitable(recopie))
  assert.ok(!schemaExploitable(analyserSchema('A -> B\nB -> C\nEtape 1 -> Etape 2')))
  // Un libellé court isolé, au milieu de vrais éléments, ne disqualifie pas le schéma.
  assert.ok(schemaExploitable(analyserSchema('Conseil de classe -> CA\nCA -> Vote du budget')))
})

test("la consigne ne montre aucun libellé générique à recopier", () => {
  const tout = messagesTableau('la rentrée').map((m) => m.content).join('\n')
  assert.ok(!/Élément A|Élément B/.test(tout))
})

test('liste « -> Étape » sans élément à gauche : suite partant du titre', () => {
  const s = analyserSchema('TITRE: Sortie scolaire\n-> Définir les objectifs\n-> Choisir le lieu\n\n-> Réserver le car')
  assert.deepEqual(s.noeuds.map((n) => n.libelle),
    ['Sortie scolaire', 'Définir les objectifs', 'Choisir le lieu', 'Réserver le car'])
  assert.deepEqual(s.aretes.map((a) => `${a.de}>${a.vers}`), ['n0>n1', 'n1>n2', 'n2>n3'])
  assert.ok(schemaExploitable(s))
  // Sans titre ni ligne précédente, la première flèche orpheline est ignorée.
  assert.equal(analyserSchema('-> Seul').aretes.length, 0)
})

test('étiquette collée à un élément (« A [oui] -> B ») : sortie du libellé', () => {
  const s = analyserSchema('Absence signalée ? [oui] -> Appeler les parents\nB -> C [non] -> D')
  assert.deepEqual(s.noeuds.map((n) => n.libelle),
    ['Absence signalée ?', 'Appeler les parents', 'B', 'C', 'D'])
  assert.deepEqual(s.aretes.map((a) => a.etiquette), ['oui', 'non', ''])
})

test("crochet d'étiquette jamais refermé retiré du libellé", () => {
  const s = analyserSchema('Choisir le lieu -> Préparer les activités [ou')
  assert.deepEqual(s.noeuds.map((n) => n.libelle), ['Choisir le lieu', 'Préparer les activités'])
})
