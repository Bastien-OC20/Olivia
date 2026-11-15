// État des secrets (mot de passe de la boîte mail, jeton Notion, clé Brave) :
// ce que le serveur annonce dans `etat_secrets` de GET /api/settings.

export const NOMS_SECRETS = {
  imap: 'connectors.imap.password',
  notion: 'connectors.notion.api_token',
  brave: 'search_brave_api_key',
}

export const NOTE_EN_CLAIR = 'Enregistré en clair sur ce poste (clé USB, macOS ou Linux).'
export const AVERTISSEMENT_A_RESSAISIR =
  'Ce secret n\'est plus lisible sur ce poste : saisissez-le de nouveau.'

/** Que dire à côté d'un champ secret ? 'a_ressaisir' (avertissement), 'clair'
 *  (ligne discrète) ou null. `etat` est `etat_secrets`, éventuellement absent
 *  (serveur plus ancien) : on n'affiche alors rien plutôt qu'une fausse alerte. */
export function noteSecret(etat, nom) {
  if (!etat || typeof etat !== 'object') return null
  if (Array.isArray(etat.a_ressaisir) && etat.a_ressaisir.includes(nom)) return 'a_ressaisir'
  if (etat.chiffres === false) return 'clair'
  return null
}
