<template>
  <div class="conversations">
    <button
      type="button"
      class="btn btn-primaire nouvelle"
      @click="nouvelle"
    >
      <Icone
        nom="plus"
        :taille="18"
      />
      Nouvelle conversation
    </button>

    <p
      v-if="chat.historyUnavailable"
      class="indisponible"
      aria-live="polite"
    >
      <Icone
        nom="alerte"
        :taille="16"
      />
      <span>
        L'historique n'est pas disponible pour le moment. Vos échanges en cours
        restent affichés mais ne seront pas enregistrés.
      </span>
    </p>

    <section
      v-for="g in groupes"
      :key="g.id"
      class="groupe"
    >
      <h3 class="groupe-titre">
        {{ g.libelle }}
      </h3>
      <ul
        class="liste"
        :aria-label="`Conversations enregistrées : ${g.libelle}`"
      >
        <li
          v-for="c in g.elements"
          :key="c.id"
          :class="{ actif: c.id === chat.currentId }"
        >
          <template v-if="renamingId === c.id">
            <label
              :for="`rename-${c.id}`"
              class="sr-only"
            >Nouveau titre de la conversation</label>
            <input
              :id="`rename-${c.id}`"
              ref="renameInput"
              v-model="renameText"
              class="champ-renommage"
              @keydown.enter.prevent="confirmRename(c.id)"
              @keydown.esc.prevent="cancelRename"
              @blur="confirmRename(c.id)"
            >
          </template>
          <template v-else>
            <button
              type="button"
              class="ouvrir"
              :aria-current="c.id === chat.currentId ? 'true' : undefined"
              @click="ouvrir(c.id)"
            >
              <span class="titre">{{ c.title || 'Sans titre' }}</span>
              <span class="meta">
                {{ dateRelative(c.updated_at) }}
                <template v-if="c.message_count">· {{ c.message_count }} message{{ c.message_count > 1 ? 's' : '' }}</template>
              </span>
            </button>
            <span class="actions">
              <button
                type="button"
                class="btn-icone action"
                :aria-label="`Renommer la conversation « ${c.title || 'Sans titre'} »`"
                @click="startRename(c)"
              >
                <Icone
                  nom="crayon"
                  :taille="16"
                />
              </button>
              <button
                type="button"
                class="btn-icone action supprimer"
                :aria-label="`Supprimer la conversation « ${c.title || 'Sans titre'} »`"
                @click="remove(c)"
              >
                <Icone
                  nom="corbeille"
                  :taille="16"
                />
              </button>
            </span>
          </template>
        </li>
      </ul>
    </section>

    <p
      v-if="chat.conversations.length === 0 && !chat.historyUnavailable"
      class="vide"
    >
      Aucune conversation enregistrée pour l'instant.
    </p>
  </div>
</template>

<script setup>
import { ref, computed, nextTick } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { useTableauxStore } from '../stores/tableaux.js'
import { dateRelative, grouperParDate } from '../dates.js'
import Icone from './Icone.vue'

// « ouverture » : une conversation vient d'être ouverte ou créée depuis la
// liste ; sur un écran étroit, App.vue referme alors le panneau.
const emit = defineEmits(['ouverture'])

const chat = useChatStore()
const tableaux = useTableauxStore()
const renamingId = ref(null)
const renameText = ref('')
const renameInput = ref(null)

// Regroupées par jour (Aujourd'hui, Hier…), dans l'ordre fourni par le serveur.
const groupes = computed(() => grouperParDate(chat.conversations, 'updated_at'))

// Un clic ici doit toujours montrer la conversation. Le watcher d'App.vue sur
// `currentId` ne suffit pas : il ne bouge pas quand on ré-ouvre la conversation
// déjà courante, ni quand on demande une nouvelle conversation alors que la
// courante est déjà vide — le tableau resterait alors affiché sans rien dire.
function nouvelle() {
  chat.newConversation()
  tableaux.fermer()
  emit('ouverture')
}

function ouvrir(id) {
  chat.openConversation(id)
  tableaux.fermer()
  emit('ouverture')
}

async function startRename(c) {
  renamingId.value = c.id
  renameText.value = c.title || ''
  await nextTick()
  const el = Array.isArray(renameInput.value) ? renameInput.value[0] : renameInput.value
  el?.focus()
  el?.select()
}

function cancelRename() {
  renamingId.value = null
  renameText.value = ''
}

async function confirmRename(id) {
  if (renamingId.value !== id) return
  const title = renameText.value.trim()
  renamingId.value = null
  if (!title) return
  const ok = await chat.renameConversation(id, title)
  if (!ok) alert("Le renommage n'a pas pu être enregistré.")
}

async function remove(c) {
  const label = c.title || 'Sans titre'
  if (!confirm(`Supprimer définitivement la conversation « ${label} » ?`)) return
  const ok = await chat.deleteConversation(c.id)
  if (!ok) alert("La suppression n'a pas pu être effectuée.")
}
</script>

<style scoped>
.conversations { padding: var(--e-2) var(--e-3) var(--e-4); }
.nouvelle { width: 100%; }

.indisponible {
  display: flex; align-items: flex-start; gap: var(--e-2);
  font-size: var(--t-xs); line-height: 1.5; color: var(--texte);
  background: color-mix(in srgb, var(--avert) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--avert) 35%, transparent);
  border-radius: var(--r-1); padding: 8px 10px; margin: var(--e-3) 0 0;
}
.indisponible .icone { color: var(--avert); flex-shrink: 0; margin-top: 1px; }

.groupe { margin-top: var(--e-4); }
.groupe-titre {
  margin: 0 0 var(--e-1); padding: 0 10px;
  font-size: var(--t-xs); font-weight: 600; color: var(--discret);
  text-transform: uppercase; letter-spacing: 0.04em;
}

/* minmax(0, 1fr) : sans cela, une ligne de grille s'élargit à la longueur du
   titre (non coupé) et le panneau défile horizontalement. */
.liste {
  list-style: none; padding: 0; margin: 0;
  display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px;
}
.liste li {
  display: flex; align-items: center; gap: 2px;
  border-radius: var(--r-1); padding-right: 4px;
  transition: background-color var(--transition);
}
.liste li:hover { background: var(--surface-2); }
.liste li.actif { background: var(--accent-doux); }
.ouvrir {
  flex: 1; min-width: 0; text-align: left;
  background: transparent; color: var(--texte);
  padding: 8px 10px; font-size: var(--t-s); border-radius: var(--r-1);
}
.ouvrir:hover { background: transparent; }
.titre {
  display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.actif .titre { font-weight: 600; }
.meta { display: block; font-size: 11px; color: var(--discret); margin-top: 2px; }

/* Actions visibles au survol et au focus clavier. */
.actions { display: flex; gap: 2px; opacity: 0; transition: opacity var(--transition); }
.liste li:hover .actions,
.liste li:focus-within .actions { opacity: 1; }
.action { width: 28px; height: 28px; }
.supprimer:hover { color: var(--danger); }

.champ-renommage { font-size: var(--t-s); padding: 6px 8px; margin: 2px 0; }
.vide { color: var(--discret); font-size: var(--t-xs); padding: 10px 4px; margin: var(--e-2) 0 0; line-height: 1.5; }
</style>
