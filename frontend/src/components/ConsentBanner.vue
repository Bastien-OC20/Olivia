<template>
  <Transition name="slide-up">
    <div
      v-if="visible"
      class="consent carte"
      role="region"
      aria-label="Information sur la confidentialité (RGPD)"
    >
      <div class="txt">
        <strong>
          <Icone
            nom="cadenas"
            :taille="18"
            class="cadenas"
          />
          Confidentialité
        </strong>
        <span>
          Cette application fonctionne <b>100 % en local</b> : vos conversations, fichiers et
          identifiants restent sur cette machine et ne sont envoyés à aucun serveur externe.
          Réglages et conversations sont enregistrés sur ce poste, dans le dossier des données
          d'Oliv'IA. Vous pouvez à tout
          moment exporter ou supprimer vos données depuis <b>Paramètres → Confidentialité</b>.
        </span>
      </div>
      <div class="btns">
        <button
          type="button"
          class="btn btn-secondaire"
          @click="openPrivacy"
        >
          Gérer mes données
        </button>
        <button
          type="button"
          class="btn btn-primaire"
          @click="accept"
        >
          J'ai compris
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { useSettingsStore } from '../stores/settings.js'
import Icone from './Icone.vue'

const settings = useSettingsStore()
const emit = defineEmits(['open-privacy'])
const visible = computed(() => settings.charge && settings.data.privacy_consent === false)

async function accept() {
  settings.data.privacy_consent = true
  await settings.save({ privacy_consent: true })
}
function openPrivacy() { emit('open-privacy') }
</script>

<style scoped>
/* Volontairement dans le flux (PAS position:fixed) : la colonne principale
   d'App.vue est un flex-column sur toute la hauteur de l'écran, donc cette carte
   y prend sa place sous la conversation et réduit d'autant sa hauteur. Elle a
   l'air de flotter (marges, ombre) sans recouvrir quoi que ce soit : en position
   fixe, la bannière flottait par-dessus le bas de l'écran et interceptait
   silencieusement les clics sur le champ de saisie et le bouton « Envoyer » du
   chat, sans aucun retour visuel. */
.consent {
  display: flex; align-items: center; gap: var(--e-4); flex-wrap: wrap;
  flex-shrink: 0;
  width: calc(100% - 2 * var(--e-4));
  max-width: 720px;
  margin: var(--e-2) auto var(--e-4);
  padding: var(--e-4) var(--e-5);
  box-shadow: var(--ombre-2);
}
.txt { flex: 1; min-width: 260px; font-size: var(--t-s); line-height: 1.5; color: var(--texte); }
.txt strong { display: flex; align-items: center; gap: var(--e-2); margin-bottom: 4px; }
.cadenas { color: var(--accent-texte); flex-shrink: 0; }
.txt span { color: var(--discret); }
.txt code {
  background: var(--surface-2); padding: 1px 5px; border-radius: var(--r-1); font-family: monospace;
}
.btns { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
