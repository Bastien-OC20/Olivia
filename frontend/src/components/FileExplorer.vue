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

    <div class="search-box">
      <label
        for="fs-search"
        class="search-label"
      >Retrouver une information dans mes documents</label>
      <input
        id="fs-search"
        v-model="search"
        class="search"
        placeholder="Ex. : convocation conseil de classe"
        aria-describedby="fs-search-help"
        @keydown.enter.prevent="doSearch"
      >
      <p
        id="fs-search-help"
        class="search-help"
      >
        Écrivez simplement les mots à retrouver. Olivia cherche à l'intérieur de vos
        documents Word, Excel, PDF et texte. Ni les majuscules ni les accents n'ont
        d'importance.
      </p>
      <div class="search-actions">
        <button
          :disabled="!search.trim() || searching"
          @click="doSearch"
        >
          {{ searching ? '⏳ Recherche…' : '🔍 Chercher' }}
        </button>
        <button
          v-if="searchData"
          class="ghost"
          @click="clearSearch"
        >
          Effacer
        </button>
      </div>
    </div>

    <div
      v-if="searchData"
      class="search-results"
      aria-live="polite"
    >
      <p class="search-summary">
        <template v-if="searchData.results.length">
          {{ searchData.results.length }} document{{ searchData.results.length > 1 ? 's' : '' }}
          trouvé{{ searchData.results.length > 1 ? 's' : '' }}
          sur {{ searchData.files_scanned }} examiné{{ searchData.files_scanned > 1 ? 's' : '' }}.
        </template>
        <template v-else>
          {{ texteAucunResultat }}
        </template>
      </p>
      <p
        v-if="searchData.notice"
        class="search-notice"
      >
        ⚠️ {{ searchData.notice }}
      </p>
      <button
        v-if="searchData.results.length > 1"
        class="inject-all"
        @click="injectAll"
      >
        ➕ Tout utiliser dans la conversation ({{ searchData.results.length }})
      </button>
      <p
        v-if="injectMsg"
        class="inject-msg"
        aria-live="polite"
      >
        {{ injectMsg }}
      </p>

      <article
        v-for="r in searchData.results"
        :key="r.path"
        class="doc-hit"
      >
        <h4 class="doc-title">
          <button
            class="doc-open"
            :title="`Ouvrir l'aperçu de ${r.name}`"
            @click="openFile(r.path)"
          >
            {{ icon(r.ext) }} {{ r.name }}
          </button>
        </h4>
        <p class="doc-path">
          {{ r.path }}
        </p>
        <!-- Le texte vient d'une reconnaissance automatique : jamais fiable à
             100 %. L'utilisatrice doit le savoir AVANT de recopier une date ou
             un numéro de circulaire dans un courrier officiel. -->
        <p
          v-if="r.ocr"
          class="doc-ocr"
          :title="r.ocr_notice || undefined"
        >
          🔍 Texte reconnu automatiquement (document scanné) — à vérifier sur l'original.
          <template v-if="r.ocr_notice">
            <br>{{ r.ocr_notice }}
          </template>
        </p>
        <p
          v-for="(s, i) in r.snippets"
          :key="i"
          class="doc-snippet"
        >
          {{ s }}
        </p>
        <p
          v-if="!r.snippets.length"
          class="doc-snippet empty-snippet"
        >
          Trouvé d'après le nom du fichier.
        </p>
        <button
          class="doc-inject"
          @click="injectPath(r.path, r.name)"
        >
          ➕ Utiliser dans la conversation
        </button>
      </article>
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
import { useChatStore } from '../stores/chat.js'

const settings = useSettingsStore()
const chat = useChatStore()
const items = ref([])
const currentPath = ref('')
const rootPath = ref('')
const rootLabel = ref('')
const selectedPath = ref(null)
const search = ref('')
const searchData = ref(null)
const searching = ref(false)
const injectMsg = ref('')
const uploadMsg = ref('')
const fileInput = ref(null)
const browseBtn = ref(null)
const browserOpen = ref(false)

// Préfixe rN du dossier actuellement affiché, pour synchroniser le sélecteur.
const rootPrefix = computed(() => {
  const m = currentPath.value.match(/^r(\d+)/)
  return m ? `r${m[1]}` : ''
})

// Message d'absence de résultat, construit en une seule chaîne : la ponctuation
// française reste correcte (pas d'espace parasite avant le point).
const texteAucunResultat = computed(() => {
  const mots = searchData.value?.terms || []
  const liste = mots.length ? ` (${mots.join(', ')})` : ''
  return `Aucun document ne contient tous ces mots${liste}. Essayez avec moins de mots.`
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
    searchData.value = null
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

// Texte brut d'un document, quel que soit son format (Word, Excel, PDF, texte).
async function loadDocument(path, name) {
  const r = await fetch(`/api/fs/text?path=${encodeURIComponent(path)}`)
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
  if (data.empty) {
    throw new Error('aucun texte lisible (document scanné ou protégé ?)')
  }
  return {
    path,
    name: data.name || name || path,
    content: data.content || '',
    // Le serveur a déjà coupé un document très long : l'info doit remonter
    // jusqu'au bandeau de la conversation.
    sourceTruncated: !!data.truncated,
  }
}

function annonce(texte) {
  injectMsg.value = texte
  setTimeout(() => { if (injectMsg.value === texte) injectMsg.value = '' }, 5000)
}

/** Ajoute un document à la conversation depuis un résultat de recherche. */
async function injectPath(path, name) {
  try {
    const doc = await loadDocument(path, name)
    if (chat.addFileContext(doc)) {
      annonce(`✓ « ${doc.name} » est maintenant utilisé dans la conversation.`)
    } else {
      annonce(chat.fileContextNotice)
    }
  } catch (e) {
    annonce(`Impossible d'utiliser « ${name} » : ${e.message}`)
  }
}

/** Ajoute d'un coup tous les documents trouvés. */
async function injectAll() {
  const cibles = searchData.value?.results || []
  let ok = 0
  const echecs = []
  for (const r of cibles) {
    try {
      const doc = await loadDocument(r.path, r.name)
      if (chat.addFileContext(doc)) ok++
      else { echecs.push(r.name); break }
    } catch { echecs.push(r.name) }
  }
  const suite = echecs.length ? ` — non ajouté(s) : ${echecs.join(', ')}` : ''
  annonce(`✓ ${ok} document(s) ajouté(s) à la conversation${suite}`)
}

// Injection depuis l'aperçu d'un fichier (bouton du panneau de prévisualisation).
async function onInject({ path, name }) {
  await injectPath(path, name)
}

function clearSearch() {
  searchData.value = null
  injectMsg.value = ''
}

async function doSearch() {
  const q = search.value.trim()
  if (!q || searching.value) return
  searching.value = true
  injectMsg.value = ''
  try {
    const url = `/api/fs/search?q=${encodeURIComponent(q)}`
      + `&path=${encodeURIComponent(currentPath.value)}`
    const r = await fetch(url)
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    searchData.value = { results: [], terms: [], files_scanned: 0, notice: '', ...data }
  } catch (e) {
    searchData.value = {
      results: [], terms: [], files_scanned: 0,
      notice: `Recherche impossible : ${e.message}`,
    }
  } finally {
    searching.value = false
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
.search-box { margin: 10px 0; }
.search-label { display: block; font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.search { width: 100%; }
.search-help { font-size: 11px; color: var(--muted); line-height: 1.4; margin: 4px 0 6px; }
.search-actions { display: flex; gap: 8px; }
.search-results { margin: 8px 0; max-height: 420px; overflow-y: auto; }
.search-summary { font-size: 12px; color: var(--muted); margin: 0 0 6px; }
.search-notice { font-size: 12px; color: var(--warn); line-height: 1.4; margin: 0 0 6px; }
.inject-all { width: 100%; font-size: 13px; margin-bottom: 6px; }
.inject-msg { font-size: 12px; color: var(--accent); line-height: 1.4; margin: 0 0 6px; }
.doc-hit {
  padding: 8px; margin-bottom: 6px; border: 1px solid var(--border);
  border-radius: 6px; background: var(--panel);
}
.doc-title { margin: 0; font-size: 13px; }
.doc-open {
  background: transparent; color: var(--accent); padding: 0;
  font-size: 13px; text-align: left; cursor: pointer;
}
.doc-open:hover { text-decoration: underline; }
.doc-path { font-size: 11px; color: var(--muted); margin: 2px 0 6px;
            overflow-wrap: anywhere; }
.doc-snippet { font-size: 12px; color: var(--text); line-height: 1.45; margin: 0 0 4px; }
.doc-snippet.empty-snippet { color: var(--muted); font-style: italic; }
.doc-ocr { font-size: 11px; color: var(--warn); line-height: 1.4; margin: 0 0 6px; }
.doc-inject { font-size: 12px; margin-top: 4px; }
.tree { list-style: none; padding: 0; margin: 8px 0; }
.tree li { padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 13px; }
.tree li:hover { background: var(--panel-2); }
.tree li.empty { color: var(--muted); cursor: default; }
.tree li.empty:hover { background: transparent; }
</style>
