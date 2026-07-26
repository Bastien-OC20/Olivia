import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
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

  async function send(userMessage, fileContext = null) {
    if (isStreaming.value || !currentModel.value) return
    messages.value.push({ role: 'user', content: userMessage })
    isStreaming.value = true
    const assistantMsg = { role: 'assistant', content: '' }
    messages.value.push(assistantMsg)

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

    abortController.value = new AbortController()
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

  return { messages, isStreaming, currentModel, availableModels,
           loadModels, send, stop, clear }
})
