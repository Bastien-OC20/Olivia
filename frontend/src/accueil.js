// Écran d'accueil (conversation vide) : fonctions pures, testées sans Vue.

/** « Bonjour » de 5 h à 17 h 59, « Bonsoir » sinon (heure locale de `date`). */
export function salutation(date = new Date()) {
  const heure = date.getHours()
  return heure >= 5 && heure < 18 ? 'Bonjour' : 'Bonsoir'
}

/** Identifiant de connexion présenté comme un prénom : première lettre en
 *  majuscule. Array.from : un caractère accentué ou hors du plan de base n'est
 *  pas coupé en deux. Chaîne vide si l'identifiant manque. */
export function nomAffiche(identifiant) {
  if (typeof identifiant !== 'string' || !identifiant.trim()) return ''
  const lettres = Array.from(identifiant.trim())
  return lettres[0].toUpperCase() + lettres.slice(1).join('')
}

/** Cartes d'actions de l'accueil.
 *  - `envoyer` : la demande part telle quelle ;
 *  - `preremplir` : le texte est placé dans la saisie, à compléter (reformuler ou
 *    résumer sans texte n'aurait pas de sens) ;
 *  - `documents` : ouvre l'onglet Documents pour joindre un fichier. */
export const ACTIONS_ACCUEIL = [
  {
    id: 'courriel',
    icone: 'mail',
    titre: 'Courriel aux familles',
    description: 'Annoncer le prochain conseil de classe',
    type: 'envoyer',
    texte: 'Rédige un courriel aux parents pour annoncer le prochain conseil de classe.',
  },
  {
    id: 'ordre-du-jour',
    icone: 'calendrier',
    titre: 'Ordre du jour',
    description: "Préparer une réunion d'équipe pédagogique",
    type: 'envoyer',
    texte: "Prépare un ordre du jour pour une réunion d'équipe pédagogique.",
  },
  {
    id: 'reformuler',
    icone: 'crayon',
    titre: 'Reformuler un texte',
    description: 'Plus professionnel et plus concis',
    type: 'preremplir',
    texte: 'Reformule ce texte de façon plus professionnelle et concise :\n',
  },
  {
    id: 'compte-rendu',
    icone: 'document',
    titre: 'Compte rendu',
    description: 'Synthétiser vos notes de réunion',
    type: 'preremplir',
    texte: 'Fais un compte-rendu synthétique à partir de mes notes :\n',
  },
  {
    id: 'document',
    icone: 'dossier',
    titre: 'Utiliser un document',
    description: "Choisir un fichier pour qu'Oliv'IA s'en serve",
    type: 'documents',
    texte: '',
  },
  {
    id: 'schema',
    icone: 'tableau',
    titre: 'Dessiner un schéma',
    description: 'Un tableau blanc à partir d\'un sujet',
    type: 'preremplir',
    texte: '/tableau ',
  },
]

/** Les `n` éléments les plus récents selon `cle` (horodatage en secondes ; absent
 *  ou invalide = 0), du plus récent au plus ancien. L'entrée n'est pas modifiée. */
export function recentes(liste, cle, n = 3) {
  const date = (el) => {
    const v = Number(el?.[cle])
    return Number.isFinite(v) ? v : 0
  }
  return [...(liste || [])]
    .sort((a, b) => date(b) - date(a))
    .slice(0, Math.max(0, n))
}
