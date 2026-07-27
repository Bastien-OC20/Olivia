<template>
  <div class="bubble-body">
    <details
      v-if="reasoning"
      class="reasoning"
    >
      <summary>💭 Raisonnement</summary>
      <p class="reasoning-text">
        {{ reasoning }}
      </p>
    </details>

    <!-- Le HTML injecté est systématiquement passé par DOMPurify (voir toHtml).
         Le Markdown vient d'un modèle, éventuellement nourri de pages web :
         il ne doit jamais être affiché sans assainissement. -->
    <!-- eslint-disable vue/no-v-html -->
    <div
      class="markdown"
      v-html="html"
    />
    <!-- eslint-enable vue/no-v-html -->
  </div>
</template>

<script setup>
import { ref, watch, onBeforeUnmount } from 'vue'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

// Les liens s'ouvrent dans un nouvel onglet, sans donner accès à la page d'origine.
DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  if (node.tagName === 'A') {
    node.setAttribute('target', '_blank')
    node.setAttribute('rel', 'noopener noreferrer')
  }
})

marked.setOptions({ gfm: true, breaks: true })

// Pendant le streaming, re-parser le Markdown à chaque token coûte cher sur une
// réponse longue : on limite le rendu à un passage toutes les 100 ms.
const THROTTLE_MS = 100

const props = defineProps({
  content: { type: String, default: '' },
  streaming: { type: Boolean, default: false },
})

const html = ref('')
const reasoning = ref('')
let timer = null

/**
 * Sépare le bloc de raisonnement (`<think>…</think>`, émis par les modèles
 * qwen3) du texte utile. Gère aussi le bloc encore ouvert pendant le streaming.
 */
function splitThinking(raw) {
  let raisonnement = ''
  let body = raw.replace(/<think>([\s\S]*?)<\/think>/gi, (_, inner) => {
    raisonnement += inner
    return ''
  })
  const open = body.search(/<think>/i)
  if (open !== -1) {
    raisonnement += body.slice(open + '<think>'.length)
    body = body.slice(0, open)
  }
  return { think: raisonnement.trim(), body: body.trim() }
}

// Olivia promet qu'aucune donnée ne sort de la machine. Or une réponse nourrie
// par la recherche web peut contenir `![](http://exemple/pixel.png)` : le
// navigateur irait alors chercher cette ressource, révélant à un tiers que la
// réponse a été lue. On interdit donc toute balise qui déclenche une requête
// réseau — le texte et les liens (que l'utilisatrice clique en connaissance de
// cause) suffisent largement dans une conversation.
const REMOTE_TAGS = ['img', 'iframe', 'video', 'audio', 'source', 'embed', 'object']

function toHtml(markdown) {
  return DOMPurify.sanitize(marked.parse(markdown, { async: false }),
                            { FORBID_TAGS: REMOTE_TAGS })
}

function render() {
  const { think, body } = splitThinking(props.content || '')
  reasoning.value = think
  html.value = toHtml(body)
}

function clearTimer() {
  if (timer) { clearTimeout(timer); timer = null }
}

watch(
  () => [props.content, props.streaming],
  () => {
    if (!props.streaming) {
      // Fin du streaming (ou message déjà complet) : rendu final immédiat.
      clearTimer()
      render()
      return
    }
    if (timer) return
    timer = setTimeout(() => { timer = null; render() }, THROTTLE_MS)
  },
  { immediate: true },
)

onBeforeUnmount(clearTimer)
</script>

<style scoped>
.bubble-body { line-height: 1.6; word-wrap: break-word; overflow-wrap: anywhere; }

.reasoning {
  margin: 0 0 10px;
  font-size: 12px;
  color: var(--muted);
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 6px 10px;
}
.reasoning summary { cursor: pointer; }
.reasoning-text { margin: 8px 0 0; white-space: pre-wrap; line-height: 1.5; }

/* Rendu Markdown — styles non « scopés » car le HTML est injecté via v-html. */
.markdown :deep(*:first-child) { margin-top: 0; }
.markdown :deep(*:last-child) { margin-bottom: 0; }
.markdown :deep(p) { margin: 0 0 10px; }
.markdown :deep(h1),
.markdown :deep(h2),
.markdown :deep(h3),
.markdown :deep(h4) { margin: 18px 0 8px; line-height: 1.3; }
.markdown :deep(h1) { font-size: 20px; }
.markdown :deep(h2) { font-size: 18px; }
.markdown :deep(h3) { font-size: 16px; }
.markdown :deep(h4) { font-size: 14px; }
.markdown :deep(ul),
.markdown :deep(ol) { margin: 0 0 10px; padding-left: 24px; }
.markdown :deep(li) { margin: 3px 0; }
.markdown :deep(a) { color: var(--accent); }
.markdown :deep(a:hover) { text-decoration: underline; }
.markdown :deep(code) {
  background: rgba(255, 255, 255, 0.08);
  padding: 1px 5px;
  border-radius: 3px;
  font-family: Consolas, Monaco, monospace;
  font-size: 0.92em;
}
.markdown :deep(pre) {
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin: 0 0 10px;
}
.markdown :deep(pre code) { background: transparent; padding: 0; }
.markdown :deep(blockquote) {
  margin: 0 0 10px;
  padding: 2px 0 2px 12px;
  border-left: 3px solid var(--border);
  color: var(--muted);
}
.markdown :deep(table) {
  border-collapse: collapse;
  margin: 0 0 10px;
  font-size: 13px;
  display: block;
  overflow-x: auto;
  max-width: 100%;
}
.markdown :deep(th),
.markdown :deep(td) { border: 1px solid var(--border); padding: 6px 10px; text-align: left; }
.markdown :deep(th) { background: var(--panel-2); }
.markdown :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
</style>
