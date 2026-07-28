<template>
  <div class="chat">
    <div
      v-if="chat.fileContextPlan.length"
      class="file-banner"
      aria-live="polite"
    >
      <div class="file-banner-head">
        <span>
          📄 {{ chat.fileContextPlan.length }} document{{ chat.fileContextPlan.length > 1 ? 's' : '' }}
          dans la conversation
        </span>
        <button
          class="x"
          @click="chat.clearFileContexts()"
        >
          Tout retirer
        </button>
      </div>
      <ul class="file-list">
        <li
          v-for="doc in chat.fileContextPlan"
          :key="doc.path"
        >
          <span
            class="file-name"
            :title="doc.path"
          >{{ doc.name }}</span>
          <span
            v-if="doc.truncated"
            class="file-cut"
            :title="`Seuls les ${doc.keptChars} premiers caractères sur ${doc.chars} sont transmis à Olivia.`"
          >
            ⚠️ tronqué
          </span>
          <button
            class="x"
            :aria-label="`Retirer ${doc.name} de la conversation`"
            @click="chat.removeFileContext(doc.path)"
          >
            ✕
          </button>
        </li>
      </ul>
      <p
        v-if="documentsTronques"
        class="file-warn"
      >
        Certains documents sont trop longs : seul leur début est transmis à Olivia.
        Retirez-en pour laisser plus de place aux autres.
      </p>
      <p
        v-if="chat.fileContextNotice"
        class="file-warn"
      >
        {{ chat.fileContextNotice }}
      </p>
    </div>

    <div
      ref="messagesEl"
      class="messages"
    >
      <div class="stream">
        <div
          v-for="(m, i) in chat.messages"
          :key="i"
          :class="['msg', m.role]"
        >
          <strong>{{ m.role === 'user' ? 'Vous' : 'Olivia' }}</strong>
          <div
            v-if="m.role === 'user'"
            class="bubble plain"
          >
            {{ m.content }}
          </div>
          <div
            v-else
            class="bubble"
          >
            <MessageBubble
              :content="m.content"
              :streaming="chat.isStreaming && i === chat.messages.length - 1"
            />
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
            <small>💡 Astuce : ouvrez l'onglet 📁 Documents à gauche pour que j'utilise un fichier dans ma réponse.</small>
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
    </div>

    <div class="composer">
      <div class="composer-inner">
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
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useChatStore } from '../stores/chat.js'
import MessageBubble from './MessageBubble.vue'
import logoUrl from '../assets/logo-mark.png'

const chat = useChatStore()
const input = ref('')
const messagesEl = ref(null)
// Recherche web : choix explicite de l'utilisatrice, conservé d'un message à l'autre.
const webSearch = ref(false)

const documentsTronques = computed(() => chat.fileContextPlan.some((d) => d.truncated))

// Exemples concrets pour une assistante de direction en lycée
const examples = [
  'Rédige un courriel aux parents pour annoncer le prochain conseil de classe.',
  'Prépare un ordre du jour pour une réunion d\'équipe pédagogique.',
  'Reformule ce texte de façon plus professionnelle et concise.',
  'Fais un compte-rendu synthétique à partir de mes notes.',
]

function useExample(text) {
  chat.send(text, webSearch.value)
}

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
  chat.send(input.value, webSearch.value)
  input.value = ''
}
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; }
.file-banner { padding: 8px 16px; background: var(--panel-2); font-size: 13px; }
.file-banner-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.file-list { list-style: none; margin: 6px 0 0; padding: 0; display: flex;
             flex-wrap: wrap; gap: 6px; }
.file-list li {
  display: flex; align-items: center; gap: 6px; background: var(--panel);
  border: 1px solid var(--border); border-radius: 999px; padding: 2px 4px 2px 12px;
  max-width: 100%;
}
.file-name { color: var(--accent); max-width: 240px; overflow: hidden;
             text-overflow: ellipsis; white-space: nowrap; }
.file-cut { color: var(--warn); font-size: 11px; }
.file-warn { margin: 6px 0 0; font-size: 12px; color: var(--warn); line-height: 1.4; }
.x { background: transparent; padding: 2px 8px; font-size: 12px; }
.messages { flex: 1; overflow-y: auto; padding: 16px; }
/* Colonne de lecture centrée (confort de lecture, style Claude Desktop) */
.stream { max-width: 760px; margin: 0 auto; }
.msg { margin-bottom: 20px; animation: msg-in 0.22s ease; }
@keyframes msg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.msg strong { font-size: 12px; color: var(--muted); display: block; margin-bottom: 4px; }
.bubble { padding: 10px 14px; border-radius: 8px;
          word-wrap: break-word; line-height: 1.5; }
/* Message tapé par l'utilisatrice : texte brut, bulle alignée à droite */
.bubble.plain { white-space: pre-wrap; }
.msg.user { display: flex; flex-direction: column; align-items: flex-end; }
.msg.user .bubble { background: var(--user); max-width: 80%; }
/* Réponse d'Olivia : pleine largeur, sans bulle (comme Claude Desktop) */
.msg.assistant .bubble { background: transparent; padding: 2px 0; }
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
.composer-inner { max-width: 760px; margin: 0 auto; }
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
