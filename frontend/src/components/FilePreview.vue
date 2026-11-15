<template>
  <div class="preview-panel">
    <div class="preview-header">
      <h3
        class="preview-title"
        :title="displayName"
      >
        <Icone
          nom="document"
          :taille="18"
        />
        <span class="preview-nom">{{ displayName }}</span>
      </h3>
      <div class="preview-actions">
        <a
          v-if="path"
          class="btn btn-secondaire"
          :href="downloadUrl"
          download
        >
          <Icone
            nom="telecharger"
            :taille="16"
          />
          Télécharger
        </a>
        <button
          v-if="canInject"
          class="btn btn-primaire"
          type="button"
          @click="onInject"
        >
          <Icone
            nom="plus"
            :taille="16"
          />
          Utiliser dans la conversation
        </button>
        <button
          class="btn-icone"
          type="button"
          aria-label="Fermer l'aperçu"
          title="Fermer l'aperçu"
          @click="$emit('close')"
        >
          <Icone
            nom="fermer"
            :taille="18"
          />
        </button>
      </div>
    </div>

    <div
      class="preview-status"
      aria-live="polite"
    >
      <div
        v-if="loading"
        class="status-loading"
      >
        Chargement de l'aperçu…
      </div>
    </div>

    <div
      v-if="!loading"
      class="preview-body"
    >
      <!-- error -->
      <div
        v-if="data && data.kind === 'error'"
        class="state-error"
      >
        <strong>Erreur :</strong> {{ data.detail }}
      </div>

      <!-- fetch failure -->
      <div
        v-else-if="fetchError"
        class="state-error"
      >
        <strong>Erreur :</strong> {{ fetchError }}
      </div>

      <!-- text -->
      <template v-else-if="data && data.kind === 'text'">
        <pre class="text-preview">{{ data.content }}</pre>
        <p
          v-if="data.truncated"
          class="note"
        >
          Aperçu tronqué.
        </p>
      </template>

      <!-- table (csv / xlsx) -->
      <template v-else-if="data && data.kind === 'table'">
        <div class="table-scroll">
          <table class="table-preview">
            <caption>{{ data.sheet ? `${displayName} — ${data.sheet}` : displayName }}</caption>
            <thead>
              <tr>
                <th
                  v-for="(col, ci) in data.columns"
                  :key="ci"
                  scope="col"
                >
                  {{ col }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="(row, ri) in data.rows"
                :key="ri"
              >
                <td
                  v-for="(cell, ci) in row"
                  :key="ci"
                >
                  {{ cell }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p
          v-if="data.truncated"
          class="note"
        >
          {{ data.rows.length }} premières lignes.
        </p>
      </template>

      <!-- doc (word) -->
      <template v-else-if="data && data.kind === 'doc'">
        <div class="doc-preview">
          <p
            v-for="(para, pi) in data.paragraphs"
            :key="pi"
          >
            {{ para }}
          </p>
        </div>
        <p
          v-if="data.truncated"
          class="note"
        >
          Aperçu tronqué.
        </p>
      </template>

      <!-- image -->
      <div
        v-else-if="data && data.kind === 'image'"
        class="image-preview"
      >
        <img
          :src="data.url"
          :alt="data.name"
        >
      </div>

      <!-- pdf -->
      <div
        v-else-if="data && data.kind === 'pdf'"
        class="pdf-preview"
      >
        <iframe
          :src="data.url"
          :title="`Aperçu PDF : ${data.name}`"
        />
        <p class="note">
          Si l'aperçu ne s'affiche pas,
          <a
            :href="downloadUrl"
            download
          >téléchargez le fichier</a>.
        </p>
      </div>

      <!-- unsupported -->
      <div
        v-else-if="data && data.kind === 'unsupported'"
        class="state-unsupported"
      >
        <Icone
          nom="document"
          :taille="32"
        />
        <p>Aperçu non disponible pour ce type de fichier.</p>
        <a
          class="btn btn-secondaire"
          :href="downloadUrl"
          download
        >
          <Icone
            nom="telecharger"
            :taille="16"
          />
          Télécharger
        </a>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import Icone from './Icone.vue'

const props = defineProps({
  path: { type: String, default: '' }
})
const emit = defineEmits(['inject', 'close'])

const data = ref(null)
const loading = ref(false)
const fetchError = ref('')

const displayName = computed(() => {
  if (data.value && data.value.name) return data.value.name
  if (!props.path) return ''
  const parts = props.path.split(/[\\/]/)
  return parts[parts.length - 1] || props.path
})

const downloadUrl = computed(() => {
  return props.path ? `/api/fs/download?path=${encodeURIComponent(props.path)}` : ''
})

// Le PDF est injectable depuis que le backend sait en extraire le texte
// (route /api/fs/text) — son aperçu reste rendu par le navigateur.
const canInject = computed(() => {
  return !!data.value && ['text', 'table', 'doc', 'pdf'].includes(data.value.kind)
})

function onInject() {
  emit('inject', { path: props.path, name: displayName.value })
}

async function fetchPreview(path) {
  if (!path) {
    data.value = null
    fetchError.value = ''
    loading.value = false
    return
  }
  loading.value = true
  fetchError.value = ''
  data.value = null
  try {
    const r = await fetch(`/api/fs/preview?path=${encodeURIComponent(path)}`)
    if (!r.ok) throw new Error(`Requête échouée (${r.status})`)
    data.value = await r.json()
  } catch (e) {
    fetchError.value = e.message || 'Erreur inconnue'
  } finally {
    loading.value = false
  }
}

watch(() => props.path, (p) => { fetchPreview(p) }, { immediate: true })
</script>

<style scoped>
.preview-panel {
  display: flex;
  flex-direction: column;
  background: var(--surface);
  border: 1px solid var(--bordure);
  border-radius: var(--r-2);
  box-shadow: var(--ombre-1);
  padding: var(--e-3);
  color: var(--texte);
}

/* Le bouton de fermeture est ancré en haut à droite : dans le panneau étroit,
   les actions passent à la ligne et il se retrouvait seul sur une ligne. */
.preview-header {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--e-3);
  flex-wrap: wrap;
  margin-bottom: var(--e-3);
  padding-right: 40px;
}
.preview-actions .btn-icone {
  position: absolute;
  top: -6px;
  right: 0;
}

.preview-title {
  display: flex;
  align-items: center;
  gap: var(--e-2);
  min-width: 0;
  max-width: 100%;
  margin: 0;
  font-size: var(--t-m);
}
.preview-title .icone { flex-shrink: 0; color: var(--accent-texte); }
.preview-nom { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.preview-actions {
  display: flex;
  align-items: center;
  gap: var(--e-2);
  flex-wrap: wrap;
}
.preview-actions .btn { font-size: var(--t-s); padding: 6px 12px; }

.preview-status .status-loading {
  color: var(--discret);
  font-size: var(--t-s);
  padding: 4px 0 8px 0;
}

.preview-body { min-width: 0; }

.note {
  color: var(--discret);
  font-size: var(--t-xs);
  margin: 8px 0 0 0;
}

.state-error {
  background: color-mix(in srgb, var(--avert) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--avert) 40%, transparent);
  color: var(--texte);
  border-radius: var(--r-1);
  padding: 10px 12px;
  font-size: var(--t-s);
}

.state-unsupported {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  padding: 24px 12px;
  color: var(--discret);
  text-align: center;
}

/* text */
.text-preview {
  margin: 0;
  max-height: 360px;
  overflow: auto;
  background: var(--surface-2);
  border: 1px solid var(--bordure);
  border-radius: var(--r-1);
  padding: 10px;
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  font-size: var(--t-xs);
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--texte);
}

/* table */
.table-scroll {
  overflow-x: auto;
  max-width: 100%;
  border: 1px solid var(--bordure);
  border-radius: var(--r-1);
}
.table-preview {
  border-collapse: collapse;
  width: 100%;
  font-size: var(--t-s);
}
.table-preview caption {
  text-align: left;
  padding: 8px 10px;
  color: var(--discret);
  font-size: var(--t-xs);
  background: var(--surface-2);
  caption-side: top;
}
.table-preview th,
.table-preview td {
  padding: 6px 10px;
  border-bottom: 1px solid var(--bordure);
  text-align: left;
  white-space: nowrap;
}
.table-preview thead th {
  background: var(--surface-2);
  position: sticky;
  top: 0;
}
.table-preview tbody tr:nth-child(even) {
  background: var(--surface-2);
}

/* doc */
.doc-preview {
  max-height: 420px;
  overflow: auto;
  max-width: 70ch;
  padding: 4px 2px;
}
.doc-preview p {
  line-height: 1.6;
  margin: 0 0 12px 0;
}

/* image */
.image-preview {
  display: flex;
  justify-content: center;
  align-items: center;
  background: var(--surface-2);
  border-radius: var(--r-1);
  padding: var(--e-2);
}
.image-preview img {
  max-width: 100%;
  height: auto;
  border-radius: var(--e-1);
}

/* pdf */
.pdf-preview iframe {
  width: 100%;
  height: 500px;
  border: 1px solid var(--bordure);
  border-radius: var(--r-1);
  background: var(--surface-2);
}

@media (prefers-reduced-motion: reduce) {
  * { transition: none !important; animation: none !important; }
}
</style>
