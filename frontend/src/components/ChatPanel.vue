<template>
  <div class="chat">
    <div
      v-if="localFile"
      class="file-banner"
    >
      📄 Contexte actif : <code>{{ localFile.path }}</code>
      <button
        class="x"
        aria-label="Retirer le fichier du contexte"
        @click="localFile = null"
      >
        ✕
      </button>
    </div>

    <div
      ref="messagesEl"
      class="messages"
    >
      <div
        v-for="(m, i) in chat.messages"
        :key="i"
        :class="['msg', m.role]"
      >
        <strong>{{ m.role === 'user' ? 'Vous' : 'Olivia' }}</strong>
        <div class="bubble">
          {{ m.content }}
        </div>
        <p
          v-if="m.searchNote"
          class="search-note"
        >
          ⚠️ {{ m.searchNote }}
        </p>
        <details
          v-if="m.sources && m.sources.length"
          class="sources"
        >
          <summary>🌐 {{ m.sources.length }} source{{ m.sources.length > 1 ? 's' : '' }} web</summary>
          <ol>
            <li
              v-for="(s, j) in m.sources"
              :key="j"
            >
              <a
                :href="s.url"
                target="_blank"
                rel="noopener noreferrer"
              >{{ s.title || s.url }}</a>
            </li>
          </ol>
        </details>
      </div>
      <div
        v-if="chat.messages.length === 0"
        class="welcome"
      >
        <img
          :src="logoUrl"
          alt=""
          class="welcome-logo"
        >
        <h2>Bonjour, je suis Olivia</h2>
        <p class="welcome-lead">
          Votre assistante pour le secrétariat de direction. Posez votre demande,
          ou choisissez un exemple pour commencer :
        </p>
        <div class="examples">
          <button
            v-for="(ex, i) in examples"
            :key="i"
            class="example"
            @click="useExample(ex)"
          >
            {{ ex }}
          </button>
        </div>
        <p class="tip">
          <small>💡 Astuce : sélectionnez un document à gauche pour que je l'utilise dans ma réponse.</small>
        </p>
      </div>
      <div
        v-if="chat.isSearching"
        class="searching"
        aria-live="polite"
      >
        🌐 Recherche sur le web…
      </div>
      <div
        v-if="chat.isStreaming && !chat.isSearching
          && (chat.messages[chat.messages.length-1]?.content || '') === ''"
        class="typing"
      >
        <span /><span /><span />
      </div>
    </div>

    <div class="composer">
      <textarea
        v-model="input"
        placeholder="Écrivez votre demande à Olivia…"
        :disabled="chat.isStreaming"
        rows="3"
        @keydown.enter.exact.prevent="send"
      />
      <div class="actions">
        <button
          class="toggle"
          :class="{ on: webSearch }"
          :aria-pressed="webSearch"
          :disabled="chat.isStreaming"
          title="Chercher sur le web avant de répondre, et citer les sources"
          @click="webSearch = !webSearch"
        >
          🌐 Recherche web
        </button>
        <button
          v-if="chat.isStreaming"
          @click="chat.stop()"
        >
          ⏸ Stop
        </button>
        <button
          v-else
          :disabled="!input.trim()"
          @click="send"
        >
          ▶ Envoyer
        </button>
      </div>
      <p
        v-if="webSearch"
        class="web-hint"
      >
        Olivia consultera le web avant de répondre, et indiquera ses sources.
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat.js'
import logoUrl from '../assets/logo-mark.png'

const props = defineProps({ fileContext: { type: Object, default: null } })
const chat = useChatStore()
const input = ref('')
const messagesEl = ref(null)
const localFile = ref(null)
// Recherche web : choix explicite de l'utilisatrice, conservé d'un message à l'autre.
const webSearch = ref(false)

// Exemples concrets pour une assistante de direction en lycée
const examples = [
  'Rédige un courriel aux parents pour annoncer le prochain conseil de classe.',
  'Prépare un ordre du jour pour une réunion d\'équipe pédagogique.',
  'Reformule ce texte de façon plus professionnelle et concise.',
  'Fais un compte-rendu synthétique à partir de mes notes.',
]

function useExample(text) {
  chat.send(text, localFile.value, webSearch.value)
}

watch(() => props.fileContext, (v) => { localFile.value = v })

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

function scrollToBottom(smooth = false) {
  const el = messagesEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth && !prefersReduced ? 'smooth' : 'auto' })
}

// Nouveau message ajouté → défilement doux
watch(() => chat.messages.length, async () => {
  await nextTick()
  scrollToBottom(true)
})

// Contenu du dernier message qui grandit (streaming) → suivi instantané
watch(() => chat.messages[chat.messages.length - 1]?.content, async () => {
  await nextTick()
  scrollToBottom(false)
})

function send() {
  if (!input.value.trim()) return
  chat.send(input.value, localFile.value, webSearch.value)
  input.value = ''
}
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; }
.file-banner { padding: 8px 16px; background: var(--panel-2); display: flex;
               align-items: center; gap: 8px; font-size: 13px; }
.file-banner code { color: var(--accent); }
.x { background: transparent; padding: 2px 8px; font-size: 12px; }
.messages { flex: 1; overflow-y: auto; padding: 16px; }
.msg { margin-bottom: 16px; animation: msg-in 0.22s ease; }
@keyframes msg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.msg strong { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
.bubble { padding: 10px 14px; border-radius: 8px; white-space: pre-wrap;
          word-wrap: break-word; line-height: 1.5; }
.msg.user .bubble { background: var(--user); margin-left: auto; max-width: 80%; }
.msg.assistant .bubble { background: var(--assistant); }
.search-note { margin: 6px 0 0; font-size: 12px; color: var(--warn); line-height: 1.4; }
.sources { margin-top: 6px; font-size: 12px; color: var(--muted); }
.sources summary { cursor: pointer; padding: 2px 0; }
.sources ol { margin: 6px 0 0; padding-left: 22px; }
.sources li { margin-bottom: 4px; line-height: 1.4; }
.sources a { color: var(--accent); }
.searching { font-size: 13px; color: var(--muted); padding: 4px 0; }
.welcome { text-align: center; color: var(--muted); padding: 32px 20px; max-width: 620px; margin: 0 auto; }
.welcome-logo { width: 84px; height: 84px; border-radius: 16px; background: #fff; padding: 6px; }
.welcome h2 { color: var(--text); font-size: 20px; margin: 8px 0 4px; }
.welcome-lead { line-height: 1.6; margin: 0 0 20px; }
.examples { display: grid; gap: 10px; text-align: left; }
.example {
  background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 14px; font-size: 13px; line-height: 1.4; cursor: pointer; width: 100%;
}
.example:hover { border-color: var(--accent); }
.tip { margin-top: 20px; }
.typing span { display: inline-block; width: 8px; height: 8px;
               background: var(--muted); border-radius: 50%;
               margin-right: 4px; animation: blink 1.4s infinite; }
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }
.composer { padding: 12px 16px; background: var(--panel); border-top: 1px solid var(--border); }
.composer textarea { width: 100%; resize: vertical; font-family: inherit; }
.composer .actions { display: flex; justify-content: space-between; align-items: center;
                     gap: 8px; margin-top: 8px; }
.composer .toggle {
  background: var(--panel-2); color: var(--muted);
  border: 1px solid var(--border); font-size: 13px;
}
.composer .toggle:hover:not(:disabled) { border-color: var(--accent); color: var(--text); }
.composer .toggle.on { background: var(--accent); color: #fff; border-color: var(--accent); }
.web-hint { margin: 6px 0 0; font-size: 12px; color: var(--muted); }
</style>
