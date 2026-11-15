<template>
  <div
    class="zone-saisie"
    :class="{ accueil }"
  >
    <div class="saisie-carte">
      <label
        :for="idTexte"
        class="sr-only"
      >Votre demande à Oliv'IA</label>
      <textarea
        :id="idTexte"
        ref="texteEl"
        :value="modelValue"
        placeholder="Écrivez votre demande à Oliv'IA…"
        :disabled="enCours"
        :rows="accueil ? 2 : 1"
        @input="surSaisie"
        @keydown.enter.exact.prevent="emit('envoyer')"
      />
      <div class="saisie-actions">
        <div class="saisie-gauche">
          <button
            type="button"
            class="btn-icone"
            aria-label="Joindre un document"
            title="Joindre un document"
            @click="emit('joindre')"
          >
            <Icone nom="trombone" />
          </button>
          <button
            type="button"
            class="interrupteur"
            :class="{ actif: recherche }"
            :aria-pressed="recherche"
            :disabled="enCours"
            title="Chercher sur le web avant de répondre, et citer les sources"
            @click="emit('update:recherche', !recherche)"
          >
            <Icone
              nom="globe"
              :taille="16"
            />
            Recherche web
          </button>
        </div>
        <button
          v-if="enCours"
          type="button"
          class="bouton-rond"
          aria-label="Arrêter la réponse"
          title="Arrêter la réponse"
          @click="emit('stop')"
        >
          <Icone
            nom="stop"
            :taille="18"
          />
        </button>
        <button
          v-else
          type="button"
          class="bouton-rond"
          aria-label="Envoyer"
          title="Envoyer"
          :disabled="!modelValue.trim()"
          @click="emit('envoyer')"
        >
          <Icone
            nom="envoyer"
            :taille="18"
          />
        </button>
      </div>
    </div>
    <p class="saisie-aide">
      Entrée pour envoyer · Maj+Entrée pour aller à la ligne
    </p>
    <p
      v-if="recherche"
      class="saisie-aide"
    >
      Oliv'IA consultera le web avant de répondre, et indiquera ses sources.
    </p>
  </div>
</template>

<script setup>
import { ref, watch, nextTick, onMounted, useId } from 'vue'
import Icone from './Icone.vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
  recherche: { type: Boolean, default: false },
  enCours: { type: Boolean, default: false },
  // Variante centrale de l'écran d'accueil : plus grande, avec la lueur.
  accueil: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'update:recherche', 'envoyer', 'stop', 'joindre'])

const idTexte = `saisie-${useId()}`
const texteEl = ref(null)

// Hauteur maximale de la zone de texte : au-delà, elle défile.
const HAUTEUR_MAX = 220

/** La zone grandit avec le texte, jusqu'à HAUTEUR_MAX. */
function ajusterHauteur() {
  const el = texteEl.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = `${Math.min(el.scrollHeight, HAUTEUR_MAX)}px`
  el.style.overflowY = el.scrollHeight > HAUTEUR_MAX ? 'auto' : 'hidden'
}

function surSaisie(e) {
  emit('update:modelValue', e.target.value)
}

// Le texte change aussi depuis le parent (envoi, carte « préremplir ») : la
// hauteur suit dans tous les cas.
watch(() => props.modelValue, async () => {
  await nextTick()
  ajusterHauteur()
})
onMounted(ajusterHauteur)

/** Donne le focus à la zone de texte, curseur à la fin. */
function focus() {
  const el = texteEl.value
  if (!el) return
  el.focus()
  const fin = el.value.length
  el.setSelectionRange(fin, fin)
  el.scrollTop = el.scrollHeight
}

defineExpose({ focus })
</script>

<style scoped>
.zone-saisie { width: 100%; }

.saisie-carte {
  display: flex;
  flex-direction: column;
  gap: var(--e-2);
  padding: var(--e-3) var(--e-3) var(--e-2) var(--e-4);
  background: var(--surface);
  border: 1px solid var(--bordure);
  border-radius: var(--r-4);
  box-shadow: var(--ombre-1);
  transition: border-color var(--transition), box-shadow var(--transition);
}
/* Le focus se voit sur la carte entière (la zone de texte n'a pas de bordure). */
.saisie-carte:focus-within {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-doux);
}
.accueil .saisie-carte {
  padding: var(--e-4) var(--e-4) var(--e-3) var(--e-5);
  box-shadow: var(--lueur);
}
.accueil .saisie-carte:focus-within {
  border-color: var(--accent);
  box-shadow: var(--lueur), 0 0 0 3px var(--accent-doux);
}

.saisie-carte textarea {
  display: block;
  width: 100%;
  min-height: 24px;
  max-height: 220px;
  padding: var(--e-1) 0;
  background: transparent;
  border: none;
  border-radius: 0;
  box-shadow: none;
  color: var(--texte);
  font-size: var(--t-m);
  line-height: 1.5;
  resize: none;
  overflow-y: hidden;
}
.accueil .saisie-carte textarea { font-size: var(--t-l); min-height: 52px; }
.saisie-carte textarea:focus,
.saisie-carte textarea:focus-visible {
  outline: none;
  border: none;
  box-shadow: none;
}
.saisie-carte textarea::placeholder { color: var(--discret); }
.saisie-carte textarea:disabled { cursor: not-allowed; opacity: 0.6; }

.saisie-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--e-2);
}
.saisie-gauche { display: flex; align-items: center; gap: var(--e-2); min-width: 0; }

.interrupteur {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-radius: var(--r-rond);
  background: transparent;
  color: var(--discret);
  border: 1px solid var(--bordure);
  font-size: var(--t-s);
  font-weight: 500;
}
.interrupteur:hover:not(:disabled) {
  background: var(--surface-2);
  border-color: var(--bordure-forte);
  color: var(--texte);
}
.interrupteur.actif,
.interrupteur.actif:hover:not(:disabled) {
  background: var(--accent-doux);
  color: var(--accent-texte);
  border-color: var(--accent-texte);
}

.bouton-rond {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 38px;
  height: 38px;
  padding: 0;
  border-radius: var(--r-rond);
  background: var(--accent);
  color: var(--sur-accent);
}
.bouton-rond:hover:not(:disabled) { background: var(--accent-survol); }

.saisie-aide {
  margin: var(--e-2) 0 0;
  padding: 0 var(--e-2);
  font-size: var(--t-xs);
  color: var(--discret);
  text-align: center;
  line-height: 1.4;
}
.saisie-aide + .saisie-aide { margin-top: 2px; }
</style>
