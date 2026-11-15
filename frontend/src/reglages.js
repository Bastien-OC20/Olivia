// Fonctions pures des réglages (stores/settings.js), testables sans Vue.

/** Copie profonde d'un réglage (les valeurs sont du JSON). */
export function copier(valeur) {
  return JSON.parse(JSON.stringify(valeur))
}

/** Réglages reçus du serveur posés sur les valeurs par défaut (connecteurs fusionnés
 *  un par un, pour qu'un champ absent garde sa valeur par défaut). */
export function fusionner(base, loaded) {
  const out = copier(base)
  for (const k in loaded) {
    if (loaded[k] && typeof loaded[k] === 'object' && !Array.isArray(loaded[k]) && out[k]) {
      out[k] = { ...out[k], ...loaded[k] }
      if (k === 'connectors') {
        for (const c in loaded[k]) out[k][c] = { ...(base.connectors[c] || {}), ...loaded[k][c] }
      }
    } else {
      out[k] = loaded[k]
    }
  }
  return out
}

/** Valeurs à remettre à l'écran quand on annule : une copie INDÉPENDANTE des
 *  réglages enregistrés (modifier l'une ne doit jamais modifier l'autre). */
export function restaurer(enregistre) {
  return copier(enregistre)
}
