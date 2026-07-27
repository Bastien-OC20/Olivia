<template>
  <Transition name="fade">
    <div
      v-if="isOpen"
      class="overlay"
      @click.self="close"
      @keydown.esc="close"
    >
      <div
        ref="modalEl"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-picker-title"
      >
        <header>
          <h2 id="folder-picker-title">
            📁 Dossiers accessibles
          </h2>
          <button
            ref="closeBtn"
            class="x"
            aria-label="Fermer la fenêtre de choix de dossier"
            @click="close"
          >
            ✕
          </button>
        </header>

        <div class="body">
          <section aria-label="Dossiers actuellement accessibles">
            <h3>Dossiers actuels</h3>
            <ul class="root-list">
              <li
                v-for="(entry, i) in settings.data.fs_roots"
                :key="entry.path + i"
                class="root-item"
              >
                <span
                  class="root-name"
                  :title="entry.path"
                >{{ entry.label || basename(entry.path) }}</span>
                <button
                  class="ghost small"
                  @click="removeRoot(i)"
                >
                  Retirer
                </button>
              </li>
              <li
                v-if="settings.data.fs_roots.length === 0"
                class="empty"
              >
                Aucun dossier configuré (Documents utilisé par défaut).
              </li>
            </ul>
          </section>

          <section aria-label="Ajouter un dossier">
            <h3>Ajouter un dossier</h3>
            <div class="breadcrumb">
              <button
                class="ghost small"
                :disabled="stack.length === 0"
                @click="goUp"
              >
                ⬆ Remonter
              </button>
              <span
                class="current-path"
                :title="currentPath"
              >{{ currentPath || 'Lecteurs' }}</span>
            </div>
            <p
              v-if="error"
              class="warn"
              aria-live="polite"
            >
              {{ error }}
            </p>
            <p
              v-if="addedMsg"
              class="hint"
              aria-live="polite"
            >
              {{ addedMsg }}
            </p>
            <ul class="folder-list">
              <li
                v-for="f in folders"
                :key="f.path"
                tabindex="0"
                role="button"
                @click="enter(f.path)"
                @keydown.enter="enter(f.path)"
              >
                📂 {{ f.name }}
              </li>
              <li
                v-if="!loading && folders.length === 0"
                class="empty"
              >
                Aucun sous-dossier
              </li>
              <li
                v-if="loading"
                class="empty"
              >
                Chargement…
              </li>
            </ul>
            <div class="pick-row">
              <button
                :disabled="!currentPath || adding"
                @click="choose"
              >
                ✓ Choisir ce dossier
              </button>
            </div>
          </section>
        </div>

        <footer>
          <button
            class="ghost"
            @click="close"
          >
            Fermer
          </button>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'
import { useSettingsStore } from '../stores/settings.js'

const props = defineProps({ isOpen: { type: Boolean, default: false } })
const emit = defineEmits(['close'])
const settings = useSettingsStore()

const currentPath = ref('')
const stack = ref([])
const folders = ref([])
const loading = ref(false)
const error = ref('')
const addedMsg = ref('')
const adding = ref(false)
const modalEl = ref(null)
const closeBtn = ref(null)

function basename(p) {
  return p.split(/[\\/]/).filter(Boolean).pop() || p
}

function samePath(a, b) {
  const norm = (v) => v.replace(/\\/g, '/').replace(/\/+$/, '').toLowerCase()
  return norm(a) === norm(b)
}

watch(() => props.isOpen, async (o) => {
  if (!o) return
  currentPath.value = ''
  stack.value = []
  error.value = ''
  addedMsg.value = ''
  await loadDrives()
  await nextTick()
  closeBtn.value?.focus()
})

async function loadDrives() {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch('/api/fs/drives')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    folders.value = (data.drives || []).map((d) => ({ name: d, path: d }))
  } catch (e) {
    error.value = 'Impossible de lister les lecteurs : ' + e.message
    folders.value = []
  } finally {
    loading.value = false
  }
}

async function browse(path) {
  loading.value = true
  error.value = ''
  try {
    const r = await fetch(`/api/fs/browse?path=${encodeURIComponent(path)}`)
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    currentPath.value = data.path
    folders.value = data.folders || []
  } catch (e) {
    error.value = 'Impossible d\'ouvrir ce dossier : ' + e.message
  } finally {
    loading.value = false
  }
}

function enter(path) {
  stack.value.push(currentPath.value)
  browse(path)
}

async function goUp() {
  if (stack.value.length === 0) return
  const prev = stack.value.pop()
  if (prev === '') {
    currentPath.value = ''
    await loadDrives()
  } else {
    await browse(prev)
  }
}

async function choose() {
  if (!currentPath.value || adding.value) return
  addedMsg.value = ''
  error.value = ''
  if (settings.data.fs_roots.some((e) => samePath(e.path, currentPath.value))) {
    error.value = 'Ce dossier est déjà accessible.'
    return
  }
  adding.value = true
  try {
    const next = [...settings.data.fs_roots, { path: currentPath.value, label: '' }]
    const result = await settings.save({ fs_roots: next })
    if (!result?.ok) throw new Error(result?.error || 'erreur inconnue')
    addedMsg.value = `✓ ${basename(currentPath.value)} ajouté.`
  } catch (e) {
    error.value = 'Ajout impossible : ' + e.message
  } finally {
    adding.value = false
  }
}

async function removeRoot(i) {
  error.value = ''
  addedMsg.value = ''
  const next = settings.data.fs_roots.filter((_, idx) => idx !== i)
  const result = await settings.save({ fs_roots: next })
  if (!result?.ok) error.value = 'Suppression impossible : ' + (result?.error || 'erreur inconnue')
}

function close() { emit('close') }
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  background: var(--panel); width: 520px; max-width: 90vw;
  max-height: 85vh; border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
  border: 1px solid var(--border);
}
header { display: flex; justify-content: space-between; align-items: center;
         padding: 14px 20px; border-bottom: 1px solid var(--border); }
header h2 { margin: 0; font-size: 16px; }
.x { background: transparent; font-size: 18px; }
.body { padding: 16px 20px; overflow-y: auto; flex: 1; }
h3 { font-size: 13px; margin: 0 0 8px; color: var(--muted); }
section + section { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--border); }
.root-list, .folder-list { list-style: none; padding: 0; margin: 0 0 8px; }
.root-item {
  display: flex; justify-content: space-between; align-items: center;
  padding: 6px 8px; border-radius: 4px; font-size: 13px;
}
.root-item:hover { background: var(--panel-2); }
.root-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: var(--muted); font-size: 13px; padding: 6px 8px; }
.breadcrumb { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.current-path {
  font-size: 12px; color: var(--muted); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.folder-list { max-height: 220px; overflow-y: auto; border: 1px solid var(--border); border-radius: 6px; }
.folder-list li { padding: 6px 10px; cursor: pointer; font-size: 13px; }
.folder-list li:hover { background: var(--panel-2); }
.pick-row { margin-top: 10px; }
.ghost { background: var(--panel-2); color: var(--text); }
.ghost.small { padding: 4px 10px; font-size: 12px; }
.hint, .warn { font-size: 12px; padding: 8px 10px; border-radius: 4px; line-height: 1.5; margin-bottom: 8px; }
.hint { color: var(--muted); background: var(--panel-2); }
.warn { color: var(--warn); background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.3); }
footer { padding: 12px 20px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; }
footer .ghost { background: var(--panel-2); color: var(--text); }
</style>
