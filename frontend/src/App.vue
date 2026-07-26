<template>
  <div class="layout">
    <a
      href="#contenu"
      class="skip-link"
    >Aller au contenu principal</a>

    <header class="topbar">
      <h1 class="brand">
        <span
          class="brand-mark"
          aria-hidden="true"
        >🌷</span>
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
        aria-label="Explorateur de fichiers"
      >
        <FileExplorer @file-selected="onFileSelected" />
      </aside>
      <section
        class="content"
        aria-label="Conversation"
      >
        <ChatPanel :file-context="currentFile" />
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
import SettingsMenu from './components/SettingsMenu.vue'
import ConnectedTools from './components/ConnectedTools.vue'
import ConsentBanner from './components/ConsentBanner.vue'

const chat = useChatStore()
const settings = useSettingsStore()
const currentFile = ref(null)
const settingsMenu = ref(null)

const device = computed(() => settings.data.compute_device || 'gpu')
const simple = computed(() => settings.data.simple_mode !== false)

onMounted(async () => {
  await settings.load()
  chat.loadModels()
})

function onFileSelected(file) { currentFile.value = file }

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
.brand { margin: 0; flex: 1; display: flex; align-items: baseline; gap: 8px; }
.brand-mark { font-size: 18px; }
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
.sidebar { width: 320px; border-right: 1px solid var(--border); overflow-y: auto; }
.content { flex: 1; overflow: hidden; }
</style>
