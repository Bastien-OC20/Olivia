<template>
  <div class="tableaux">
    <button
      type="button"
      class="btn btn-primaire nouveau"
      @click="nouveau"
    >
      <Icone
        nom="plus"
        :taille="18"
      />
      Nouveau tableau blanc
    </button>

    <p
      v-if="tableaux.indisponible"
      class="indisponible"
      aria-live="polite"
    >
      <Icone
        nom="alerte"
        :taille="16"
      />
      <span>Les tableaux ne sont pas disponibles pour le moment.</span>
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
        :aria-label="`Tableaux blancs enregistrés : ${g.libelle}`"
      >
        <li
          v-for="t in g.elements"
          :key="t.id"
          :class="{ actif: t.id === tableaux.courant?.id }"
        >
          <template v-if="renommageId === t.id">
            <label
              :for="`renommer-${t.id}`"
              class="sr-only"
            >Nouveau titre du tableau</label>
            <input
              :id="`renommer-${t.id}`"
              ref="champRenommage"
              v-model="texteRenommage"
              class="champ-renommage"
              maxlength="80"
              @keydown.enter.prevent="validerRenommage(t.id)"
              @keydown.esc.prevent="annulerRenommage"
              @blur="validerRenommage(t.id)"
            >
          </template>
          <template v-else>
            <button
              type="button"
              class="ouvrir"
              :aria-current="t.id === tableaux.courant?.id ? 'true' : undefined"
              @click="ouvrir(t.id)"
            >
              <span class="titre">{{ t.titre }}</span>
              <span class="meta">
                {{ dateRelative(t.modifie_le) }}
                · {{ t.elements }} élément{{ t.elements > 1 ? 's' : '' }}
              </span>
            </button>
            <span class="actions">
              <button
                type="button"
                class="btn-icone action"
                :aria-label="`Renommer le tableau « ${t.titre} »`"
                @click="commencerRenommage(t)"
              >
                <Icone
                  nom="crayon"
                  :taille="16"
                />
              </button>
              <button
                type="button"
                class="btn-icone action supprimer"
                :aria-label="`Supprimer le tableau « ${t.titre} »`"
                @click="supprimer(t)"
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
      v-if="tableaux.liste.length === 0 && !tableaux.indisponible"
      class="vide"
    >
      Aucun tableau pour l'instant. Un tableau blanc sert à dessiner un schéma, un plan,
      une carte mentale ou un organigramme ; il est enregistré automatiquement.
    </p>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { useTableauxStore } from '../stores/tableaux.js'
import { dateRelative, grouperParDate } from '../dates.js'
import Icone from './Icone.vue'

// « ouverture » : un tableau vient d'être ouvert ou créé depuis la liste ; sur
// un écran étroit, App.vue referme alors le panneau.
const emit = defineEmits(['ouverture'])

const tableaux = useTableauxStore()
const renommageId = ref(null)
const texteRenommage = ref('')
const champRenommage = ref(null)

// Regroupés par jour (Aujourd'hui, Hier…), dans l'ordre fourni par le serveur.
const groupes = computed(() => grouperParDate(tableaux.liste, 'modifie_le'))

onMounted(() => tableaux.charger())

function nouveau() {
  tableaux.nouveau()
  emit('ouverture')
}

function ouvrir(id) {
  tableaux.ouvrir(id)
  emit('ouverture')
}

async function commencerRenommage(t) {
  renommageId.value = t.id
  texteRenommage.value = t.titre
  await nextTick()
  const el = Array.isArray(champRenommage.value) ? champRenommage.value[0] : champRenommage.value
  el?.focus()
  el?.select()
}

function annulerRenommage() {
  renommageId.value = null
  texteRenommage.value = ''
}

async function validerRenommage(id) {
  if (renommageId.value !== id) return
  const titre = texteRenommage.value.trim()
  renommageId.value = null
  if (!titre) return
  if (!(await tableaux.renommer(id, titre))) alert("Le renommage n'a pas pu être enregistré.")
}

async function supprimer(t) {
  if (!confirm(`Supprimer définitivement le tableau « ${t.titre} » ?`)) return
  if (!(await tableaux.supprimer(t.id))) alert("La suppression n'a pas pu être effectuée.")
}
</script>

<style scoped>
.tableaux { padding: var(--e-2) var(--e-3) var(--e-4); }
.nouveau { width: 100%; }

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
.titre { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
