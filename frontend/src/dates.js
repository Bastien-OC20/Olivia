// Dates des listes du panneau (conversations, tableaux) : fonctions pures,
// testées sans Vue. Les horodatages du backend sont en SECONDES (time.time()).

const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })
const UNITES = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

/** Date relative en français : « il y a 5 minutes », « hier »…
 *  `ts` en secondes ; `maintenant` en millisecondes (fixé par les tests). */
export function dateRelative(ts, maintenant = Date.now()) {
  if (!ts) return ''
  const secondes = (Number(ts) * 1000 - maintenant) / 1000
  if (!Number.isFinite(secondes)) return ''
  for (const [unite, taille] of UNITES) {
    if (Math.abs(secondes) >= taille) return rtf.format(Math.round(secondes / taille), unite)
  }
  return "à l'instant"
}

const GROUPES = [
  { id: 'aujourdhui', libelle: "Aujourd'hui" },
  { id: 'hier', libelle: 'Hier' },
  { id: 'semaine', libelle: '7 derniers jours' },
  { id: 'ancien', libelle: 'Plus ancien' },
]

/** Minuit (heure locale) du jour de `ms`, décalé de `jours` jours calendaires.
 *  setDate plutôt que des multiples de 86 400 s : un jour de changement d'heure
 *  ne dure pas 24 h. */
function minuit(ms, jours = 0) {
  const d = new Date(ms)
  d.setHours(0, 0, 0, 0)
  d.setDate(d.getDate() + jours)
  return d.getTime()
}

/** Range des éléments par jour calendaire local : « Aujourd'hui », « Hier »,
 *  « 7 derniers jours » (de l'avant-veille à il y a 7 jours), « Plus ancien ».
 *  Renvoie les seuls groupes non vides, dans cet ordre, sous la forme
 *  `{ id, libelle, elements }`. L'ordre des éléments est conservé ; un élément
 *  sans date valable va dans « Plus ancien », une date future (horloge décalée)
 *  dans « Aujourd'hui ». */
export function grouperParDate(elements, cle, maintenant = Date.now()) {
  const aujourdhui = minuit(maintenant)
  const hier = minuit(maintenant, -1)
  const semaine = minuit(maintenant, -7)
  const parGroupe = { aujourdhui: [], hier: [], semaine: [], ancien: [] }
  for (const el of elements || []) {
    const ts = Number(el?.[cle])
    const ms = ts > 0 ? ts * 1000 : NaN
    let id = 'ancien'
    if (Number.isFinite(ms)) {
      if (ms >= aujourdhui) id = 'aujourdhui'
      else if (ms >= hier) id = 'hier'
      else if (ms >= semaine) id = 'semaine'
    }
    parGroupe[id].push(el)
  }
  return GROUPES
    .filter(g => parGroupe[g.id].length > 0)
    .map(g => ({ ...g, elements: parGroupe[g.id] }))
}
