import { defineStore } from 'pinia'
import { ref } from 'vue'

// Recherche web : nombre de résultats injectés et longueur max de la requête
// envoyée au moteur (une demande de chat peut être un paragraphe entier).
const WEB_SEARCH_LIMIT = 5
const WEB_QUERY_MAX = 300

async function fetchWebResults(query, signal) {
  const r = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.slice(0, WEB_QUERY_MAX), limit: WEB_SEARCH_LIMIT }),
    signal
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
  return data?.results || []
}

/** Reformule la demande de l'utilisateur en y joignant les résultats web numérotés. */
function withWebContext(question, results) {
  const today = new Date().toLocaleDateString('fr-FR',
    { day: 'numeric', month: 'long', year: 'numeric' })
  const sources = results.map((r, i) =>
    `[${i + 1}] ${r.title || r.url}\n${r.url}\n${r.snippet || ''}`.trim()).join('\n\n')
  return `Résultats d'une recherche web effectuée le ${today} :\n\n${sources}\n\n` +
    'Appuie-toi sur ces résultats pour répondre à la demande ci-dessous et cite tes ' +
    'sources par leur numéro entre crochets ([1], [2]…). Si les résultats ne ' +
    "permettent pas de répondre, dis-le simplement plutôt que d'inventer.\n\n" +
    `Demande : ${question}`
}

/** Titre par défaut d'une conversation : début de la première demande. */
function deriveTitle(msgs) {
  const first = msgs.find((m) => m.role === 'user')
  const raw = (first?.content || '').replace(/\s+/g, ' ').trim()
  if (!raw) return 'Nouvelle conversation'
  return raw.length > 60 ? `${raw.slice(0, 60)}…` : raw
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const isSearching = ref(false)
  const currentModel = ref('')
  const availableModels = ref([])
  const abortController = ref(null)

  // Historique des conversations (persistées côté backend).
  const conversations = ref([])
  const currentId = ref(null)
  // Vrai si le backend ne sait pas gérer l'historique : l'interface le signale
  // sans se casser (les routes peuvent être absentes d'une ancienne version).
  const historyUnavailable = ref(false)

  async function loadModels() {
    try {
      const r = await fetch('/api/models')
      const data = await r.json()
      availableModels.value = data.models || []
      if (availableModels.value.length && !currentModel.value) {
        currentModel.value = availableModels.value[0].name
      }
    } catch (e) {
      console.error('Impossible de charger les modèles :', e)
    }
  }

  // ---------- Historique des conversations ----------

  /** Ne conserve que les champs utiles (dont sources / searchNote, qui doivent
   *  survivre à un rechargement de page). */
  function serialize(msgs) {
    return msgs.map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources || [],
      searchNote: m.searchNote || '',
    }))
  }

  async function loadConversations() {
    try {
      const r = await fetch('/api/conversations')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      conversations.value = Array.isArray(data) ? data : (data.conversations || [])
      historyUnavailable.value = false
    } catch (e) {
      conversations.value = []
      historyUnavailable.value = true
      console.warn('Historique des conversations indisponible :', e.message)
    }
  }

  async function openConversation(id) {
    if (isStreaming.value) stop()
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      messages.value = (data.messages || []).map((m) => ({
        role: m.role,
        content: m.content || '',
        sources: m.sources || [],
        searchNote: m.searchNote || '',
      }))
      currentId.value = data.id ?? id
      historyUnavailable.value = false
    } catch (e) {
      historyUnavailable.value = true
      console.warn('Ouverture de la conversation impossible :', e.message)
    }
  }

  /** Repart d'une conversation vierge. Rien n'est envoyé au backend tant que
   *  le premier échange n'est pas terminé : une conversation vide ne crée
   *  aucune entrée dans l'historique. */
  function newConversation() {
    if (isStreaming.value) stop()
    messages.value = []
    currentId.value = null
  }

  async function renameConversation(id, titre) {
    const title = (titre || '').trim()
    if (!title) return false
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const item = conversations.value.find((c) => c.id === id)
      if (item) item.title = title
      await loadConversations()
      return true
    } catch (e) {
      console.warn('Renommage impossible :', e.message)
      return false
    }
  }

  async function deleteConversation(id) {
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      conversations.value = conversations.value.filter((c) => c.id !== id)
      if (currentId.value === id) newConversation()
      return true
    } catch (e) {
      console.warn('Suppression impossible :', e.message)
      return false
    }
  }

  /** Sauvegarde de la conversation courante. Appelée UNIQUEMENT à la fin du
   *  streaming (ou quand l'utilisatrice interrompt) — jamais à chaque token. */
  async function persist() {
    if (!messages.value.length) return
    const body = { messages: serialize(messages.value) }
    try {
      let r
      if (currentId.value) {
        r = await fetch(`/api/conversations/${encodeURIComponent(currentId.value)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      } else {
        body.title = deriveTitle(messages.value)
        r = await fetch('/api/conversations', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        })
      }
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json().catch(() => null)
      if (data?.id) currentId.value = data.id
      historyUnavailable.value = false
      await loadConversations()
    } catch (e) {
      historyUnavailable.value = true
      console.warn('Sauvegarde de la conversation impossible :', e.message)
    }
  }

  async function send(userMessage, fileContext = null, useWebSearch = false) {
    if (isStreaming.value || !currentModel.value) return
    messages.value.push({ role: 'user', content: userMessage })
    isStreaming.value = true
    messages.value.push({ role: 'assistant', content: '', sources: [], searchNote: '' })
    // On reprend l'élément DEPUIS le tableau : Vue renvoie alors un proxy réactif.
    // Écrire sur l'objet brut d'origine ne déclencherait aucun rendu — la réponse
    // n'apparaîtrait qu'à la toute fin du streaming, et la comparaison
    // « m === assistantMsg » plus bas échouerait (proxy ≠ objet brut).
    const assistantMsg = messages.value[messages.value.length - 1]
    abortController.value = new AbortController()

    // Recherche web (bouton 🌐 du composeur) : on interroge le moteur AVANT
    // d'appeler le modèle, puis on injecte les résultats dans la demande.
    // Un échec du moteur ne bloque pas la réponse : on prévient et on continue.
    let webResults = []
    if (useWebSearch) {
      isSearching.value = true
      try {
        webResults = await fetchWebResults(userMessage, abortController.value.signal)
        assistantMsg.sources = webResults
        if (webResults.length === 0) {
          assistantMsg.searchNote = 'Aucun résultat web trouvé — réponse basée sur les '
            + 'seules connaissances du modèle.'
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          isSearching.value = false
          isStreaming.value = false
          abortController.value = null
          return
        }
        assistantMsg.searchNote = `Recherche web indisponible (${e.message}) — réponse `
          + 'basée sur les seules connaissances du modèle.'
      } finally {
        isSearching.value = false
      }
    }

    // Contexte RAG : si un fichier est sélectionné, on injecte son contenu (tronqué à 8 Ko)
    const ollamaMessages = []
    if (fileContext) {
      ollamaMessages.push({
        role: 'user',
        content: `Voici le contenu du fichier "${fileContext.path}". Réponds en t'appuyant dessus si pertinent :\n\n\`\`\`\n${(fileContext.content || '').slice(0, 8000)}\n\`\`\``
      })
    }
    for (const m of messages.value) {
      if (m === assistantMsg) continue
      ollamaMessages.push({ role: m.role, content: m.content })
    }

    // Les résultats web enrichissent la DERNIÈRE demande (et non le début de
    // l'historique) : les petits modèles locaux suivent mieux un contexte récent.
    if (webResults.length) {
      const last = ollamaMessages[ollamaMessages.length - 1]
      last.content = withWebContext(userMessage, webResults)
    }

    try {
      const r = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: currentModel.value,
          messages: ollamaMessages,
          stream: true
        }),
        signal: abortController.value.signal
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (line.startsWith('data:')) {
            try {
              const payload = JSON.parse(line.slice(5).trim())
              if (payload.message?.content) {
                assistantMsg.content += payload.message.content
              }
              if (payload.done) {
                isStreaming.value = false
                abortController.value = null
                return
              }
            } catch { /* skip */ }
          }
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        assistantMsg.content += `\n\n[Erreur : ${e.message}]`
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
      // Sauvegarde en fin de streaming, y compris après un « Stop ».
      await persist()
    }
  }

  function stop() {
    if (abortController.value) abortController.value.abort()
  }

  /** Vide l'affichage. La conversation déjà enregistrée reste dans l'historique :
   *  on se détache simplement d'elle (équivalent d'une nouvelle conversation). */
  function clear() { newConversation() }

  return { messages, isStreaming, isSearching, currentModel, availableModels,
           conversations, currentId, historyUnavailable,
           loadModels, send, stop, clear,
           loadConversations, openConversation, newConversation,
           renameConversation, deleteConversation }
})
