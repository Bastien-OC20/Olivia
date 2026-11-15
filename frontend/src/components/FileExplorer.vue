<template>
  <div class="explorer">
    <div class="fil">
      <button
        v-if="currentPath"
        type="button"
        class="btn-icone"
        aria-label="Revenir à la racine des documents"
        title="Revenir à la racine des documents"
        @click="loadRoot"
      >
        <Icone
          nom="chevron-gauche"
          :taille="18"
        />
      </button>
      <span
        class="fil-nom"
        :title="currentPath || rootPath || undefined"
      >
        <Icone
          nom="dossier"
          :taille="16"
        />
        <span class="fil-texte">{{ nomDossierCourant }}</span>
      </span>
    </div>

    <div
      v-if="settings.data.fs_roots.length > 1 || auth.estResponsable"
      class="root-row"
    >
      <template v-if="settings.data.fs_roots.length > 1">
        <label
          for="fs-root-select"
          class="sr-only"
        >Choisir un dossier</label>
        <select
          id="fs-root-select"
          :value="rootPrefix"
          @change="onSelectRoot"
        >
          <option value="">
            Tous les dossiers
          </option>
          <option
            v-for="(entry, i) in settings.data.fs_roots"
            :key="entry.path + i"
            :value="'r' + i"
          >
            {{ entry.label || basename(entry.path) }}
          </option>
        </select>
      </template>
      <button
        v-if="auth.estResponsable"
        ref="browseBtn"
        type="button"
        class="btn btn-secondaire"
        @click="browserOpen = true"
      >
        <Icone
          nom="dossier"
          :taille="16"
        />
        Parcourir…
      </button>
    </div>

    <div class="upload-row">
      <label
        for="fileup"
        class="btn btn-secondaire upload-btn"
      >
        <Icone
          nom="plus"
          :taille="16"
        />
        Importer un fichier
      </label>
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
      >
        <Icone
          v-if="uploadMsgOk"
          nom="coche"
          :taille="14"
        />
        <span>{{ uploadMsgTexte }}</span>
      </span>
    </div>

    <div class="search-box">
      <label
        for="fs-search"
        class="search-label"
      >Retrouver une information dans mes documents</label>
      <div class="champ champ-recherche">
        <Icone
          nom="loupe"
          :taille="16"
        />
        <input
          id="fs-search"
          v-model="search"
          class="search"
          placeholder="Ex. : convocation conseil de classe"
          aria-describedby="fs-search-help"
          @keydown.enter.prevent="doSearch"
        >
      </div>
      <p
        id="fs-search-help"
        class="search-help"
      >
        {{ searchHelpText }}
      </p>
      <div
        class="search-mode"
        role="group"
        aria-label="Mode de recherche"
      >
        <div class="seg">
          <button
            type="button"
            :class="{ on: searchMode === 'keyword' }"
            :aria-pressed="searchMode === 'keyword'"
            @click="searchMode = 'keyword'"
          >
            <Icone
              nom="loupe"
              :taille="14"
            />
            Mots-clés
          </button>
          <button
            type="button"
            :class="{ on: searchMode === 'semantic' }"
            :aria-pressed="searchMode === 'semantic'"
            @click="searchMode = 'semantic'"
          >
            <Icone
              nom="etincelles"
              :taille="14"
            />
            Par le sens
          </button>
        </div>
      </div>
      <div class="search-actions">
        <button
          type="button"
          class="btn btn-primaire"
          :disabled="!search.trim() || searching"
          @click="doSearch"
        >
          <template v-if="searching">
            Recherche…
          </template>
          <template v-else>
            <Icone
              nom="loupe"
              :taille="16"
            />
            Chercher
          </template>
        </button>
        <button
          v-if="searchData"
          type="button"
          class="btn btn-fantome"
          @click="clearSearch"
        >
          Effacer
        </button>
      </div>
    </div>

    <!-- Confirmation / erreur d'un ajout à la conversation, d'où qu'il parte
         (résultat de recherche ou aperçu d'un fichier de l'arborescence). Collée
         en haut du corps du panneau, qui défile sous son en-tête : l'arborescence
         peut être longue et l'aperçu loin sous l'écran. -->
    <p
      v-if="injectMsg"
      class="inject-msg"
      aria-live="polite"
    >
      <Icone
        v-if="injectMsgOk"
        nom="coche"
        :taille="14"
      />
      <span>{{ injectMsgTexte }}</span>
    </p>

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
        <Icone
          nom="alerte"
          :taille="14"
        />
        <span>{{ searchData.notice }}</span>
      </p>
      <button
        v-if="searchData.results.length > 1"
        type="button"
        class="btn btn-secondaire inject-all"
        @click="injectAll"
      >
        <Icone
          nom="plus"
          :taille="16"
        />
        Tout utiliser dans la conversation ({{ searchData.results.length }})
      </button>

      <article
        v-for="r in searchData.results"
        :key="r.path"
        class="doc-hit"
      >
        <h4 class="doc-title">
          <button
            type="button"
            class="doc-open"
            :title="`Ouvrir l'aperçu de ${r.name}`"
            @click="openFile(r.path)"
          >
            <Icone
              :nom="nomIconeFichier(r.ext)"
              :taille="16"
            />
            <span class="doc-nom">{{ r.name }}</span>
          </button>
        </h4>
        <p class="doc-path">
          {{ cheminLisible(r.path) }}
        </p>
        <!-- Le texte vient d'une reconnaissance automatique : jamais fiable à
             100 %. L'utilisatrice doit le savoir AVANT de recopier une date ou
             un numéro de circulaire dans un courrier officiel. -->
        <p
          v-if="r.ocr"
          class="doc-ocr"
          :title="r.ocr_notice || undefined"
        >
          <Icone
            nom="alerte"
            :taille="14"
          />
          <span>
            Texte reconnu automatiquement (document scanné) — à vérifier sur l'original.
            <template v-if="r.ocr_notice">
              <br>{{ r.ocr_notice }}
            </template>
          </span>
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
          type="button"
          class="btn btn-secondaire doc-inject"
          @click="injectPath(r.path, r.name)"
        >
          <Icone
            nom="plus"
            :taille="16"
          />
          Utiliser dans la conversation
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
        :title="item.name"
        @click="item.is_dir ? navigate(item.path) : openFile(item.path)"
        @keydown.enter="item.is_dir ? navigate(item.path) : openFile(item.path)"
      >
        <Icone
          :nom="nomIconeFichier(item.ext, item.is_dir)"
          :taille="18"
        />
        <span class="nom">{{ item.name }}</span>
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
      v-if="auth.estResponsable"
      :is-open="browserOpen"
      @close="closeBrowser"
    />
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import FilePreview from './FilePreview.vue'
import FolderPickerModal from './FolderPickerModal.vue'
import Icone from './Icone.vue'
import { nomIconeFichier, cheminLisible } from '../typesFichier.js'
import { useSettingsStore } from '../stores/settings.js'
import { useAuthStore } from '../stores/auth.js'
import { useChatStore } from '../stores/chat.js'
import { useTableauxStore } from '../stores/tableaux.js'

const settings = useSettingsStore()
// Le parcours des dossiers du poste est réservé au responsable (403 sinon).
const auth = useAuthStore()
const chat = useChatStore()
const tableaux = useTableauxStore()
const items = ref([])
const currentPath = ref('')
const rootPath = ref('')
const rootLabel = ref('')
const selectedPath = ref(null)
const search = ref('')
// Mode de recherche documentaire : 'keyword' (mots exacts) ou 'semantic' (par le
// sens, via l'index vectoriel). Simple état de session, non persisté.
const searchMode = ref('keyword')
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
// française reste correcte (pas d'espace parasite avant le point). Les « termes »
// n'ont de sens qu'en recherche par mots-clés.
const texteAucunResultat = computed(() => {
  if (searchMode.value === 'semantic') {
    return 'Aucun extrait ne correspond à cette recherche. Essayez de la reformuler.'
  }
  const mots = searchData.value?.terms || []
  const liste = mots.length ? ` (${mots.join(', ')})` : ''
  return `Aucun document ne contient tous ces mots${liste}. Essayez avec moins de mots.`
})

// Texte d'aide sous le champ de recherche, adapté au mode choisi.
const searchHelpText = computed(() => (searchMode.value === 'semantic'
  ? 'Décrivez l\'idée recherchée avec vos propres mots — Oliv\'IA comprend le sens, '
    + 'pas seulement les mots exacts. Nécessite d\'avoir construit l\'index dans '
    + 'Paramètres → Documents.'
  : 'Écrivez simplement les mots à retrouver. Oliv\'IA cherche à l\'intérieur de vos '
    + 'documents Word, Excel, PDF et texte. Ni les majuscules ni les accents n\'ont '
    + 'd\'importance.'))

// Nom du dossier affiché dans le fil d'Ariane ; « rN » est un préfixe interne,
// jamais montré tel quel.
const nomDossierCourant = computed(() => {
  const p = currentPath.value
  if (!p || /^r\d+$/.test(p)) return rootLabel.value || 'Documents'
  return basename(p)
})

// Les messages de réussite commencent par « ✓ » (annoncé aux lecteurs d'écran) ;
// à l'écran, la coche est dessinée par une icône et le texte reste seul.
const injectMsgOk = computed(() => injectMsg.value.startsWith('✓'))
const injectMsgTexte = computed(() => injectMsg.value.replace(/^✓\s*/, ''))
const uploadMsgOk = computed(() => uploadMsg.value.startsWith('✓'))
const uploadMsgTexte = computed(() => uploadMsg.value.replace(/^✓\s*/, ''))

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
  let renomme = false
  uploadMsg.value = 'Envoi…'
  try {
    const fd = new FormData()
    fd.append('file', file)
    const r = await fetch(`/api/fs/upload?path=${encodeURIComponent(currentPath.value)}`, {
      method: 'POST', body: fd,
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
    // Un fichier du même nom existait : le serveur ne l'écrase jamais et range
    // l'import sous un autre nom. Il faut le dire, sinon l'utilisatrice
    // chercherait (ou rouvrirait) l'ancien document sous le nom d'origine.
    renomme = !!data.renamed
    uploadMsg.value = renomme
      ? `✓ Importé sous « ${data.name} » : un fichier « ${data.requested_name} » existait déjà, il n'a pas été remplacé.`
      : `✓ ${data.name} importé`
    await navigate(currentPath.value)
  } catch (err) {
    uploadMsg.value = ''
    alert('Upload impossible : ' + err.message)
  } finally {
    if (fileInput.value) fileInput.value.value = ''
    // Message de renommage laissé plus longtemps : il demande d'être lu.
    setTimeout(() => { uploadMsg.value = '' }, renomme ? 10000 : 4000)
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

// Après un ajout réussi, un tableau blanc affiché garderait l'utilisatrice devant
// un écran qui n'a pas bougé : on ramène à la conversation, où le bandeau
// « N documents » confirme l'ajout. En cas d'échec, on ne change rien : le
// message d'erreur doit rester lisible ici.
function montrerConversation() {
  tableaux.fermer()
}

/** Ajoute un document à la conversation (résultat de recherche ou aperçu). */
async function injectPath(path, name) {
  try {
    const doc = await loadDocument(path, name)
    if (chat.addFileContext(doc)) {
      annonce(`✓ « ${doc.name} » est maintenant utilisé dans la conversation.`)
      montrerConversation()
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
  if (ok > 0) montrerConversation()
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
    const base = searchMode.value === 'semantic' ? '/api/fs/search/semantic' : '/api/fs/search'
    const url = `${base}?q=${encodeURIComponent(q)}`
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
.explorer { padding: var(--e-2) var(--e-3) var(--e-4); }
.fil { display: flex; align-items: center; gap: var(--e-1); min-height: 36px; }
.fil-nom {
  display: flex; align-items: center; gap: var(--e-2); min-width: 0;
  font-size: var(--t-s); font-weight: 600; color: var(--texte); padding: 0 var(--e-1);
}
.fil-nom .icone { flex-shrink: 0; color: var(--accent-texte); }
.fil-texte { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.root-row { display: flex; align-items: center; gap: var(--e-2); margin: var(--e-2) 0; flex-wrap: wrap; }
.root-row select { flex: 1; min-width: 0; }
.upload-row { margin: var(--e-2) 0; display: flex; align-items: center; gap: var(--e-2); flex-wrap: wrap; }
.upload-btn { cursor: pointer; font-size: var(--t-s); }
/* Le champ « fichier » est masqué : le focus clavier se voit sur son libellé. */
.upload-row:has(#fileup:focus-visible) .upload-btn {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.upload-msg { display: inline-flex; align-items: center; gap: 6px; font-size: var(--t-xs); color: var(--discret); }
.upload-msg .icone { color: var(--ok); flex-shrink: 0; }
.search-box { margin: var(--e-3) 0; }
.search-label { display: block; font-size: var(--t-s); font-weight: 600; margin-bottom: var(--e-1); }
.champ-recherche { display: flex; align-items: center; gap: var(--e-2); padding: 0 var(--e-3); }
.champ-recherche .icone { color: var(--discret); flex-shrink: 0; }
/* Le contour de focus est porté par le conteneur (.champ:focus-within). */
.champ-recherche .search {
  flex: 1; min-width: 0; background: transparent; border: none; box-shadow: none;
  padding: 8px 0; border-radius: 0;
}
.search-help { font-size: 11px; color: var(--discret); line-height: 1.4; margin: var(--e-1) 0 var(--e-2); }
.search-mode { margin: 0 0 var(--e-2); }
.seg {
  display: flex; gap: 2px; padding: 3px; background: var(--surface-2);
  border: 1px solid var(--bordure); border-radius: var(--r-rond);
}
.seg button {
  flex: 1; display: inline-flex; align-items: center; justify-content: center; gap: 6px;
  background: transparent; color: var(--discret);
  padding: 5px 10px; font-size: var(--t-xs); border-radius: var(--r-rond);
}
.seg button:where(:not(:disabled)):hover { background: var(--surface-3); color: var(--texte); }
.seg button.on,
.seg button.on:where(:not(:disabled)):hover {
  background: var(--accent-doux); color: var(--accent-texte); font-weight: 600;
}
.search-actions { display: flex; gap: var(--e-2); }
.search-results { margin: var(--e-2) 0; max-height: 420px; overflow-y: auto; }
.search-summary { font-size: var(--t-xs); color: var(--discret); margin: 0 0 6px; }
.search-notice {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: var(--t-xs); color: var(--avert); line-height: 1.4; margin: 0 0 6px;
}
.search-notice .icone, .doc-ocr .icone { flex-shrink: 0; margin-top: 1px; }
.inject-all { width: 100%; font-size: var(--t-s); margin-bottom: 6px; }
/* Collé en haut du corps du panneau (qui défile sous son en-tête), sur fond opaque. */
.inject-msg {
  position: sticky; top: 0; z-index: 1;
  display: flex; align-items: flex-start; gap: 6px;
  font-size: var(--t-xs); color: var(--texte); line-height: 1.4; margin: var(--e-2) 0 6px;
  padding: 6px var(--e-2); background: var(--surface);
  border: 1px solid var(--bordure); border-radius: var(--r-1);
}
.inject-msg .icone { color: var(--ok); flex-shrink: 0; margin-top: 1px; }
.doc-hit {
  padding: var(--e-2); margin-bottom: 6px; border: 1px solid var(--bordure);
  border-radius: var(--r-2); background: var(--surface);
}
.doc-title { margin: 0; font-size: var(--t-s); }
.doc-open {
  display: flex; align-items: center; gap: 6px; max-width: 100%;
  background: transparent; color: var(--accent-texte); padding: 0;
  font-size: var(--t-s); text-align: left; cursor: pointer;
}
.doc-open:where(:not(:disabled)):hover { background: transparent; text-decoration: underline; }
.doc-open .icone { flex-shrink: 0; }
.doc-nom { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.doc-path { font-size: 11px; color: var(--discret); margin: 2px 0 6px; overflow-wrap: anywhere; }
.doc-snippet { font-size: var(--t-xs); color: var(--texte); line-height: 1.45; margin: 0 0 4px; }
.doc-snippet.empty-snippet { color: var(--discret); font-style: italic; }
.doc-ocr {
  display: flex; align-items: flex-start; gap: 6px;
  font-size: 11px; color: var(--avert); line-height: 1.4; margin: 0 0 6px;
}
.doc-inject { font-size: var(--t-xs); margin-top: var(--e-1); padding: 6px 12px; }
.tree { list-style: none; padding: 0; margin: var(--e-2) 0; }
.tree li {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 10px; border-radius: var(--r-1); cursor: pointer; font-size: var(--t-s);
  color: var(--texte); transition: background-color var(--transition);
}
.tree li .icone { flex-shrink: 0; color: var(--discret); }
.tree li.folder .icone { color: var(--accent-texte); }
.tree li .nom { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tree li:hover { background: var(--surface-2); }
.tree li.empty { color: var(--discret); cursor: default; }
.tree li.empty:hover { background: transparent; }
</style>
