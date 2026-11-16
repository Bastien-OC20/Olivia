// Analyse du flux de chat (SSE de POST /api/chat/stream) : fonctions PURES, testées
// sans navigateur (tests/fluxChat.test.js). `send()` (stores/chat.js) ne fait plus
// que lire le réseau et appeler ces fonctions.

/**
 * Lit une ligne du flux. Renvoie l'objet JSON, ou null pour une ligne à ignorer :
 * étrangère au protocole (ne commence pas par « data: »), vide ou incomplète.
 */
export function analyserLigne(ligne) {
  if (typeof ligne !== 'string' || !ligne.startsWith('data:')) return null
  try {
    const payload = JSON.parse(ligne.slice(5).trim())
    return payload !== null && typeof payload === 'object' ? payload : null
  } catch {
    return null           // ligne incomplète ou étrangère au protocole
  }
}

/** Fusionne une étape reçue dans la liste : même `id` = mise à jour (fusion des
 *  champs) ; sinon l'étape est créée, même si sa ligne `en_cours` n'est jamais
 *  arrivée. Une étape sans identifiant exploitable est ignorée. */
function appliquerEtape(message, etape) {
  if (!etape || typeof etape !== 'object' || etape.id === undefined || etape.id === null) return
  if (!Array.isArray(message.etapes)) message.etapes = []
  const existante = message.etapes.find((e) => e.id === etape.id)
  if (existante) Object.assign(existante, etape)
  else message.etapes.push({ ...etape })
}

/** Proposition de document Word nettoyée (champs texte seulement). Un `type_document`
 *  inconnu est conservé tel quel : c'est ChatPanel qui retombe sur le type par défaut. */
function proposition(brut) {
  if (!brut || typeof brut !== 'object' || brut.type !== 'document_word') return null
  const texte = (valeur) => (typeof valeur === 'string' ? valeur : '')
  return {
    type: 'document_word',
    type_document: texte(brut.type_document),
    titre: texte(brut.titre),
    objet: texte(brut.objet),
    destinataire: texte(brut.destinataire),
    texte: texte(brut.texte),
  }
}

/**
 * Applique un évènement du flux au message d'Olivia (`content`, `erreur`, `etapes`,
 * `proposition`). Renvoie true quand le flux est terminé (erreur ou `done`).
 */
export function appliquerEvenement(message, payload) {
  if (!payload || typeof payload !== 'object') return false
  // Erreur du moteur (Ollama éteint, modèle absent…), envoyée par le
  // backend ou par Ollama en cours de réponse. Auparavant ignorée :
  // l'utilisatrice voyait une bulle vide, sans explication.
  if (payload.error) {
    message.erreur = String(payload.error)
    return true
  }
  if (payload.etape) appliquerEtape(message, payload.etape)
  if (payload.proposition) {
    // Une seule proposition par message : la dernière reçue l'emporte.
    const p = proposition(payload.proposition)
    if (p) message.proposition = p
  }
  if (payload.message?.content) {
    message.content += payload.message.content
  }
  if (payload.done) {
    // Plafond de génération atteint (num_predict, voir backend) : la
    // réponse est coupée, il faut le dire avant qu'elle soit recopiée.
    if (payload.done_reason === 'length') {
      message.erreur = 'Réponse coupée : longueur maximale atteinte. '
        + 'Demandez la suite, ou une version plus courte.'
    }
    return true
  }
  return false
}

/** Copie des étapes et de la proposition à enregistrer avec le message. */
export function champsOutils(m) {
  return {
    ...(Array.isArray(m?.etapes) && m.etapes.length ? { etapes: m.etapes } : {}),
    ...(m?.proposition ? { proposition: m.proposition } : {}),
  }
}
