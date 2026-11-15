// Navigation au clavier dans une liste d'éléments (onglets, menus) : fonction
// pure, testée sans DOM. Le composant applique le focus à l'indice renvoyé.

/** Indice de l'élément à atteindre après la touche `touche`.
 *
 *  Haut / Bas (et Gauche / Droite si `horizontal`) passent au précédent ou au
 *  suivant en bouclant ; Début et Fin vont au premier et au dernier. Si aucun
 *  élément n'a encore le focus (`index` < 0), Bas mène au premier et Haut au
 *  dernier. Renvoie null pour une autre touche ou une liste vide : l'appelant
 *  laisse alors la touche à son comportement habituel. */
export function indexApresTouche(touche, index, total, { horizontal = false } = {}) {
  if (!(total > 0)) return null
  const precedent = touche === 'ArrowUp' || (horizontal && touche === 'ArrowLeft')
  const suivant = touche === 'ArrowDown' || (horizontal && touche === 'ArrowRight')
  if (touche === 'Home') return 0
  if (touche === 'End') return total - 1
  if (precedent) return index < 0 ? total - 1 : (index - 1 + total) % total
  if (suivant) return index < 0 ? 0 : (index + 1) % total
  return null
}
