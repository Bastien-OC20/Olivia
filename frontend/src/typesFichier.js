// Nom d'icône (voir icones.js) correspondant à un élément de l'explorateur.
// Fonction pure : testée sans DOM par tests/typesFichier.test.js.

const IMAGES = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp']
const TABLEURS = ['.xlsx', '.xlsm', '.csv']

/**
 * @param {string} ext extension avec son point (« .pdf »), éventuellement absente
 * @param {boolean} [estDossier]
 * @returns {string} nom d'icône
 */
export function nomIconeFichier(ext, estDossier = false) {
  if (estDossier) return 'dossier'
  const e = String(ext || '').toLowerCase()
  if (IMAGES.includes(e)) return 'image'
  // « grille » et non « tableau » : l'icône des tableaux blancs prêterait à
  // confusion avec la section Tableaux du rail.
  if (TABLEURS.includes(e)) return 'grille'
  return 'document'
}

/**
 * Chemin affichable d'un document : sans l'identifiant interne de la racine
 * (« r0/ »), qui ne dit rien à l'utilisatrice. Le chemin complet reste celui
 * envoyé au serveur ; seule la présentation change.
 * @param {string} chemin
 * @returns {string}
 */
export function cheminLisible(chemin) {
  return String(chemin || '').replace(/^r\d+(\/|$)/, '')
}
