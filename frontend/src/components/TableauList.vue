<template>
  <div class="tableaux">
    <button
      class="nouveau"
      @click="tableaux.nouveau()"
    >
      ＋ Nouveau tableau blanc
    </button>

    <p
      v-if="tableaux.indisponible"
      class="indisponible"
      aria-live="polite"
    >
      ⚠️ Les tableaux ne sont pas disponibles pour le moment.
    </p>

    <ul
      class="liste"
      aria-label="Tableaux blancs enregistrés"
    >
      <li
        v-for="t in tableaux.liste"
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
            class="champ"
            maxlength="80"
            @keydown.enter.prevent="validerRenommage(t.id)"
            @keydown.esc.prevent="annulerRenommage"
            @blur="validerRenommage(t.id)"
          >
        </template>
        <template v-else>
          <button
            class="ouvrir"
            :aria-current="t.id === tableaux.courant?.id ? 'true' : undefined"
            @click="tableaux.ouvrir(t.id)"
          >
            <span class="titre">🎨 {{ t.titre }}</span>
            <span class="meta">
              {{ dateRelative(t.modifie_le) }}
              · {{ t.elements }} élément{{ t.elements > 1 ? 's' : '' }}
            </span>
          </button>
          <span class="actions">
            <button
              class="icone"
              :aria-label="`Renommer le tableau « ${t.titre} »`"
              @click="commencerRenommage(t)"
            >
              ✏️
            </button>
            <button
              class="icone"
              :aria-label="`Supprimer le tableau « ${t.titre} »`"
              @click="supprimer(t)"
            >
              🗑
            </button>
          </span>
        </template>
      </li>
      <li
        v-if="tableaux.liste.length === 0 && !tableaux.indisponible"
        class="vide"
      >
        Aucun tableau pour l'instant. Un tableau blanc sert à dessiner un schéma, un plan,
        une carte mentale ou un organigramme ; il est enregistré automatiquement.
      </li>
    </ul>
  </div>
</template>

<script setup>
import { ref, nextTick, onMounted } from 'vue'
import { useTableauxStore } from '../stores/tableaux.js'

const tableaux = useTableauxStore()
const renommageId = ref(null)
const texteRenommage = ref('')
const champRenommage = ref(null)

onMounted(() => tableaux.charger())

const rtf = new Intl.RelativeTimeFormat('fr', { numeric: 'auto' })
const UNITES = [['year', 31536000], ['month', 2592000], ['week', 604800],
  ['day', 86400], ['hour', 3600], ['minute', 60]]

function dateRelative(ts) {
  if (!ts) return ''
  const secondes = (Number(ts) * 1000 - Date.now()) / 1000
  for (const [unite, taille] of UNITES) {
    if (Math.abs(secondes) >= taille) return rtf.format(Math.round(secondes / taille), unite)
  }
  return "à l'instant"
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
.tableaux { padding: 12px; }
.nouveau { width: 100%; font-size: 13px; }
.indisponible {
  font-size: 12px; line-height: 1.5; color: var(--warn);
  background: rgba(245, 158, 11, 0.08); border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: 6px; padding: 8px 10px; margin: 10px 0 0;
}
.liste { list-style: none; padding: 0; margin: 10px 0 0; }
.liste li {
  display: flex; align-items: center; gap: 4px;
  border-radius: 6px; padding: 2px 4px 2px 0;
}
.liste li:hover { background: var(--panel-2); }
.liste li.actif { background: var(--panel-2); box-shadow: inset 2px 0 0 var(--accent); }
.ouvrir {
  flex: 1; min-width: 0; text-align: left;
  background: transparent; color: var(--text);
  padding: 8px 10px; font-size: 13px; border-radius: 6px;
}
.titre { display: block; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.meta { display: block; font-size: 11px; color: var(--muted); margin-top: 2px; }
.actions { display: flex; gap: 2px; opacity: 0; transition: opacity 0.15s ease; }
.liste li:hover .actions,
.liste li:focus-within .actions { opacity: 1; }
.icone { background: transparent; padding: 4px 6px; font-size: 13px; line-height: 1; }
.champ { font-size: 13px; padding: 6px 8px; }
.vide { color: var(--muted); font-size: 12px; padding: 10px 4px; line-height: 1.5; }
.vide:hover { background: transparent; }
</style>
