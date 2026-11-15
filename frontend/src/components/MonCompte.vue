<template>
  <form
    class="mon-compte"
    aria-label="Changer mon mot de passe"
    @submit.prevent="changer"
  >
    <h3>🔑 Mon mot de passe</h3>
    <p class="hint">
      Connectée comme <strong>{{ auth.identite?.username }}</strong>
      ({{ libelleRole(auth.role).toLowerCase() }}).
      Règle du mot de passe : {{ REGLE_MOT_DE_PASSE }}
    </p>

    <div class="field">
      <label for="mdp-ancien">Mot de passe actuel</label>
      <input
        id="mdp-ancien"
        v-model="ancien"
        type="password"
        autocomplete="current-password"
      >
    </div>
    <div class="field">
      <label for="mdp-nouveau">Nouveau mot de passe</label>
      <input
        id="mdp-nouveau"
        v-model="nouveau"
        type="password"
        autocomplete="new-password"
        aria-describedby="mdp-regle"
      >
      <p
        id="mdp-regle"
        class="hint"
      >
        {{ REGLE_MOT_DE_PASSE }}
      </p>
    </div>
    <div class="field">
      <label for="mdp-confirmation">Confirmation du nouveau mot de passe</label>
      <input
        id="mdp-confirmation"
        v-model="confirmation"
        type="password"
        autocomplete="new-password"
      >
    </div>

    <button
      type="submit"
      :disabled="enCours"
    >
      {{ enCours ? '⏳ Modification…' : 'Changer mon mot de passe' }}
    </button>

    <p
      v-if="erreur"
      class="msg erreur"
      role="alert"
    >
      {{ erreur }}
    </p>
    <p
      v-if="succes"
      class="msg succes"
      role="status"
    >
      {{ succes }}
    </p>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { libelleRole } from '../roles.js'
import {
  REGLE_MOT_DE_PASSE, erreurFormulaireMotDePasse, messageMotDePasseChange,
  messageErreurServeur,
} from '../comptes.js'

const auth = useAuthStore()
const ancien = ref('')
const nouveau = ref('')
const confirmation = ref('')
const enCours = ref(false)
const erreur = ref('')
const succes = ref('')

async function changer() {
  erreur.value = ''
  succes.value = ''
  const probleme = erreurFormulaireMotDePasse({
    ancien: ancien.value, nouveau: nouveau.value, confirmation: confirmation.value,
  })
  if (probleme) {
    erreur.value = probleme
    return
  }
  // Une réponse tardive ne doit pas s'afficher pour un autre compte.
  const compte = auth.identite?.user_id
  enCours.value = true
  try {
    const r = await fetch('/api/auth/mot-de-passe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ancien: ancien.value, nouveau: nouveau.value }),
    })
    const corps = await r.json().catch(() => null)
    if (compte !== auth.identite?.user_id) return
    if (!r.ok) {
      erreur.value = messageErreurServeur(r.status, corps, r.headers.get('Retry-After'))
      return
    }
    succes.value = messageMotDePasseChange(corps?.sessions_fermees)
    ancien.value = ''
    nouveau.value = ''
    confirmation.value = ''
  } catch (e) {
    console.error('Changement de mot de passe impossible :', e)
    if (compte === auth.identite?.user_id) {
      erreur.value = 'Oliv\'IA ne répond pas. Vérifiez qu\'elle est bien démarrée, puis réessayez.'
    }
  } finally {
    enCours.value = false
  }
}
</script>

<style scoped>
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
.field input { width: 100%; }
.hint { font-size: 12px; padding: 10px; border-radius: 4px; line-height: 1.5;
        color: var(--muted); background: var(--panel-2); }
.msg { font-size: 13px; padding: 10px; border-radius: 4px; margin-top: 12px; }
.erreur { color: var(--danger); background: rgba(239,68,68,0.08);
          border: 1px solid rgba(239,68,68,0.3); }
.succes { color: var(--text); background: rgba(34,197,94,0.1);
          border: 1px solid rgba(34,197,94,0.35); }
h3 { font-size: 14px; margin: 0 0 8px; }
</style>
