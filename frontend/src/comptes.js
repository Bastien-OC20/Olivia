// Mots de passe et comptes : fonctions pures (sans Vue, sans réseau), testées par
// tests/comptes.test.js. Le serveur reste l'autorité : ces contrôles évitent
// seulement un aller-retour inutile et disent à l'utilisatrice quoi corriger.

export const REGLE_MOT_DE_PASSE = '8 caractères au moins, avec trois types parmi : '
  + 'minuscules, majuscules, chiffres et caractères spéciaux.'

/** Nombre de types de caractères présents (minuscules, majuscules, chiffres, autres). */
export function typesDeCaracteres(mot) {
  const s = String(mot ?? '')
  let n = 0
  if (/\p{Ll}/u.test(s)) n += 1
  if (/\p{Lu}/u.test(s)) n += 1
  if (/\d/.test(s)) n += 1
  if (/[^\p{L}\d]/u.test(s)) n += 1
  return n
}

/** Le nouveau mot de passe respecte-t-il la règle ? Renvoie '' ou le message à afficher. */
export function erreurMotDePasseFaible(nouveau) {
  const s = String(nouveau ?? '')
  if ([...s].length < 8 || typesDeCaracteres(s) < 3) {
    return `Mot de passe trop faible : ${REGLE_MOT_DE_PASSE}`
  }
  return ''
}

/** Contrôle du formulaire « changer mon mot de passe ». '' si tout est en ordre. */
export function erreurFormulaireMotDePasse({ ancien, nouveau, confirmation }) {
  if (!ancien) return 'Saisissez votre mot de passe actuel.'
  if (!nouveau) return 'Saisissez le nouveau mot de passe.'
  const faible = erreurMotDePasseFaible(nouveau)
  if (faible) return faible
  if (nouveau === ancien) return 'Le nouveau mot de passe doit être différent de l\'ancien.'
  if (nouveau !== confirmation) return 'La confirmation ne correspond pas au nouveau mot de passe.'
  return ''
}

/** Contrôle de la saisie d'un nouveau mot de passe pour un autre compte. */
export function erreurReinitialisation(nouveau) {
  if (!nouveau) return 'Saisissez le nouveau mot de passe.'
  return erreurMotDePasseFaible(nouveau)
}

/** Message de succès après un changement de mot de passe. */
export function messageMotDePasseChange(sessionsFermees) {
  const n = Number(sessionsFermees) || 0
  let suite
  if (n <= 0) suite = 'Aucune autre session n\'était ouverte.'
  else if (n === 1) suite = 'Votre autre session a été fermée : reconnectez-vous avec le nouveau mot de passe.'
  else suite = `Vos ${n} autres sessions ont été fermées : reconnectez-vous avec le nouveau mot de passe.`
  return `Mot de passe modifié. ${suite}`
}

/** Message à afficher pour une réponse en erreur : le `detail` du serveur tel quel,
 *  sinon une consigne selon le code (429 : temporisation, après trop d'essais). */
export function messageErreurServeur(statut, corps, retryAfter) {
  const detail = corps && typeof corps.detail === 'string' ? corps.detail.trim() : ''
  if (detail) return detail
  if (statut === 429) {
    const s = Number(retryAfter)
    return Number.isFinite(s) && s > 0
      ? `Trop d'essais. Patientez ${Math.ceil(s)} seconde(s) avant de réessayer.`
      : 'Trop d\'essais. Patientez un moment avant de réessayer.'
  }
  if (statut === 403) return 'Cette action est réservée au responsable de l\'organisation dans Oliv\'IA. Demandez-lui de la faire pour vous.'
  return 'L\'opération a échoué. Réessayez, ou demandez de l\'aide au responsable.'
}

/** Actions proposées sur une ligne de la liste des comptes. Jamais de suppression,
 *  de réinitialisation ni de changement de rôle sur sa propre ligne : un
 *  responsable ne doit pas pouvoir se retirer lui-même l'accès. */
export function actionsCompte(compte) {
  const moi = Boolean(compte?.moi)
  const responsable = compte?.role === 'responsable'
  return {
    reinitialiser: !moi,
    debloquer: Boolean(compte?.bloque),
    changerRole: moi ? null : (responsable ? 'membre' : 'responsable'),
    supprimer: !moi,
  }
}

/** Libellé du bouton de changement de rôle. */
export function libelleChangerRole(nouveauRole) {
  return nouveauRole === 'responsable' ? 'Passer responsable' : 'Passer membre'
}

/** Question de confirmation avant de supprimer un compte (affichée dans la page). */
export function questionSuppression(compte) {
  return `Supprimer le compte « ${compte?.username ?? ''} » ? Il ne pourra plus se connecter. `
    + 'Cette action est irréversible.'
}

/** Date de création lisible (le serveur donne des secondes depuis 1970). */
export function dateCreation(secondes) {
  const n = Number(secondes)
  if (!Number.isFinite(n) || n <= 0) return ''
  return new Date(n * 1000).toLocaleDateString('fr-FR', {
    day: 'numeric', month: 'long', year: 'numeric',
  })
}

/** Remplace un compte dans la liste par sa vue à jour (réponse du serveur). */
export function remplacerCompte(liste, vue) {
  return liste.map(c => (c.id === vue.id ? { ...c, ...vue, moi: c.moi } : c))
}

/** Liste triée : soi d'abord, puis par identifiant. */
export function trierComptes(liste) {
  return [...liste].sort((a, b) => {
    if (a.moi !== b.moi) return a.moi ? -1 : 1
    return String(a.username).localeCompare(String(b.username), 'fr')
  })
}
