import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  // `null` tant que le serveur n'a pas répondu : l'interface ne doit afficher NI
  // l'application NI l'écran de connexion avant de savoir, sinon l'écran de
  // connexion apparaît puis disparaît à chaque rechargement de page.
  const connecte = ref(null)
  const identite = ref(null)
  // Message affiché en haut de l'écran de connexion (session expirée en cours
  // d'usage). Vide le reste du temps.
  const avis = ref('')

  /** Répond à « suis-je connectée ? » au démarrage, sans effet de bord. */
  async function verifier() {
    try {
      const r = await fetch('/api/auth/me')
      if (r.ok) {
        identite.value = await r.json()
        connecte.value = true
        return
      }
    } catch (e) {
      console.warn('Vérification de la session impossible :', e.message)
    }
    identite.value = null
    connecte.value = false
  }

  /** Tente une connexion. Renvoie { ok } ou { ok: false, error } à afficher tel quel. */
  async function connexion(username, password) {
    try {
      const r = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      const body = await r.json().catch(() => null)
      if (!r.ok) {
        // Le backend renvoie déjà un message unique et lisible (« Identifiant ou
        // mot de passe incorrect ») : on le reprend au lieu d'en inventer un qui
        // distinguerait compte inconnu et mot de passe faux.
        return { ok: false, error: body?.detail || 'Connexion impossible.' }
      }
      identite.value = body
      connecte.value = true
      avis.value = ''
      return { ok: true }
    } catch (e) {
      console.error('Connexion impossible :', e)
      return { ok: false, error: "Olivia ne répond pas. Vérifiez qu'elle est bien démarrée." }
    }
  }

  async function deconnexion() {
    try {
      await fetch('/api/auth/logout', { method: 'POST' })
    } catch (e) {
      // La déconnexion côté serveur a pu échouer, mais on ferme quand même la
      // session côté écran : rester bloquée dans l'application serait pire.
      console.warn('Déconnexion côté serveur impossible :', e.message)
    }
    identite.value = null
    connecte.value = false
    avis.value = ''
  }

  /**
   * Ramène à l'écran de connexion dès qu'un appel authentifié se voit refuser
   * (session expirée : le TTL est de 8 h, donc cela arrive en pleine journée de
   * travail). Emballer `fetch` une fois ici est plus court et plus sûr que
   * d'instrumenter les ~25 appels dispersés dans les composants, dont aucun ne
   * distingue aujourd'hui un 401 d'une autre panne : sans cela l'utilisatrice
   * verrait une application qui ne répond plus, sans explication.
   */
  function surveillerExpiration() {
    const natif = window.fetch
    window.fetch = async (...args) => {
      const r = await natif(...args)
      const cible = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '')
      // Les routes /api/auth/* sont exclues : un mot de passe refusé répond 401
      // aussi, et ce n'est pas une session expirée.
      if (r.status === 401 && connecte.value === true
          && cible.includes('/api/') && !cible.includes('/api/auth/')) {
        identite.value = null
        connecte.value = false
        avis.value = 'Votre session a expiré. Reconnectez-vous pour continuer.'
      }
      return r
    }
  }

  return { connecte, identite, avis, verifier, connexion, deconnexion, surveillerExpiration }
})
