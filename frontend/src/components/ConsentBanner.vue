<template>
  <Transition name="slide-up">
    <div
      v-if="visible"
      class="consent"
      role="region"
      aria-label="Information sur la confidentialité (RGPD)"
    >
      <div class="txt">
        <strong>🔒 Confidentialité</strong>
        <span>
          Cette application fonctionne <b>100 % en local</b> : vos conversations, fichiers et
          identifiants restent sur cette machine et ne sont envoyés à aucun serveur externe.
          Les paramètres sont stockés dans <code>backend/settings.json</code>. Vous pouvez à tout
          moment exporter ou supprimer vos données depuis <b>Paramètres → Confidentialité</b>.
        </span>
      </div>
      <div class="btns">
        <button
          class="ghost"
          @click="openPrivacy"
        >
          Gérer mes données
        </button>
        <button @click="accept">
          J'ai compris
        </button>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { computed } from 'vue'
import { useSettingsStore } from '../stores/settings.js'

const settings = useSettingsStore()
const emit = defineEmits(['open-privacy'])
const visible = computed(() => settings.data.privacy_consent === false)

async function accept() {
  settings.data.privacy_consent = true
  await settings.save({ privacy_consent: true })
}
function openPrivacy() { emit('open-privacy') }
</script>

<style scoped>
/* Volontairement dans le flux (PAS position:fixed) : `.layout` (App.vue) est un
   flex-column sur toute la hauteur de l'écran, donc cette barre y prend sa place
   comme n'importe quel enfant et réduit d'autant la hauteur du panneau de
   conversation au-dessus. En position fixe, la bannière flottait par-dessus le
   bas de l'écran et interceptait silencieusement les clics sur le champ de
   saisie et le bouton « Envoyer » du chat, sans aucun retour visuel. */
.consent {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  padding: 14px 20px; background: var(--panel);
  border-top: 1px solid var(--border);
  box-shadow: 0 -4px 20px rgba(0,0,0,0.35);
}
.txt { flex: 1; min-width: 280px; font-size: 13px; line-height: 1.5; color: var(--text); }
.txt strong { display: block; margin-bottom: 4px; }
.txt span { color: var(--muted); }
.txt code { background: var(--panel-2); padding: 1px 5px; border-radius: 3px; font-family: monospace; }
.btns { display: flex; gap: 10px; }
.btns .ghost { background: var(--panel-2); color: var(--text); }
</style>
