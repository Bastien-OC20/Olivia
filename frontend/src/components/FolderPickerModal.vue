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
        class="modal carte"
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-picker-title"
      >
        <header>
          <h2 id="folder-picker-title">
            <Icone
              nom="dossier"
              :taille="20"
            />
            Dossiers accessibles
          </h2>
          <button
            ref="closeBtn"
            type="button"
            class="btn-icone"
            aria-label="Fermer la fenêtre de choix de dossier"
            @click="close"
          >
            <Icone
              nom="fermer"
              :taille="18"
            />
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
                  type="button"
                  class="btn btn-secondaire petit"
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
                type="button"
                class="btn btn-secondaire petit"
                :disabled="stack.length === 0"
                @click="goUp"
              >
                <Icone
                  nom="chevron-gauche"
                  :taille="14"
                />
                Remonter
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
              <Icone
                nom="alerte"
                :taille="16"
              />
              <span>{{ error }}</span>
            </p>
            <p
              v-if="addedMsg"
              class="hint"
              aria-live="polite"
            >
              <Icone
                nom="coche"
                :taille="16"
              />
              <span>{{ addedMsgTexte }}</span>
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
                <Icone
                  nom="dossier"
                  :taille="16"
                />
                <span class="nom">{{ f.name }}</span>
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
                type="button"
                class="btn btn-primaire"
                :disabled="!currentPath || adding"
                @click="choose"
              >
                <Icone
                  nom="coche"
                  :taille="16"
                />
                Choisir ce dossier
              </button>
            </div>
          </section>
        </div>

        <footer>
          <button
            type="button"
            class="btn btn-secondaire"
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
import { ref, computed, watch, nextTick } from 'vue'
import Icone from './Icone.vue'
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
// Le message commence par « ✓ » pour les lecteurs d'écran ; à l'écran, une icône le remplace.
const addedMsgTexte = computed(() => addedMsg.value.replace(/^✓\s*/, ''))
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
  position: fixed; inset: 0; background: color-mix(in srgb, var(--fond) 70%, transparent);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  width: 520px; max-width: 90vw;
  max-height: 85vh; border-radius: var(--r-4); box-shadow: var(--ombre-2);
  display: flex; flex-direction: column; overflow: hidden;
}
header { display: flex; justify-content: space-between; align-items: center;
         padding: var(--e-3) var(--e-5); border-bottom: 1px solid var(--bordure); }
header h2 { display: flex; align-items: center; gap: 10px; margin: 0; font-size: var(--t-l); }
header h2 .icone { color: var(--accent-texte); }
.body { padding: var(--e-4) var(--e-5); overflow-y: auto; flex: 1; }
h3 { font-size: var(--t-s); margin: 0 0 var(--e-2); color: var(--discret); }
section + section { margin-top: 18px; padding-top: 14px; border-top: 1px solid var(--bordure); }
.root-list, .folder-list { list-style: none; padding: 0; margin: 0 0 var(--e-2); }
.root-item {
  display: flex; justify-content: space-between; align-items: center; gap: var(--e-2);
  padding: 6px var(--e-2); border-radius: var(--r-1); font-size: var(--t-s);
}
.root-item:hover { background: var(--surface-2); }
.root-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.empty { color: var(--discret); font-size: var(--t-s); padding: 6px var(--e-2); }
.breadcrumb { display: flex; align-items: center; gap: var(--e-2); margin-bottom: var(--e-2); }
.current-path {
  font-size: var(--t-xs); color: var(--discret); overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap;
}
.folder-list {
  max-height: 220px; overflow-y: auto;
  border: 1px solid var(--bordure); border-radius: var(--r-1);
}
.folder-list li {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 10px; cursor: pointer; font-size: var(--t-s);
}
.folder-list li .icone { flex-shrink: 0; color: var(--accent-texte); }
.folder-list li .nom { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.folder-list li:hover { background: var(--surface-2); }
.folder-list li.empty { cursor: default; }
.folder-list li.empty:hover { background: transparent; }
.pick-row { margin-top: 10px; }
.petit { padding: 4px 10px; font-size: var(--t-xs); flex-shrink: 0; }
.hint, .warn {
  display: flex; align-items: flex-start; gap: var(--e-2);
  font-size: var(--t-xs); padding: var(--e-2) 10px; border-radius: var(--r-1);
  line-height: 1.5; margin-bottom: var(--e-2); color: var(--texte);
}
.hint .icone, .warn .icone { flex-shrink: 0; margin-top: 1px; }
.hint { background: var(--surface-2); }
.hint .icone { color: var(--ok); }
.warn {
  background: color-mix(in srgb, var(--avert) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--avert) 35%, transparent);
}
.warn .icone { color: var(--avert); }
footer { padding: var(--e-3) var(--e-5); border-top: 1px solid var(--bordure);
         display: flex; justify-content: flex-end; }
</style>
