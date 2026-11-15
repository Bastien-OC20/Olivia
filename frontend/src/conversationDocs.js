// Fonctions pures du store des conversations (stores/chat.js) : documents joints
// rattachés à une conversation, et décision « cette réponse tardive s'applique-t-elle
// encore ? ». Sorties du store pour être testées sans Vue ni réseau.

/** Nombre maximal de documents joints à une conversation (aligné sur le backend). */
export const DOC_MAX = 10

/**
 * Une réponse asynchrone (enregistrement, ouverture) ne s'applique à l'écran que si
 * l'utilisatrice est toujours dans le contexte qui l'a demandée. Les contextes sont
 * comparés par identité : un nouveau contexte est créé à chaque ouverture ou
 * nouvelle conversation, y compris quand on revient sur la même conversation.
 */
export function reponseApplicable(contexteDepart, contexteActif) {
  return !!contexteDepart && contexteDepart === contexteActif
}

/**
 * Identifiant à retenir comme conversation courante après un enregistrement.
 * `null` : ne rien changer à l'affichage (autre conversation entre-temps, ou pas
 * d'identifiant reçu).
 */
export function idAAppliquerApresEnregistrement(contexteDepart, contexteActif, idRecu) {
  if (!idRecu) return null
  return reponseApplicable(contexteDepart, contexteActif) ? idRecu : null
}

/** Liste brute (réponse du serveur, absente pour une ancienne conversation) vers
 *  `[{ path, name }]` : entrées valides, sans doublon, `DOC_MAX` au plus. */
export function normaliserDocuments(brut) {
  if (!Array.isArray(brut)) return []
  const vus = new Set()
  const out = []
  for (const d of brut) {
    const path = typeof d?.path === 'string' ? d.path.trim() : ''
    if (!path || vus.has(path)) continue
    vus.add(path)
    out.push({ path, name: (typeof d.name === 'string' && d.name.trim()) || path })
    if (out.length >= DOC_MAX) break
  }
  return out
}

/** Ce qui est envoyé au serveur : chemin et nom seulement, JAMAIS le contenu. */
export function documentsPourEnvoi(docs) {
  return normaliserDocuments((docs || []).map((d) => ({ path: d?.path, name: d?.name })))
}

/** Objet document attendu par `addFileContext`, construit comme dans FileExplorer.vue
 *  à partir de la réponse de `GET /api/fs/text`. Lève une erreur si illisible. */
export function documentDepuisTexte(path, name, data) {
  if (!data || data.empty) {
    throw new Error('aucun texte lisible (document scanné ou protégé ?)')
  }
  return {
    path,
    name: data.name || name || path,
    content: data.content || '',
    sourceTruncated: !!data.truncated,
  }
}

/** Phrase affichée quand des documents joints ne peuvent plus être rechargés. */
export function avisDocumentsIndisponibles(noms) {
  const liste = (noms || []).filter(Boolean)
  if (!liste.length) return ''
  const n = liste.length
  return n === 1
    ? `1 document joint n'est plus disponible : ${liste[0]}. Ajoutez-le de nouveau si besoin.`
    : `${n} documents joints ne sont plus disponibles : ${liste.join(', ')}. `
      + 'Ajoutez-les de nouveau si besoin.'
}

/** Ajoute à `actuels` les documents rechargés qui n'y sont pas déjà (l'utilisatrice a pu
 *  en joindre pendant le rechargement), dans la limite de `DOC_MAX`. */
export function fusionnerDocuments(actuels, recharges) {
  const out = [...actuels]
  for (const d of recharges) {
    if (out.length >= DOC_MAX) break
    if (!out.some((x) => x.path === d.path)) out.push(d)
  }
  return out
}
