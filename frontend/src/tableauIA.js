// Commande /tableau : Oliv'IA dessine un schéma dans un tableau blanc Excalidraw.
//
// Les petits modèles locaux (2 milliards de paramètres) ne savent pas produire
// du JSON Excalidraw, ni même du Mermaid fiable. On leur demande donc le format
// le plus simple possible (une flèche par ligne, « A -> B »), qu'on analyse
// ici avec tolérance, puis qu'on convertit nous-mêmes en Mermaid, que la
// bibliothèque @excalidraw/mermaid-to-excalidraw transforme en dessin.
//
// Tout ce fichier est pur (aucune dépendance à Vue ni à Excalidraw au
// chargement) pour être testé sous Node : frontend/tests/tableauIA.test.js.
// Seule `sceneDepuisMermaid` charge les bibliothèques, à la demande.

// Plafonds : un schéma lisible tient en quelques éléments ; au-delà, c'est le
// modèle qui boucle ou qui recopie du texte, pas un schéma utile.
export const MAX_NOEUDS = 30
export const MAX_ARETES = 60
export const LIBELLE_MAX = 60
export const ETIQUETTE_MAX = 40
export const TITRE_MAX = 80       // même plafond que le titre d'un tableau (backend)

// Consigne en « few-shot » : le format est montré par un échange précédent
// (demande d'exemple, puis réponse modèle), et non décrit puis illustré dans un
// seul message. Mesuré avec qwen2.5:1.5b sur 5 sujets : 5 schémas exploitables
// sur 5, contre 1 sur 5 avec un exemple inclus dans la consigne — le petit
// modèle recopiait alors l'exemple, ou un gabarit « Élément A -> Élément B »
// (d'où aucun libellé générique ici). L'exemple porte volontairement sur un
// sujet sans rapport avec le travail d'un lycée : s'il déteint sur la réponse,
// cela se voit au lieu de passer pour un vrai contenu.
const FORMAT = [
  'Réponds UNIQUEMENT avec ce format, sans aucun autre texte (ni introduction, ni',
  'conclusion, ni explication) :',
  '- une première ligne « TITRE: » suivie d\'un titre court ;',
  '- puis UNE flèche « -> » par ligne, entre deux éléments du sujet ;',
  '- pour nommer une flèche (un choix par exemple), ajoute-le entre crochets en fin de',
  '  ligne : [oui], [non]…',
  '',
  'Règles : de 3 à 15 éléments, de 6 mots au maximum chacun ; un même élément',
  's\'écrit TOUJOURS avec exactement le même texte.',
].join('\n')

const EXEMPLE_SUJET = 'préparer un pique-nique'
const EXEMPLE_REPONSE = [
  'TITRE: Pique-nique',
  'Choisir le parc -> Météo favorable ?',
  'Météo favorable ? -> Préparer le panier [oui]',
  'Météo favorable ? -> Changer de date [non]',
  'Changer de date -> Météo favorable ?',
  'Préparer le panier -> Partir au parc',
].join('\n')

const RAPPEL_STRICT = 'ATTENTION : ta réponse précédente n\'était pas au bon format. '
  + 'Chaque ligne DOIT contenir une flèche « -> » ENTRE deux éléments. N\'écris rien '
  + 'd\'autre que la ligne TITRE et les lignes de flèches.\n\n'

/**
 * Messages à envoyer au modèle (après l'historique de la conversation) : un
 * échange d'exemple, puis la vraie demande, sujet en dernier — un petit modèle
 * suit mieux ce qu'il lit en dernier. `strict` : seconde tentative, quand la
 * première réponse n'était pas exploitable.
 */
export function messagesTableau(sujet, strict = false) {
  return [
    { role: 'user', content: `Dessine un schéma.\n\n${FORMAT}\n\nSujet : ${EXEMPLE_SUJET}` },
    { role: 'assistant', content: EXEMPLE_REPONSE },
    { role: 'user', content: `${strict ? RAPPEL_STRICT : ''}Même format. Sujet : ${sujet}` },
  ]
}

/** Détecte la commande dans ce que l'utilisatrice a tapé. Renvoie `null` si ce
 *  n'est pas la commande, sinon le sujet (chaîne vide si elle est seule).
 *  « /tableaux » n'est pas la commande : il faut un espace ou la fin du texte. */
export function sujetCommandeTableau(texte) {
  const m = /^\/tableau(?:\s+([\s\S]*))?$/i.exec((texte || '').trim())
  return m ? (m[1] || '').replace(/\s+/g, ' ').trim() : null
}

// ---------- Analyse de la réponse du modèle ----------

// Flèches acceptées : ->, -->, =>, ==>, →… (les petits modèles varient).
const FLECHE = /\s*(?:[-–—=]{1,3}>|→|⟶|➔|➜|➞)\s*/
const PUCE = /^(?:(?:[-*•–—]|\d+[.)])\s+)+/
const TITRE = /^(?:#+\s*)?titre\s*:\s*(.*)$/i
const ETIQUETTE = /\[([^[\]]*)\]/

function compacter(texte) {
  return texte.replace(/\s+/g, ' ').trim()
}

/** Identité d'un élément : même texte, sans tenir compte des espaces ni de la casse. */
function cle(libelle) {
  return compacter(libelle).normalize('NFC').toLowerCase()
}

function tronquer(texte, max) {
  return texte.length > max ? `${texte.slice(0, max - 1).trimEnd()}…` : texte
}

/** Retire guillemets et ponctuation de fin autour d'un libellé, et un crochet
 *  d'étiquette jamais refermé (réponse coupée : « Préparer les activités [o »). */
function nettoyer(texte) {
  return compacter(texte.replace(/\[[^\]]*$/, ''))
    .replace(/^[\s"“”«»'‘’`]+|[\s"“”«»'‘’`.;,]+$/g, '')
}

/**
 * Lit la réponse du modèle. Ne lève jamais d'erreur : ce qui n'est pas compris
 * est ignoré (le modèle bavarde souvent autour du format demandé).
 * Renvoie { titre, noeuds: [{ id, libelle }], aretes: [{ de, vers, etiquette }] },
 * où `de` et `vers` sont des `id` de nœuds. Un nœud n'existe que s'il est relié.
 */
export function analyserSchema(texte) {
  const brut = String(texte || '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')
    .replace(/<think>[\s\S]*$/i, '')            // réflexion jamais refermée
  let titre = ''
  const noeuds = []
  const parCle = new Map()
  const aretes = []
  const parPaire = new Map()
  let precedent = ''          // dernier élément de la ligne de flèches précédente

  for (const ligneBrute of brut.split(/\r?\n/)) {
    if (aretes.length >= MAX_ARETES) break
    if (ligneBrute.trim().startsWith('```')) continue
    const ligne = ligneBrute.replace(/\*\*/g, '').replace(PUCE, '').trim()
    if (!ligne) continue

    const t = TITRE.exec(ligne)
    if (t) {
      if (!titre) titre = tronquer(nettoyer(t[1]), TITRE_MAX)
      continue
    }
    if (!FLECHE.test(ligne)) continue

    // Étiquette entre crochets : en fin de ligne (format demandé), elle qualifie
    // la dernière flèche ; collée à un élément (« A [oui] -> B », vu chez les
    // petits modèles), la flèche qui en part.
    const parties = ligne.split(FLECHE).map((partie) => {
      const e = ETIQUETTE.exec(partie)
      return {
        libelle: nettoyer(e ? partie.replace(ETIQUETTE, ' ') : partie),
        etiquette: e ? tronquer(nettoyer(e[1]), ETIQUETTE_MAX) : '',
      }
    })
    // « -> Étape » sans rien à gauche : le modèle a écrit une liste au lieu de
    // flèches (fréquent avec qwen2.5:1.5b). Lue comme une suite : chaque élément
    // part du dernier de la ligne précédente, le premier part du titre.
    if (!parties[0].libelle) parties[0].libelle = precedent || titre
    precedent = parties[parties.length - 1].libelle || precedent

    for (let i = 0; i + 1 < parties.length; i++) {
      const [a, b] = [parties[i].libelle, parties[i + 1].libelle]
      if (!a || !b || cle(a) === cle(b)) continue
      const nouveaux = [a, b].filter((p) => !parCle.has(cle(p))).length
      if (noeuds.length + nouveaux > MAX_NOEUDS || aretes.length >= MAX_ARETES) continue

      const ids = [a, b].map((libelle) => {
        const k = cle(libelle)
        if (!parCle.has(k)) {
          const noeud = { id: `n${noeuds.length}`, libelle: tronquer(compacter(libelle), LIBELLE_MAX) }
          noeuds.push(noeud)
          parCle.set(k, noeud.id)
        }
        return parCle.get(k)
      })
      const etiquetteArete = parties[i + 1].etiquette || (i === 0 ? parties[0].etiquette : '')
      const paire = `${ids[0]}>${ids[1]}`
      const existante = parPaire.get(paire)
      if (existante) {
        if (!existante.etiquette && etiquetteArete) existante.etiquette = etiquetteArete
        continue
      }
      const arete = { de: ids[0], vers: ids[1], etiquette: etiquetteArete }
      parPaire.set(paire, arete)
      aretes.push(arete)
    }
  }
  return { titre, noeuds, aretes }
}

// Libellé de remplissage (« Élément A », « Étape 3 », « Noeud B », « A ») : signe
// qu'un petit modèle a recopié un gabarit au lieu de traiter le sujet.
const LIBELLE_GENERIQUE = /^(?:(?:é|e)l(?:é|e)ment|(?:é|e)tape|n(?:oe|œ)ud|bo(?:i|î)te)?\s*[a-z0-9]{1,2}$/i

/** Un schéma vaut la peine d'être dessiné : au moins deux éléments reliés, et
 *  pas majoritairement des libellés de remplissage. */
export function schemaExploitable(schema) {
  if (schema.noeuds.length < 2 || schema.aretes.length < 1) return false
  const generiques = schema.noeuds.filter((n) => LIBELLE_GENERIQUE.test(n.libelle)).length
  return generiques * 2 < schema.noeuds.length
}

/** Titre du tableau : celui du modèle, sinon le sujet demandé. */
export function titreTableau(schema, sujet) {
  const base = schema.titre || compacter(sujet)
  return tronquer(base.charAt(0).toUpperCase() + base.slice(1), TITRE_MAX)
}

// ---------- Conversion en Mermaid ----------

/** Texte sûr entre guillemets Mermaid : `"` s'écrit `#quot;` ; `#`, `<` et `>`
 *  passent aussi par une entité (sinon Mermaid les lirait comme du code ou du
 *  HTML) ; les accents graves ouvriraient une chaîne « Markdown ». */
function echapper(texte) {
  return texte
    .replace(/#/g, '#35;')
    .replace(/"/g, '#quot;')
    .replace(/</g, '#lt;')
    .replace(/>/g, '#gt;')
    .replace(/`/g, "'")
}

/** Schéma → texte Mermaid (`flowchart TD`). Libellés TOUJOURS entre guillemets :
 *  c'est ce qui permet d'écrire « Dossier complet ? » ou « Accueil (parents) »
 *  sans que Mermaid y voie de la syntaxe. */
export function versMermaid(schema) {
  const lignes = ['flowchart TD']
  for (const n of schema.noeuds) lignes.push(`  ${n.id}["${echapper(n.libelle)}"]`)
  for (const a of schema.aretes) {
    const fleche = a.etiquette ? `-->|"${echapper(a.etiquette)}"|` : '-->'
    lignes.push(`  ${a.de} ${fleche} ${a.vers}`)
  }
  return lignes.join('\n')
}

// ---------- Mermaid → scène Excalidraw (navigateur) ----------

/**
 * Dessine le Mermaid dans une scène au format .excalidraw. Ces deux
 * bibliothèques sont chargées à l'appel seulement, comme dans TableauBlanc.vue :
 * le démarrage d'Oliv'IA n'est pas alourdi. mermaid-to-excalidraw rend le
 * diagramme dans la page (mesures de texte), il lui faut donc un vrai navigateur.
 */
export async function sceneDepuisMermaid(definition) {
  // Même adresse de polices que TableauBlanc.vue : sans elle, Excalidraw
  // chercherait les polices sur un CDN (refusé par la CSP du backend).
  window.EXCALIDRAW_ASSET_PATH = new URL('excalidraw-assets/', document.baseURI).href
  const [{ parseMermaidToExcalidraw }, { convertToExcalidrawElements }] = await Promise.all([
    import('@excalidraw/mermaid-to-excalidraw'),
    import('@excalidraw/excalidraw'),
  ])
  const { elements, files } = await parseMermaidToExcalidraw(definition)
  return {
    type: 'excalidraw',
    version: 2,
    source: 'oliv-ia',
    elements: convertToExcalidrawElements(elements),
    appState: { viewBackgroundColor: '#ffffff' },
    files: files || {},
  }
}
