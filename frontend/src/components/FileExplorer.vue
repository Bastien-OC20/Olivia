<template>
  <div class="explorer">
    <div class="explorer-header">
      <h3>📁 Documents</h3>
      <button
        class="ghost"
        aria-label="Revenir à la racine"
        @click="loadRoot"
      >
        ↑ Racine
      </button>
    </div>
    <div
      v-if="rootLabel"
      class="root-path"
      :title="rootPath"
    >
      {{ rootLabel }}
    </div>

    <div class="root-row">
      <label
        for="fs-root-select"
        class="sr-only"
      >Choisir un dossier</label>
      <select
        v-if="settings.data.fs_roots.length > 1"
        id="fs-root-select"
        :value="rootPrefix"
        @change="onSelectRoot"
      >
        <option value="">
          📁 Tous les dossiers
        </option>
        <option
          v-for="(entry, i) in settings.data.fs_roots"
          :key="entry.path + i"
          :value="'r' + i"
        >
          {{ entry.label || basename(entry.path) }}
        </option>
      </select>
      <button
        ref="browseBtn"
        class="ghost"
        @click="browserOpen = true"
      >
        📂 Parcourir…
      </button>
    </div>

    <div class="upload-row">
      <label
        for="fileup"
        class="upload-btn"
      >⬆ Importer un fichier</label>
      <input
        id="fileup"
        ref="fileInput"
        type="file"
        class="sr-only"
        @change="onUpload"
      >
      <span
        v-if="uploadMsg"
        class="upload-msg"
        aria-live="polite"
      >{{ uploadMsg }}</span>
    </div>

    <label
      for="fs-search"
      class="sr-only"
    >Rechercher dans les fichiers</label>
    <input
      id="fs-search"
      v-model="search"
      placeholder="Rechercher dans les fichiers..."
      class="search"
      @keydown.enter.prevent="doSearch"
    >
    <button
      :disabled="!search"
      @click="doSearch"
    >
      🔍 Chercher
    </button>

    <div
      v-if="searchResults"
      class="search-results"
      aria-live="polite"
    >
      <div
        v-for="(r, i) in searchResults"
        :key="i"
        class="search-hit"
        tabindex="0"
        role="button"
        @click="openFile(r.file)"
        @keydown.enter="openFile(r.file)"
      >
        <div class="hit-file">
          {{ r.file }}:{{ r.line }}
        </div>
        <div class="hit-snippet">
          {{ r.snippet }}
        </div>
      </div>
    </div>

    <ul class="tree">
      <li
        v-for="item in items"
        :key="item.path"
        :class="{ folder: item.is_dir, file: !item.is_dir }"
        tabindex="0"
        role="button"
        @click="item.is_dir ? navigate(item.path) : openFile(item.path)"
        @keydown.enter="item.is_dir ? navigate(item.path) : openFile(item.path)"
      >
        {{ item.is_dir ? '📂' : icon(item.ext) }} {{ item.name }}
      </li>
      <li
        v-if="items.length === 0"
        class="empty"
      >
        Aucun élément
      </li>
    </ul>

    <Transition name="fade">
      <FilePreview
        v-if="selectedPath"
        :path="selectedPath"
        @inject="onInject"
        @close="selectedPath = null"
      />
    </Transition>

    <FolderPickerModal
      :is-open="browserOpen"
      @close="closeBrowser"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import FilePreview from './FilePreview.vue'
import FolderPickerModal from './FolderPickerModal.vue'
import { useSettingsStore } from '../stores/settings.js'

const settings = useSettingsStore()
const items = ref([])
const currentPath = ref('')
const rootPath = ref('')
const rootLabel = ref('')
const selectedPath = ref(null)
const search = ref('')
const searchResults = ref(null)
const uploadMsg = ref('')
const fileInput = ref(null)
const browseBtn = ref(null)
const browserOpen = ref(false)
const emit = defineEmits(['file-selected'])

// Préfixe rN du dossier actuellement affiché, pour synchroniser le sélecteur.
const rootPrefix = computed(() => {
  const m = currentPath.value.match(/^r(\d+)/)
  return m ? `r${m[1]}` : ''
})

function onSelectRoot(e) { navigate(e.target.value) }

// Accessibilité : le focus revient au bouton « Parcourir » à la fermeture de la modale.
function closeBrowser() {
  browserOpen.value = false
  nextTick(() => browseBtn.value?.focus())
}

function basename(p) {
  return p.split(/[\\/]/).filter(Boolean).pop() || p
}

// Recharge la liste quand les dossiers accessibles sont reconfigurés dans les paramètres.
watch(() => JSON.stringify(settings.data.fs_roots), () => { loadRoot() })

// Charge la racine au montage (sinon la liste reste vide tant que rien ne déclenche le watch).
onMounted(loadRoot)

function icon(ext) {
  if (['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'].includes(ext)) return '🖼️'
  if (ext === '.pdf') return '📕'
  if (['.xlsx', '.xlsm', '.csv'].includes(ext)) return '📊'
  if (ext === '.docx') return '📘'
  return '📄'
}

async function navigate(path) {
  currentPath.value = path
  try {
    const r = await fetch(`/api/fs/list?path=${encodeURIComponent(path)}`)
    if (!r.ok) throw new Error()
    const data = await r.json()
    items.value = data.items || []
    searchResults.value = null
    if (data.root) {
      rootPath.value = data.root
      rootLabel.value = data.root_label || basename(data.root)
    }
  } catch { items.value = [] }
}
async function loadRoot() { await navigate('') }

function openFile(path) { selectedPath.value = path }

async function onUpload(e) {
  const file = e.target.files?.[0]
  if (!file) return
  uploadMsg.value = 'Envoi…'
  try {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch(`/api/fs/upload?path=${encodeURIComponent(currentPath.value)}`, {
      method: 'POST', body: fd,
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
    uploadMsg.value = `✓ ${data.name} importé`
    await navigate(currentPath.value)
  } catch (err) {
    uploadMsg.value = ''
    alert('Upload impossible : ' + err.message)
  } finally {
    if (fileInput.value) fileInput.value.value = ''
    setTimeout(() => { uploadMsg.value = '' }, 4000)
  }
}

// Injecte le fichier comme contexte de chat, quel que soit son type prévisualisable.
async function onInject({ path, name }) {
  try {
    const r = await fetch(`/api/fs/preview?path=${encodeURIComponent(path)}`)
    const data = await r.json()
    let content = ''
    if (data.kind === 'text') content = data.content || ''
    else if (data.kind === 'doc') content = (data.paragraphs || []).join('\n\n')
    else if (data.kind === 'table') {
      const head = (data.columns || []).join('\t')
      const body = (data.rows || []).map(row => row.join('\t')).join('\n')
      content = [head, body].filter(Boolean).join('\n')
    } else {
      alert('Ce type de fichier ne peut pas être injecté comme texte.')
      return
    }
    emit('file-selected', { path, name, content })
  } catch (e) {
    alert('Injection impossible : ' + e.message)
  }
}

async function doSearch() {
  if (!search.value) return
  try {
    const r = await fetch(`/api/fs/search?q=${encodeURIComponent(search.value)}&path=${encodeURIComponent(currentPath.value)}`)
    if (!r.ok) return
    const data = await r.json()
    searchResults.value = data.results || []
  } catch (e) {
    console.error('Recherche impossible :', e)
  }
}
</script>

<style scoped>
.explorer { padding: 12px; }
.explorer-header { display: flex; justify-content: space-between; align-items: center; }
.explorer-header h3 { margin: 0; font-size: 14px; }
.root-path {
  font-size: 11px; color: var(--muted); white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; margin: 2px 0 6px;
}
.root-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.root-row select { flex: 1; }
.ghost { background: var(--panel-2); color: var(--text); }
.upload-row { margin: 10px 0; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.upload-btn {
  display: inline-block; background: var(--panel-2); color: var(--text);
  border: 1px dashed var(--border); padding: 8px 14px; border-radius: 6px;
  cursor: pointer; font-size: 13px;
}
.upload-btn:hover { border-color: var(--accent); }
.upload-msg { font-size: 12px; color: var(--muted); }
.search { width: 100%; margin: 8px 0; }
.search-results { margin: 8px 0; max-height: 200px; overflow-y: auto; }
.search-hit { padding: 6px; border-bottom: 1px solid var(--border); cursor: pointer; border-radius: 4px; }
.search-hit:hover { background: var(--panel-2); }
.hit-file { font-size: 12px; color: var(--accent); }
.hit-snippet { font-size: 12px; color: var(--muted); font-family: monospace; }
.tree { list-style: none; padding: 0; margin: 8px 0; }
.tree li { padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.tree li:hover { background: var(--panel-2); }
.tree li.empty { color: var(--muted); cursor: default; }
.tree li.empty:hover { background: transparent; }
</style>
