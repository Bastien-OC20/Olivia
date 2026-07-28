<template>
  <div class="layout">
    <a
      href="#contenu"
      class="skip-link"
    >Aller au contenu principal</a>

    <header class="topbar">
      <h1 class="brand">
        <img
          :src="logoUrl"
          alt=""
          class="brand-logo"
        >
        <span class="brand-name">Olivia</span>
        <span class="brand-sub">votre assistante</span>
      </h1>

      <div
        v-if="!simple"
        class="device"
        role="group"
        aria-label="Puissance de calcul"
      >
        <span
          id="device-lbl"
          class="device-label"
        >Puissance</span>
        <div
          class="seg"
          aria-labelledby="device-lbl"
        >
          <button
            :class="{ on: device === 'gpu' }"
            :aria-pressed="device === 'gpu'"
            title="Utilise la carte graphique — réponses plus rapides"
            @click="setDevice('gpu')"
          >
            ⚡ Rapide
          </button>
          <button
            :class="{ on: device === 'cpu' }"
            :aria-pressed="device === 'cpu'"
            title="Sans carte graphique — compatible avec tout ordinateur"
            @click="setDevice('cpu')"
          >
            🧩 Standard
          </button>
        </div>
      </div>

      <ModelPicker v-if="!simple" />
      <button
        class="ghost"
        aria-label="Ouvrir les paramètres"
        @click="settings.show()"
      >
        ⚙️ Paramètres
      </button>
      <button
        class="ghost"
        :disabled="chat.messages.length === 0"
        aria-label="Effacer la conversation"
        @click="chat.clear()"
      >
        Effacer
      </button>
    </header>

    <ConnectedTools
      @open-settings="settings.show()"
      @open-mail="settings.show()"
    />

    <main
      id="contenu"
      class="main"
    >
      <aside
        class="sidebar"
        aria-label="Conversations et documents"
      >
        <div
          class="side-tabs"
          role="tablist"
          aria-label="Sections de la barre latérale"
        >
          <button
            v-for="t in sideTabs"
            :id="`tab-${t.id}`"
            :key="t.id"
            role="tab"
            type="button"
            :class="{ on: sideTab === t.id }"
            :aria-selected="sideTab === t.id"
            :aria-controls="`panel-${t.id}`"
            :tabindex="sideTab === t.id ? 0 : -1"
            @click="sideTab = t.id"
            @keydown="onTabKeydown"
          >
            {{ t.label }}
          </button>
        </div>

        <div
          v-show="sideTab === 'conversations'"
          id="panel-conversations"
          role="tabpanel"
          aria-labelledby="tab-conversations"
          tabindex="0"
        >
          <ConversationList />
        </div>
        <div
          v-show="sideTab === 'documents'"
          id="panel-documents"
          role="tabpanel"
          aria-labelledby="tab-documents"
          tabindex="0"
        >
          <FileExplorer />
        </div>
      </aside>
      <section
        class="content"
        aria-label="Conversation"
      >
        <ChatPanel />
      </section>
    </main>

    <SettingsMenu ref="settingsMenu" />
    <ConsentBanner @open-privacy="openPrivacy" />
  </div>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue'
import { useChatStore } from './stores/chat.js'
import { useSettingsStore } from './stores/settings.js'
import ModelPicker from './components/ModelPicker.vue'
import FileExplorer from './components/FileExplorer.vue'
import ChatPanel from './components/ChatPanel.vue'
import ConversationList from './components/ConversationList.vue'
import SettingsMenu from './components/SettingsMenu.vue'
import ConnectedTools from './components/ConnectedTools.vue'
import ConsentBanner from './components/ConsentBanner.vue'
import logoUrl from './assets/logo-mark.png'

const chat = useChatStore()
const settings = useSettingsStore()
const settingsMenu = ref(null)

const device = computed(() => settings.data.compute_device || 'gpu')
const simple = computed(() => settings.data.simple_mode !== false)

// Barre latérale à deux onglets : conversations et documents.
// Visible dans les deux modes (simple et avancé).
const sideTabs = [
  { id: 'conversations', label: '💬 Conversations' },
  { id: 'documents', label: '📁 Documents' },
]
const sideTab = ref('conversations')

onMounted(async () => {
  await settings.load()
  chat.loadModels()
  chat.loadConversations()
})

// Navigation clavier attendue pour un role="tablist" (flèches, Début, Fin).
function onTabKeydown(e) {
  const keys = ['ArrowLeft', 'ArrowRight', 'Home', 'End']
  if (!keys.includes(e.key)) return
  e.preventDefault()
  const i = sideTabs.findIndex(t => t.id === sideTab.value)
  let next
  if (e.key === 'ArrowLeft') next = (i - 1 + sideTabs.length) % sideTabs.length
  else if (e.key === 'ArrowRight') next = (i + 1) % sideTabs.length
  else if (e.key === 'Home') next = 0
  else next = sideTabs.length - 1
  sideTab.value = sideTabs[next].id
  document.getElementById(`tab-${sideTabs[next].id}`)?.focus()
}

async function setDevice(d) {
  if (settings.data.compute_device === d) return
  settings.data.compute_device = d
  await settings.save({ compute_device: d })
}

function openPrivacy() {
  settings.show()
  settingsMenu.value?.goToPrivacy?.()
}
</script>

<style scoped>
.layout { display: flex; flex-direction: column; height: 100vh; }
.topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 12px 20px; background: var(--panel);
  border-bottom: 1px solid var(--border);
}
.brand { margin: 0; flex: 1; display: flex; align-items: center; gap: 10px; }
.brand-logo { width: 30px; height: 30px; border-radius: 6px; background: #fff; padding: 1px; }
.brand-sub { align-self: flex-end; padding-bottom: 3px; }
.brand-name { font-size: 20px; font-weight: 700; letter-spacing: 0.2px; }
.brand-sub { font-size: 12px; color: var(--muted); font-weight: 400; }
.topbar .ghost { background: var(--panel-2); color: var(--text); }

.device { display: flex; align-items: center; gap: 8px; }
.device-label { font-size: 12px; color: var(--muted); }
.seg { display: inline-flex; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
.seg button {
  background: var(--panel-2); color: var(--muted); border: none;
  padding: 6px 12px; font-size: 13px; border-radius: 0;
}
.seg button.on { background: var(--accent); color: #fff; }

.main { display: flex; flex: 1; overflow: hidden; }
.sidebar {
  width: 320px; border-right: 1px solid var(--border);
  overflow-y: auto; display: flex; flex-direction: column;
}
.side-tabs {
  display: flex; gap: 4px; padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  position: sticky; top: 0; background: var(--bg); z-index: 1;
}
.side-tabs button {
  flex: 1; background: var(--panel-2); color: var(--muted);
  padding: 7px 8px; font-size: 13px;
}
.side-tabs button.on { background: var(--accent); color: #fff; }
.sidebar [role="tabpanel"] { outline-offset: -2px; }
.content { flex: 1; overflow: hidden; }
</style>
