<template>
  <div class="tools-bar">
    <template v-if="enabledConnectors.length">
      <button
        v-for="c in enabledConnectors"
        :key="c.id"
        type="button"
        class="pastille outil"
        :title="chipTitle(c)"
        :aria-label="chipAriaLabel(c)"
        @click="onChipClick(c)"
      >
        <Icone
          v-if="ICONES_CONNECTEURS[c.id]"
          :nom="ICONES_CONNECTEURS[c.id]"
          :taille="14"
        />
        <span
          v-else
          class="emoji"
          aria-hidden="true"
        >{{ c.icon }}</span>
        <span class="libelle">{{ c.label }}</span>
        <span
          class="dot"
          :style="{ background: dotColor(c.status) }"
          aria-hidden="true"
        />
        <span
          v-if="c.id === 'imap' && mail.enabled && mail.count > 0"
          class="badge"
          aria-hidden="true"
        >{{ mail.count > 99 ? '99+' : mail.count }}</span>
      </button>
    </template>

    <!-- Aucun outil connecté : rien en mode simple (rien à faire pour
         l'utilisatrice) ; en mode avancé, un accès discret aux Paramètres. -->
    <button
      v-else-if="!simple"
      type="button"
      class="pastille outil connecter"
      @click="emit('open-settings')"
    >
      <Icone
        nom="plus"
        :taille="14"
      />
      <span class="libelle">Connecter un outil</span>
    </button>

    <!-- Zone accessible : annonce les e-mails non lus aux lecteurs d'écran -->
    <div
      class="sr-only"
      aria-live="polite"
    >
      {{ mailSrText }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import Icone from './Icone.vue'

defineProps({
  // Mode simple : rien n'est proposé tant qu'aucun outil n'est connecté.
  simple: { type: Boolean, default: true },
})

const emit = defineEmits(['open-settings', 'open-mail'])

// Icône au trait des connecteurs connus ; les autres gardent l'emoji fourni
// par le serveur (c.icon).
const ICONES_CONNECTEURS = {
  imap: 'mail',
  calendar_ics: 'calendrier',
  obsidian: 'livre',
  notion: 'document',
}

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
      return 'var(--ok)'
    case 'misconfigured':
    case 'scaffold':
      return 'var(--avert)'
    default:
      return 'var(--discret)'
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
/* Dans la barre du haut : pastilles compactes. Le remplissage vertical laisse
   la place au badge, qui déborde de sa pastille (la zone défile sinon). */
.tools-bar {
  display: flex;
  gap: var(--e-2);
  align-items: center;
  min-width: 0;
  padding: 8px 10px 8px 2px;
  overflow-x: auto;
}

.outil {
  position: relative;
  flex-shrink: 0;
  gap: 6px;
  padding: 4px 10px;
  font-size: var(--t-xs);
  white-space: nowrap;
  color: var(--texte);
  cursor: pointer;
}
.outil:hover {
  background: var(--surface-3);
  border-color: var(--bordure-forte);
}
.outil .icone { color: var(--discret); flex-shrink: 0; }
.connecter { color: var(--discret); border-style: dashed; }
.connecter:hover { color: var(--texte); }

.emoji { font-size: var(--t-s); line-height: 1; }
.libelle { line-height: 1.2; }

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* Nombre d'e-mails non lus. --fond sur --avert : lisible dans les deux thèmes
   (texte sombre sur ambre clair, texte clair sur ambre foncé). */
.badge {
  position: absolute;
  top: -7px;
  right: -8px;
  min-width: 18px;
  background: var(--avert);
  color: var(--fond);
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
  text-align: center;
  padding: 3px 5px;
  border-radius: var(--r-rond);
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

/* Écran étroit : seules les icônes restent (le nom accessible est porté par
   aria-label sur chaque pastille). */
@media (max-width: 1100px) {
  .outil:not(.connecter) .libelle { display: none; }
}
</style>
