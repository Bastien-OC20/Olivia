<template>
  <MenuDeroulant
    type="dialog"
    :etiquette="`Puissance de calcul : ${modeCourant.nom}`"
    etiquette-fenetre="Puissance de calcul et modèle d'IA"
    classe-declencheur="declencheur-moteur"
  >
    <template #declencheur>
      <Icone
        :nom="modeCourant.icone"
        :taille="16"
      />
      <span>{{ modeCourant.nom }}</span>
      <Icone
        nom="chevron-bas"
        :taille="14"
      />
    </template>

    <div class="contenu">
      <fieldset class="modes">
        <legend class="intitule">
          Puissance de calcul
        </legend>
        <label
          v-for="m in MODES"
          :key="m.id"
          class="mode"
          :class="{ actif: device === m.id }"
        >
          <input
            type="radio"
            class="sr-only"
            name="puissance-calcul"
            :value="m.id"
            :checked="device === m.id"
            :data-focus-initial="device === m.id ? 'true' : undefined"
            @change="setDevice(m.id)"
          >
          <span class="mode-icone">
            <Icone
              :nom="m.icone"
              :taille="18"
            />
          </span>
          <span class="mode-texte">
            <span class="mode-nom">{{ m.nom }}</span>
            <span class="mode-aide">{{ m.aide }}</span>
          </span>
          <Icone
            v-if="device === m.id"
            nom="coche"
            :taille="16"
            class="mode-coche"
          />
        </label>
      </fieldset>

      <div class="modele">
        <span
          class="intitule"
          aria-hidden="true"
        >Modèle d'IA</span>
        <ModelPicker />
      </div>
    </div>
  </MenuDeroulant>
</template>

<script setup>
// Choix de la puissance de calcul et du modèle d'IA (mode avancé seulement),
// dans la barre du haut. Une fenêtre non modale plutôt qu'un menu : elle
// contient un formulaire (boutons radio, liste déroulante).
import { computed } from 'vue'
import { useSettingsStore } from '../stores/settings.js'
import MenuDeroulant from './MenuDeroulant.vue'
import ModelPicker from './ModelPicker.vue'
import Icone from './Icone.vue'

const settings = useSettingsStore()

const MODES = [
  { id: 'gpu', nom: 'Rapide', icone: 'eclair', aide: 'Utilise la carte graphique — réponses plus rapides' },
  { id: 'cpu', nom: 'Standard', icone: 'puce', aide: 'Sans carte graphique — compatible avec tout ordinateur' },
  {
    id: 'leger',
    nom: 'Léger',
    icone: 'plume',
    aide: 'Ordinateur ancien ou peu puissant — modèle plus petit, réponses plus simples',
  },
]

const device = computed(() => settings.data.compute_device || 'gpu')
const modeCourant = computed(() => MODES.find(m => m.id === device.value) || MODES[0])

async function setDevice(d) {
  if (settings.data.compute_device === d) return
  settings.data.compute_device = d
  await settings.save({ compute_device: d })
}
</script>

<style scoped>
/* Déclencheur : pastille de la barre du haut. :deep() car le bouton est rendu
   par MenuDeroulant. */
:deep(.declencheur-moteur) {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border-radius: var(--r-rond);
  background: var(--surface-2);
  border: 1px solid var(--bordure);
  color: var(--texte);
  font-size: var(--t-s);
  white-space: nowrap;
}
:deep(.declencheur-moteur:hover),
:deep(.declencheur-moteur[aria-expanded="true"]) {
  background: var(--surface-3);
  border-color: var(--bordure-forte);
}

.contenu { width: 340px; max-width: calc(100vw - 32px); padding: 6px; }
.intitule {
  display: block;
  padding: 0;
  margin: 0 0 6px;
  font-size: var(--t-xs);
  font-weight: 600;
  color: var(--discret);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.modes { border: 0; padding: 0; margin: 0 0 var(--e-3); display: grid; gap: 4px; }
.mode {
  position: relative;
  display: flex;
  align-items: flex-start;
  gap: var(--e-3);
  padding: 8px 10px;
  border-radius: var(--r-2);
  border: 1px solid transparent;
  cursor: pointer;
  transition: background-color var(--transition), border-color var(--transition);
}
.mode:hover { background: var(--surface-2); }
.mode.actif { background: var(--accent-doux); border-color: var(--bordure-forte); }
/* Le bouton radio est masqué : le focus clavier s'affiche sur sa carte. */
.mode:has(input:focus-visible) {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.mode-icone {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  flex-shrink: 0;
  border-radius: var(--r-1);
  background: var(--surface-2);
  color: var(--discret);
}
.mode.actif .mode-icone { color: var(--accent-texte); background: var(--surface); }
.mode-texte { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.mode-nom { font-size: var(--t-m); font-weight: 600; }
.mode.actif .mode-nom { color: var(--accent-texte); }
.mode-aide { font-size: var(--t-xs); color: var(--discret); line-height: 1.4; }
.mode-coche { color: var(--accent-texte); flex-shrink: 0; margin-top: 2px; }
.modele { border-top: 1px solid var(--bordure); padding-top: var(--e-3); }
</style>
