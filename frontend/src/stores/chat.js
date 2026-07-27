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

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const isSearching = ref(false)
  const currentModel = ref('')
  const availableModels = ref([])
  const abortController = ref(null)

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

  async function send(userMessage, fileContext = null, useWebSearch = false) {
    if (isStreaming.value || !currentModel.value) return
    messages.value.push({ role: 'user', content: userMessage })
    isStreaming.value = true
    const assistantMsg = { role: 'assistant', content: '', sources: [], searchNote: '' }
    messages.value.push(assistantMsg)
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
    }
  }

  function stop() {
    if (abortController.value) abortController.value.abort()
  }

  function clear() { messages.value = [] }

  return { messages, isStreaming, isSearching, currentModel, availableModels,
           loadModels, send, stop, clear }
})
