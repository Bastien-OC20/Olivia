<template>
  <form
    class="mon-compte"
    aria-label="Changer mon mot de passe"
    @submit.prevent="changer"
  >
    <h3>
      <Icone
        nom="cadenas"
        :taille="18"
      />
      Mon mot de passe
    </h3>
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
      class="btn btn-primaire"
      :disabled="enCours"
    >
      <Icone
        :nom="enCours ? 'actualiser' : 'coche'"
        :taille="16"
      />
      {{ enCours ? 'Modification…' : 'Changer mon mot de passe' }}
    </button>

    <p
      v-if="erreur"
      class="msg erreur"
      role="alert"
    >
      <Icone
        nom="alerte"
        :taille="16"
      />
      <span>{{ erreur }}</span>
    </p>
    <p
      v-if="succes"
      class="msg succes"
      role="status"
    >
      <Icone
        nom="coche"
        :taille="16"
      />
      <span>{{ succes }}</span>
    </p>
  </form>
</template>

<script setup>
import { ref } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { libelleRole } from '../roles.js'
import Icone from './Icone.vue'
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
/* Carte légère, comme les groupes de réglages de la fenêtre des Paramètres. */
.mon-compte {
  background: var(--surface);
  border: 1px solid var(--bordure);
  border-radius: var(--r-3);
  padding: var(--e-4) var(--e-5);
}
.field { margin-bottom: var(--e-4); }
.field label {
  display: block; font-size: var(--t-s); font-weight: 500; color: var(--texte);
  margin-bottom: 4px;
}
.field input { width: 100%; }
.hint { font-size: var(--t-xs); color: var(--discret); line-height: 1.5; margin: 6px 0 var(--e-3); }
.field .hint { margin-bottom: 0; }
.msg {
  display: flex; gap: var(--e-2); align-items: flex-start;
  font-size: var(--t-s); line-height: 1.5; color: var(--texte);
  padding: var(--e-3); border-radius: var(--r-2); margin-top: var(--e-3);
}
.msg .icone { flex-shrink: 0; margin-top: 2px; }
.erreur {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--danger) 45%, transparent);
}
.erreur .icone { color: var(--danger); }
.succes {
  background: color-mix(in srgb, var(--ok) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--ok) 45%, transparent);
}
.succes .icone { color: var(--ok); }
h3 {
  display: flex; align-items: center; gap: var(--e-2);
  font-size: var(--t-m); font-weight: 600; margin: 0 0 var(--e-2);
}
h3 .icone { color: var(--accent-texte); }
</style>
