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
.consent {
  position: fixed; left: 0; right: 0; bottom: 0; z-index: 1500;
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
