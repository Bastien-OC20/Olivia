<!-- eslint-disable vue/multi-word-component-names -- nom imposé par la refonte : <Icone nom="…" /> -->
<script setup>
// Icône au trait, dessinée à partir des chemins de icones.js (aucun v-html).
// Décorative par défaut (cachée aux lecteurs d'écran) ; avec `titre`, elle devient
// une image nommée — à réserver aux icônes qui portent seules un sens.
import { computed } from 'vue'
import { ICONES } from '../icones.js'

const props = defineProps({
  nom: { type: String, required: true },
  taille: { type: Number, default: 20 },
  titre: { type: String, default: '' },
})

// Nom inconnu : rien n'est affiché, sans erreur (une icône manquante ne doit
// jamais casser l'écran).
const chemins = computed(() => (Object.hasOwn(ICONES, props.nom) ? ICONES[props.nom] : []))
</script>

<template>
  <svg
    v-if="chemins.length"
    class="icone"
    viewBox="0 0 24 24"
    :width="taille"
    :height="taille"
    fill="none"
    stroke="currentColor"
    stroke-width="1.75"
    stroke-linecap="round"
    stroke-linejoin="round"
    :role="titre ? 'img' : undefined"
    :aria-hidden="titre ? undefined : 'true'"
    :focusable="titre ? undefined : 'false'"
  >
    <title v-if="titre">{{ titre }}</title>
    <path
      v-for="(d, i) in chemins"
      :key="i"
      :d="d"
    />
  </svg>
</template>
