// Thème de l'interface (clair / sombre) : fonctions pures, testées sans DOM.
// Le thème est porté par l'attribut `data-theme` de <html> ; style.css définit
// les couleurs de chacun.

/** Valeurs possibles du réglage `theme` (alignées sur backend/settings.py). */
export const THEMES = ['systeme', 'sombre', 'clair']

/** Thème réellement affiché. « systeme » suit la préférence de Windows ; une
 *  valeur absente ou inconnue (réglage ancien, corrompu) fait de même plutôt
 *  que de laisser l'interface sans couleurs. */
export function themeEffectif(reglage, prefereSombre) {
  if (reglage === 'sombre' || reglage === 'clair') return reglage
  return prefereSombre ? 'sombre' : 'clair'
}

/** Pose le thème sur l'élément racine (typiquement `document.documentElement`). */
export function appliquerTheme(racine, theme) {
  racine.dataset.theme = theme
}
