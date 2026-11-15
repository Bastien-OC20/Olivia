<template>
  <div
    ref="racine"
    class="menu-deroulant"
    @keydown="surTouche"
    @focusout="surSortieFocus"
  >
    <button
      ref="declencheur"
      type="button"
      :class="classeDeclencheur"
      :aria-label="etiquette || undefined"
      :title="titre || undefined"
      :aria-haspopup="type"
      :aria-expanded="ouvert ? 'true' : 'false'"
      :aria-controls="ouvert ? idCarte : undefined"
      @click="basculer"
      @keydown="surToucheDeclencheur"
    >
      <slot name="declencheur" />
    </button>

    <div
      v-if="ouvert"
      :id="idCarte"
      ref="carte"
      class="menu"
      :class="`menu-${position}`"
      :role="type === 'dialog' ? 'dialog' : undefined"
      :aria-label="type === 'dialog' ? nomFenetre : undefined"
    >
      <!-- En-tête (ex. identité du compte) : hors du role="menu", qui ne doit
           contenir que des éléments de menu. -->
      <slot name="entete" />
      <div
        v-if="type === 'menu'"
        ref="liste"
        role="menu"
        :aria-label="nomFenetre"
      >
        <slot :fermer="fermer" />
      </div>
      <slot
        v-else
        :fermer="fermer"
      />
    </div>
  </div>
</template>

<script setup>
// Menu déroulant accessible, partagé par le compte (rail), « Plus d'actions »
// et le choix du moteur (barre du haut). Deux formes :
//  - type « menu » : les éléments du slot sont des <button role="menuitem"
//    class="menu-item" tabindex="-1"> ; Haut/Bas/Début/Fin les parcourent ;
//  - type « dialog » : fenêtre non modale (formulaire), Tab y circule librement.
// Dans les deux cas : focus dans la carte à l'ouverture, Échap ferme et rend le
// focus au déclencheur, un clic à l'extérieur ou un focus parti ailleurs ferme.
import { ref, computed, nextTick, watch, onBeforeUnmount, useId } from 'vue'
import { indexApresTouche } from '../clavier.js'

const props = defineProps({
  // Nom accessible du déclencheur ; vide si son contenu visible suffit.
  etiquette: { type: String, default: '' },
  // Nom de la carte (menu ou fenêtre) ; par défaut, celui du déclencheur.
  etiquetteFenetre: { type: String, default: '' },
  titre: { type: String, default: '' },
  type: { type: String, default: 'menu', validator: v => ['menu', 'dialog'].includes(v) },
  // « bas-fin » : sous le déclencheur, alignée à droite (barre du haut) ;
  // « droite-haut » : à droite du déclencheur, alignée en bas (rail).
  position: { type: String, default: 'bas-fin' },
  classeDeclencheur: { type: String, default: 'btn-icone' },
})

const nomFenetre = computed(() => props.etiquetteFenetre || props.etiquette)
const idCarte = `menu-${useId()}`
const ouvert = ref(false)
const racine = ref(null)
const declencheur = ref(null)
const carte = ref(null)
const liste = ref(null)

const elementsMenu = () => Array.from(liste.value?.querySelectorAll('[role="menuitem"]') || [])

const FOCUSABLES = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'

async function ouvrir(dernier = false) {
  ouvert.value = true
  await nextTick()
  if (props.type === 'menu') {
    const items = elementsMenu()
    items[dernier ? items.length - 1 : 0]?.focus()
  } else {
    const cible = carte.value?.querySelector('[data-focus-initial="true"]')
      || carte.value?.querySelector(FOCUSABLES)
    cible?.focus()
  }
}

/** Ferme la carte ; `rendreFocus` ramène le focus au déclencheur (Échap, choix
 *  d'un élément). Un clic ailleurs ou une tabulation laisse le focus où il va. */
function fermer(rendreFocus = true) {
  if (!ouvert.value) return
  ouvert.value = false
  if (rendreFocus) declencheur.value?.focus()
}

function basculer() {
  if (ouvert.value) fermer()
  else ouvrir()
}

// Motif ARIA « bouton de menu » : Bas ou Haut sur le déclencheur ouvre le menu
// sur le premier ou le dernier élément.
function surToucheDeclencheur(e) {
  if (props.type !== 'menu' || ouvert.value) return
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  ouvrir(e.key === 'ArrowUp')
}

function surTouche(e) {
  if (!ouvert.value) return
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    fermer()
    return
  }
  if (props.type !== 'menu' || !liste.value?.contains(e.target)) return
  const items = elementsMenu()
  const suivant = indexApresTouche(e.key, items.indexOf(document.activeElement), items.length)
  if (suivant === null) return
  e.preventDefault()
  items[suivant].focus()
}

function surSortieFocus(e) {
  // relatedTarget nul : la fenêtre perd le focus (autre application) ; on garde
  // le menu ouvert. Le clic sur une zone non focusable est traité plus bas.
  if (e.relatedTarget && !racine.value?.contains(e.relatedTarget)) fermer(false)
}

function surPointeur(e) {
  if (!racine.value?.contains(e.target)) fermer(false)
}

watch(ouvert, (oui) => {
  if (oui) document.addEventListener('pointerdown', surPointeur, true)
  else document.removeEventListener('pointerdown', surPointeur, true)
})

onBeforeUnmount(() => document.removeEventListener('pointerdown', surPointeur, true))

defineExpose({ fermer })
</script>

<style scoped>
.menu-deroulant { position: relative; display: inline-flex; }
.menu-bas-fin { top: calc(100% + 6px); right: 0; }
.menu-droite-haut { left: calc(100% + 8px); bottom: 0; }
</style>
