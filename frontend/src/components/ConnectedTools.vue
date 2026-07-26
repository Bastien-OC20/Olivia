<template>
  <div class="tools-bar">
    <template v-if="enabledConnectors.length">
      <button
        v-for="c in enabledConnectors"
        :key="c.id"
        type="button"
        class="chip"
        :title="chipTitle(c)"
        :aria-label="chipAriaLabel(c)"
        @click="onChipClick(c)"
      >
        <span
          class="emoji"
          aria-hidden="true"
        >{{ c.icon }}</span>
        <span class="label">{{ c.label }}</span>
        <span
          class="dot"
          :style="{ background: dotColor(c.status) }"
          aria-hidden="true"
        />
        <span
          v-if="c.id === 'imap' && mail.enabled && mail.count > 0"
          class="badge"
          aria-hidden="true"
        >
          🔔{{ mail.count > 99 ? '99+' : mail.count }}
        </span>
      </button>
    </template>

    <div
      v-else
      class="empty"
    >
      <span>Aucun outil connecté</span>
      <button
        type="button"
        class="configure-btn"
        @click="emit('open-settings')"
      >
        <span aria-hidden="true">⚙️</span> Configurer
      </button>
    </div>

    <!-- Zone accessible : annonce les e-mails non lus aux lecteurs d'écran -->
    <div
      class="sr-only"
      aria-live="polite"
    >
      {{ mailSrText }}
    </div>

    <button
      type="button"
      class="settings-btn"
      aria-label="Ouvrir les paramètres des connecteurs"
      title="Paramètres"
      @click="emit('open-settings')"
    >
      <span aria-hidden="true">⚙️</span>
    </button>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'

const emit = defineEmits(['open-settings', 'open-mail'])

const connectors = ref([])
const mail = ref({ enabled: false, count: 0, label: '', error: null })

let mailTimer = null

const enabledConnectors = computed(() => connectors.value.filter((c) => c.enabled))

const mailSrText = computed(() => {
  if (mail.value.error) {
    return `Erreur de connexion à la boîte mail : ${mail.value.error}`
  }
  if (mail.value.enabled && mail.value.count > 0) {
    const boxLabel = mail.value.label || 'Boîte pro'
    return `${mail.value.count} e-mail${mail.value.count > 1 ? 's' : ''} non lu${mail.value.count > 1 ? 's' : ''} dans ${boxLabel}`
  }
  return ''
})

function statusText(status) {
  switch (status) {
    case 'connected':
      return 'connecté'
    case 'idle':
      return 'inactif'
    case 'misconfigured':
      return 'mal configuré'
    case 'scaffold':
      return 'à brancher'
    default:
      return status || 'inconnu'
  }
}

function dotColor(status) {
  switch (status) {
    case 'connected':
      return '#22c55e'
    case 'idle':
      return 'var(--muted)'
    case 'misconfigured':
      return 'var(--warn)'
    case 'scaffold':
      return 'var(--warn)'
    default:
      return 'var(--muted)'
  }
}

function chipTitle(c) {
  return c.detail || statusText(c.status)
}

function chipAriaLabel(c) {
  let label = `${c.label}, ${statusText(c.status)}`
  if (c.id === 'imap' && mail.value.enabled && mail.value.count > 0) {
    label += `, ${mail.value.count} e-mail${mail.value.count > 1 ? 's' : ''} non lu${mail.value.count > 1 ? 's' : ''}`
  }
  return label
}

function onChipClick(c) {
  emit('open-settings')
  if (c.id === 'imap') {
    emit('open-mail')
  }
}

async function fetchStatus() {
  try {
    const r = await fetch('/api/connectors/status')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    connectors.value = Array.isArray(data.connectors) ? data.connectors : []
  } catch (e) {
    console.error('ConnectedTools: échec du chargement du statut des connecteurs', e)
  }
}

async function fetchMailUnread() {
  try {
    const r = await fetch('/api/connectors/mail/unread')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    mail.value = {
      enabled: !!data.enabled,
      count: Number(data.count) || 0,
      label: data.label || '',
      error: data.error || null,
    }
  } catch (e) {
    console.error('ConnectedTools: échec du chargement des e-mails non lus', e)
  }
}

onMounted(() => {
  fetchStatus()
  fetchMailUnread()
  mailTimer = setInterval(fetchMailUnread, 60000)
})

onUnmounted(() => {
  if (mailTimer) clearInterval(mailTimer)
})
</script>

<style scoped>
.tools-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 8px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--panel);
  overflow-x: auto;
}

.chip {
  position: relative;
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
  color: var(--text);
  white-space: nowrap;
  cursor: pointer;
}

.chip:hover {
  border-color: var(--accent);
}

.chip .emoji {
  font-size: 14px;
  line-height: 1;
}

.chip .label {
  line-height: 1;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.badge {
  position: absolute;
  top: -7px;
  right: -8px;
  background: var(--warn);
  color: #1a1300;
  font-size: 10px;
  font-weight: 600;
  line-height: 1;
  padding: 3px 5px;
  border-radius: 10px;
  white-space: nowrap;
  animation: badge-pulse 2s ease-in-out infinite;
}

@media (prefers-reduced-motion: reduce) {
  .badge {
    animation: none;
  }
}

@keyframes badge-pulse {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(1.12); }
}

.empty {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13px;
  color: var(--muted);
  flex-shrink: 0;
}

.configure-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  color: var(--text);
}

.configure-btn:hover {
  border-color: var(--accent);
}

.settings-btn {
  margin-left: auto;
  flex-shrink: 0;
  background: transparent;
  border: none;
  font-size: 16px;
  padding: 4px 6px;
  color: var(--muted);
  cursor: pointer;
}

.settings-btn:hover {
  color: var(--text);
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
