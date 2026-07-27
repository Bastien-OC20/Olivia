<template>
  <div class="conversations">
    <button
      class="new-conv"
      @click="chat.newConversation()"
    >
      ＋ Nouvelle conversation
    </button>

    <p
      v-if="chat.historyUnavailable"
      class="unavailable"
      aria-live="polite"
    >
      ⚠️ L'historique n'est pas disponible pour le moment. Vos échanges en cours
      restent affichés mais ne seront pas enregistrés.
    </p>

    <ul
      class="conv-list"
      aria-label="Conversations enregistrées"
    >
      <li
        v-for="c in chat.conversations"
        :key="c.id"
        :class="{ active: c.id === chat.currentId }"
      >
        <template v-if="renamingId === c.id">
          <label
            :for="`rename-${c.id}`"
            class="sr-only"
          >Nouveau titre de la conversation</label>
          <input
            :id="`rename-${c.id}`"
            ref="renameInput"
            v-model="renameText"
            class="rename-input"
            @keydown.enter.prevent="confirmRename(c.id)"
            @keydown.esc.prevent="cancelRename"
            @blur="confirmRename(c.id)"
          >
        </template>
        <template v-else>
          <button
            class="conv-open"
            :aria-current="c.id === chat.currentId ? 'true' : undefined"
            @click="chat.openConversation(c.id)"
          >
            <span class="conv-title">{{ c.title || 'Sans titre' }}</span>
            <span class="conv-meta">
              {{ relativeDate(c.updated_at) }}
              <template v-if="c.message_count">· {{ c.message_count }} message{{ c.message_count > 1 ? 's' : '' }}</template>
            </span>
          </button>
          <span class="conv-actions">
            <button
              class="icon"
              :aria-label="`Renommer la conversation « ${c.title || 'Sans titre'} »`"
              @click="startRename(c)"
            >
              ✏️
            </button>
            <button
              class="icon"
              :aria-label="`Supprimer la conversation « ${c.title || 'Sans titre'} »`"
              @click="remove(c)"
            >
              🗑
            </button>
          </span>
        </template>
      </li>
      <li
        v-if="chat.conversations.length === 0 && !chat.historyUnavailable"
        class="empty"
      >
        Aucune conversation enregistrée pour l'instant.
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, nextTick } from 'vue'
import { useChatStore } from '../stores/chat.js'

const chat = useChatStore()
const renamingId = ref(null)
const renameText = ref('')
const renameInput = ref(null)

const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })
const UNITS = [
  ['year', 31536000],
  ['month', 2592000],
  ['week', 604800],
  ['day', 86400],
  ['hour', 3600],
  ['minute', 60],
]

/** Date relative en français : « il y a 5 minutes », « hier »… */
function relativeDate(ts) {
  if (!ts) return ''
  const diff = Number(ts) * 1000 - Date.now()
  const seconds = diff / 1000
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit)
  }
  return "à l'instant"
}

async function startRename(c) {
  renamingId.value = c.id
  renameText.value = c.title || ''
  await nextTick()
  const el = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  el?.focus()
  el?.select()
}

function cancelRename() {
  renamingId.value = null
  renameText.value = ''
}

async function confirmRename(id) {
  if (renamingId.value !== id) return
  const title = renameText.value.trim()
  renamingId.value = null
  if (!title) return
  const ok = await chat.renameConversation(id, title)
  if (!ok) alert("Le renommage n'a pas pu être enregistré.")
}

async function remove(c) {
  const label = c.title || 'Sans titre'
  if (!confirm(`Supprimer définitivement la conversation « ${label} » ?`)) return
  const ok = await chat.deleteConversation(c.id)
  if (!ok) alert("La suppression n'a pas pu être effectuée.")
}
</script>

<style scoped>
.conversations { padding: 12px; }
.new-conv { width: 100%; font-size: 13px; }
.unavailable {
  font-size: 12px; line-height: 1.5; color: var(--warn);
  background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 6px; padding: 8px 10px; margin: 10px 0 0;
}
.conv-list { list-style: none; padding: 0; margin: 10px 0 0; }
.conv-list li {
  display: flex; align-items: center; gap: 4px;
  border-radius: 6px; padding: 2px 4px 2px 0;
}
.conv-list li:hover { background: var(--panel-2); }
.conv-list li.active { background: var(--panel-2); box-shadow: inset 2px 0 0 var(--accent); }
.conv-open {
  flex: 1; min-width: 0; text-align: left;
  background: transparent; color: var(--text);
  padding: 8px 10px; font-size: 13px; border-radius: 6px;
}
.conv-open:hover { opacity: 1; }
.conv-title {
  display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.conv-meta { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
.conv-actions { display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s ease; }
.conv-list li:hover .conv-actions,
.conv-list li:focus-within .conv-actions { opacity: 1; }
.icon { background: transparent; padding: 4px 6px; font-size: 13px; line-height: 1; }
.rename-input { font-size: 13px; padding: 6px 8px; }
.empty { color: var(--muted); font-size: 12px; padding: 10px 4px; line-height: 1.5; }
.empty:hover { background: transparent; }
</style>
