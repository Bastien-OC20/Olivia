import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

// Tant que le moteur n'est pas prêt, on revérifie régulièrement : le panneau
// disparaît alors de lui-même dès qu'Ollama est démarré ou qu'un modèle a fini
// de se télécharger, sans que l'utilisatrice ait à recharger la page. Une fois
// prêt et complet, plus aucune vérification de fond : une panne ultérieure est
// détectée par la conversation elle-même (voir `signalerPanne`).
const INTERVALLE_MS = 10000
// Pendant un téléchargement, la barre de progression doit avancer à vue d'œil.
const INTERVALLE_TELECHARGEMENT_MS = 2000

/**
 * État du moteur d'IA (Ollama) : joignable ? modèles nécessaires installés ?
 * Source : GET /api/moteur/etat (backend/moteur.py).
 */
export const useMoteurStore = defineStore('moteur', () => {
  // null tant que la première réponse n'est pas arrivée : on n'affiche rien
  // plutôt qu'un panneau d'alerte qui clignoterait à chaque ouverture.
  const etat = ref(null)
  const enCours = ref(false)
  // Fermé par l'utilisatrice : ne réapparaît qu'à la prochaine panne constatée.
  const masque = ref(false)
  let minuteur = null
  // Appelé quand le moteur devient prêt (ex. recharger la liste des modèles).
  let quandPret = null

  const pret = computed(() => etat.value?.pret === true)
  const visible = computed(() => !!etat.value && !masque.value
    && (!etat.value.pret || !etat.value.complet))

  const telechargementEnCours = computed(() => (etat.value?.modeles || [])
    .some((m) => m.telechargement?.etat === 'en_cours'))

  /** Demande au backend de faire télécharger un modèle par Ollama. */
  async function telecharger(nom) {
    try {
      const r = await fetch('/api/moteur/telecharger', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ modele: nom }),
      })
      if (!r.ok) console.warn('Téléchargement refusé :', (await r.json().catch(() => ({}))).detail)
    } catch (e) {
      console.warn('Téléchargement impossible :', e.message)
    }
    masque.value = false
    // Fil de vérification en cours éventuel : on attend qu'il rende la main
    // pour repartir aussitôt avec la progression.
    if (enCours.value) await new Promise((ok) => setTimeout(ok, 300))
    await verifier()
  }

  async function verifier() {
    if (enCours.value) return
    enCours.value = true
    const etaitPret = pret.value
    try {
      const r = await fetch('/api/moteur/etat')
      // 401 : session expirée, App.vue appelle alors arreter() — on ne
      // replanifie rien. Autre erreur : backend d'une version antérieure sans
      // cette route — on n'affiche rien plutôt qu'une fausse alerte.
      if (r.status === 401) return
      if (r.ok) etat.value = await r.json()
    } catch (e) {
      console.warn('État du moteur indisponible :', e.message)
    } finally {
      enCours.value = false
    }
    if (pret.value && !etaitPret && quandPret) quandPret()
    planifier()
  }

  function planifier() {
    clearTimeout(minuteur)
    minuteur = null
    // Aussi tant qu'un modèle conseillé manque et que le panneau est affiché :
    // il se retire de lui-même à la fin du téléchargement de bge-m3.
    if (etat.value && (!pret.value || visible.value || telechargementEnCours.value)) {
      minuteur = setTimeout(verifier,
        telechargementEnCours.value ? INTERVALLE_TELECHARGEMENT_MS : INTERVALLE_MS)
    }
  }

  /** Démarre la surveillance (après connexion). */
  function demarrer(rappelPret) {
    quandPret = rappelPret || null
    masque.value = false
    verifier()
  }

  /** La conversation a constaté que le moteur ne répond pas : on le redit. */
  function signalerPanne() {
    masque.value = false
    verifier()
  }

  function masquer() {
    masque.value = true
  }

  /** Déconnexion : rien ne doit tourner ni rester affiché pour le compte suivant. */
  function arreter() {
    clearTimeout(minuteur)
    minuteur = null
    etat.value = null
    masque.value = false
    quandPret = null
  }

  return {
    etat, enCours, masque, pret, visible, telechargementEnCours,
    verifier, telecharger, demarrer, signalerPanne, masquer, arreter,
  }
})
