// Rôles des comptes (responsable / membre) : fonctions pures, testées sans Vue.
// Le serveur reste l'autorité (403 sur toute route réservée) ; ces fonctions ne
// servent qu'à ne pas proposer ce qui serait refusé.

export const ROLE_RESPONSABLE = 'responsable'
export const ROLE_MEMBRE = 'membre'

/** Seul « responsable » ouvre les options réservées ; tout autre rôle (absent,
 *  inconnu) est traité comme un membre. */
export function estResponsable(role) {
  return role === ROLE_RESPONSABLE
}

export function libelleRole(role) {
  return role === ROLE_RESPONSABLE ? 'Responsable' : 'Membre'
}

/** Réglages que le serveur laisse modifier à un membre (voir PUT /api/settings). */
export const CLES_MEMBRE = [
  'reasoning_style', 'tone', 'compute_device', 'simple_mode', 'temperature', 'privacy_consent',
  'theme',
]

/** Réglages à envoyer à l'enregistrement. Un responsable envoie tout ; un membre
 *  seulement ses réglages de confort : le serveur refuse (403) toute clé réservée
 *  dont la valeur diffère, et ne doit pas avoir à comparer le reste. L'état des
 *  secrets (`etat_secrets`) n'est pas un réglage et n'est jamais renvoyé. */
export function reglagesAEnvoyer(data, role) {
  const reglages = { ...(data || {}) }
  delete reglages.etat_secrets
  if (estResponsable(role)) return reglages
  const out = {}
  for (const cle of CLES_MEMBRE) {
    if (cle in reglages) out[cle] = reglages[cle]
  }
  return out
}

const ONGLETS = [
  { id: 'reasoning', label: 'Préférences', simple: true, responsable: false },
  { id: 'documents', label: 'Documents', simple: true, responsable: false },
  { id: 'formules', label: 'Formules', simple: true, responsable: true },
  { id: 'search', label: 'Recherche web', simple: false, responsable: true },
  { id: 'connectors', label: 'Connexions', simple: false, responsable: true },
  { id: 'privacy', label: 'Confidentialité', simple: true, responsable: false },
  { id: 'compte', label: 'Mon compte', simple: true, responsable: false },
  { id: 'comptes', label: 'Comptes', simple: true, responsable: true },
]

/** Onglets des Paramètres selon le rôle et le mode (simple ou avancé). */
export function onglets(role, simple) {
  const resp = estResponsable(role)
  return ONGLETS.filter(t => (resp || !t.responsable) && (!simple ? true : t.simple))
}

/** Un onglet est-il proposé ? (pour retomber sur un onglet valable) */
export function ongletDisponible(id, role, simple) {
  return onglets(role, simple).some(t => t.id === id)
}

/** Ce que contient l'export de la section Confidentialité. */
export function texteExport(role) {
  if (estResponsable(role)) {
    return 'Exportez les paramètres et les données de toute votre organisation '
      + '(conversations et tableaux de tous les comptes) au format JSON.'
  }
  return 'Exportez vos paramètres et vos données : vos conversations et vos tableaux, '
    + 'ainsi que ceux, plus anciens, communs à toute l\'organisation, au format JSON.'
}

export const MESSAGE_RESERVE = 'Réglé par le responsable de votre organisation.'
