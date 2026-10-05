import { defineStore } from 'pinia'
import { ref } from 'vue'

/**
 * Tableaux blancs (Excalidraw) de l'organisation connectée.
 * Source : /api/tableaux (backend/tableaux.py). Un tableau ouvert remplace la
 * conversation dans la zone principale (App.vue) ; « ← Conversation » la rétablit.
 */
export const useTableauxStore = defineStore('tableaux', () => {
  const liste = ref([])
  const indisponible = ref(false)
  // Tableau ouvert (données complètes, scène comprise), ou null.
  const courant = ref(null)
  // État de la sauvegarde automatique : '' | 'en_cours' | 'enregistre' | 'erreur'.
  const sauvegarde = ref('')
  const erreurSauvegarde = ref('')

  async function charger() {
    try {
      const r = await fetch('/api/tableaux')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      liste.value = (await r.json()).tableaux || []
      indisponible.value = false
    } catch (e) {
      console.warn('Tableaux indisponibles :', e.message)
      indisponible.value = true
    }
  }

  async function ouvrir(id) {
    const r = await fetch(`/api/tableaux/${encodeURIComponent(id)}`)
    if (!r.ok) {
      alert("Ce tableau n'a pas pu être ouvert.")
      await charger()
      return
    }
    courant.value = await r.json()
    sauvegarde.value = ''
    erreurSauvegarde.value = ''
  }

  async function nouveau() {
    const r = await fetch('/api/tableaux', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titre: '' }),
    })
    if (!r.ok) {
      alert("Le tableau n'a pas pu être créé.")
      return
    }
    courant.value = await r.json()
    sauvegarde.value = ''
    await charger()
  }

  /**
   * Crée un tableau déjà dessiné (schéma produit par /tableau), SANS l'ouvrir :
   * l'appelant choisit le moment de l'ouvrir. Renvoie le tableau créé ; lève une
   * erreur lisible si le serveur refuse ou ne répond pas.
   */
  async function creerAvecScene(titre, scene) {
    const r = await fetch('/api/tableaux', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titre, scene }),
    })
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail
      throw new Error(detail || `Le tableau n'a pas pu être créé (erreur ${r.status}).`)
    }
    const cree = await r.json()
    await charger()
    return cree
  }

  async function renommer(id, titre) {
    const r = await fetch(`/api/tableaux/${encodeURIComponent(id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ titre }),
    })
    if (!r.ok) return false
    const maj = await r.json()
    if (courant.value?.id === id) courant.value.titre = maj.titre
    await charger()
    return true
  }

  /** Enregistre la scène sérialisée par Excalidraw (format .excalidraw). */
  async function enregistrerScene(id, scene) {
    sauvegarde.value = 'en_cours'
    try {
      const r = await fetch(`/api/tableaux/${encodeURIComponent(id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scene }),
      })
      if (!r.ok) {
        const detail = (await r.json().catch(() => ({}))).detail
        throw new Error(detail || `HTTP ${r.status}`)
      }
      sauvegarde.value = 'enregistre'
      erreurSauvegarde.value = ''
      charger()
      return true
    } catch (e) {
      sauvegarde.value = 'erreur'
      erreurSauvegarde.value = e instanceof TypeError
        ? "Oliv'IA ne répond pas : les dernières modifications ne sont pas enregistrées."
        : e.message
      return false
    }
  }

  async function supprimer(id) {
    const r = await fetch(`/api/tableaux/${encodeURIComponent(id)}`, { method: 'DELETE' })
    if (!r.ok) return false
    if (courant.value?.id === id) fermer()
    await charger()
    return true
  }

  function fermer() {
    courant.value = null
    sauvegarde.value = ''
    erreurSauvegarde.value = ''
  }

  /** Déconnexion : rien du compte précédent ne doit rester affiché. */
  function reinitialiser() {
    liste.value = []
    indisponible.value = false
    fermer()
  }

  return {
    liste, indisponible, courant, sauvegarde, erreurSauvegarde,
    charger, ouvrir, nouveau, creerAvecScene, renommer, enregistrerScene, supprimer, fermer, reinitialiser,
  }
})
