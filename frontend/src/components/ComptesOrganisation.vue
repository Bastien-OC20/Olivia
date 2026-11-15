<template>
  <section
    class="comptes"
    aria-label="Comptes de l'organisation"
  >
    <h3>👥 Comptes de l'organisation</h3>
    <p class="hint">
      Pour <strong>créer</strong> un compte, utilisez l'assistant « Créer un compte »
      (menu de l'application, ou raccourci du menu Démarrer). Ici, vous pouvez
      gérer les comptes existants.
    </p>

    <p
      v-if="message"
      class="msg"
      :class="messageErreur ? 'erreur' : 'succes'"
      :role="messageErreur ? 'alert' : 'status'"
    >
      {{ message }}
    </p>
    <p
      v-if="chargement"
      class="hint"
      aria-live="polite"
    >
      ⏳ Chargement des comptes…
    </p>

    <ul
      v-if="comptes.length"
      class="liste"
    >
      <li
        v-for="c in comptes"
        :key="c.id"
        class="ligne"
      >
        <div class="ident">
          <strong>{{ c.username }}</strong>
          <span class="badge">{{ libelleRole(c.role) }}</span>
          <span
            v-if="c.moi"
            class="badge moi"
          >vous</span>
          <span
            v-if="c.bloque"
            class="badge bloque"
          >bloqué</span>
          <span
            v-if="dateCreation(c.created_at)"
            class="date"
          >créé le {{ dateCreation(c.created_at) }}</span>
        </div>

        <div
          v-if="!enAction(c.id)"
          class="actions"
        >
          <button
            v-if="actionsCompte(c).reinitialiser"
            type="button"
            class="ghost"
            :disabled="occupe"
            :aria-label="`Réinitialiser le mot de passe de ${c.username}`"
            @click="ouvrir(c, 'reinit')"
          >
            Réinitialiser le mot de passe
          </button>
          <button
            v-if="actionsCompte(c).debloquer"
            type="button"
            class="ghost"
            :disabled="occupe"
            :aria-label="`Débloquer ${c.username}`"
            @click="debloquer(c)"
          >
            Débloquer
          </button>
          <button
            v-if="actionsCompte(c).changerRole"
            type="button"
            class="ghost"
            :disabled="occupe"
            :aria-label="`${libelleChangerRole(actionsCompte(c).changerRole)} : ${c.username}`"
            @click="changerRole(c, actionsCompte(c).changerRole)"
          >
            {{ libelleChangerRole(actionsCompte(c).changerRole) }}
          </button>
          <button
            v-if="actionsCompte(c).supprimer"
            type="button"
            class="danger"
            :disabled="occupe"
            :aria-label="`Supprimer le compte de ${c.username}`"
            @click="ouvrir(c, 'suppr')"
          >
            Supprimer
          </button>
        </div>

        <!-- Saisie du nouveau mot de passe, dans la page (pas de fenêtre native). -->
        <form
          v-else-if="action.mode === 'reinit'"
          class="confirmation"
          @submit.prevent="reinitialiser(c)"
        >
          <label :for="`reinit-${c.id}`">Nouveau mot de passe pour {{ c.username }}</label>
          <input
            :id="`reinit-${c.id}`"
            ref="champ"
            v-model="nouveau"
            type="password"
            autocomplete="new-password"
            :aria-describedby="`reinit-regle-${c.id}`"
          >
          <p
            :id="`reinit-regle-${c.id}`"
            class="hint"
          >
            {{ REGLE_MOT_DE_PASSE }} Ses sessions ouvertes seront fermées.
          </p>
          <div class="actions">
            <button
              type="submit"
              :disabled="occupe"
            >
              Enregistrer
            </button>
            <button
              type="button"
              class="ghost"
              @click="fermer"
            >
              Annuler
            </button>
          </div>
        </form>

        <div
          v-else
          class="confirmation"
          role="group"
          :aria-label="`Confirmer la suppression de ${c.username}`"
        >
          <p class="warn">
            {{ questionSuppression(c) }}
          </p>
          <div class="actions">
            <button
              ref="champ"
              type="button"
              class="danger"
              :disabled="occupe"
              @click="supprimer(c)"
            >
              Oui, supprimer
            </button>
            <button
              type="button"
              class="ghost"
              @click="fermer"
            >
              Annuler
            </button>
          </div>
        </div>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { ref, onMounted, nextTick } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { libelleRole } from '../roles.js'
import {
  REGLE_MOT_DE_PASSE, actionsCompte, libelleChangerRole, questionSuppression,
  dateCreation, erreurReinitialisation, messageErreurServeur, remplacerCompte,
  trierComptes,
} from '../comptes.js'

const auth = useAuthStore()
const comptes = ref([])
const chargement = ref(false)
const occupe = ref(false)
const message = ref('')
const messageErreur = ref(false)
const action = ref(null)       // { id, mode: 'reinit' | 'suppr' } : une seule ligne à la fois
const nouveau = ref('')
const champ = ref(null)

function enAction(id) { return action.value?.id === id }

function dire(texte, erreur = false) {
  message.value = texte
  messageErreur.value = erreur
}

function fermer() {
  action.value = null
  nouveau.value = ''
}

async function ouvrir(c, mode) {
  message.value = ''
  nouveau.value = ''
  action.value = { id: c.id, mode }
  await nextTick()
  const el = Array.isArray(champ.value) ? champ.value[0] : champ.value
  el?.focus()
}

/** Appel d'une route de gestion des comptes. Une réponse qui arrive après un
 *  changement de compte connecté est ignorée (renvoie null). */
async function appeler(url, methode, corps) {
  const moi = auth.identite?.user_id
  occupe.value = true
  try {
    const r = await fetch(url, {
      method: methode,
      headers: corps ? { 'Content-Type': 'application/json' } : undefined,
      body: corps ? JSON.stringify(corps) : undefined,
    })
    const donnees = await r.json().catch(() => null)
    if (moi !== auth.identite?.user_id) return null
    if (!r.ok) {
      dire(messageErreurServeur(r.status, donnees, r.headers.get('Retry-After')), true)
      return null
    }
    return donnees ?? {}
  } catch (e) {
    console.error('Gestion des comptes impossible :', e)
    if (moi === auth.identite?.user_id) {
      dire('Oliv\'IA ne répond pas. Vérifiez qu\'elle est bien démarrée, puis réessayez.', true)
    }
    return null
  } finally {
    occupe.value = false
  }
}

async function charger() {
  const moi = auth.identite?.user_id
  chargement.value = true
  const donnees = await appeler('/api/comptes', 'GET')
  chargement.value = false
  if (donnees && moi === auth.identite?.user_id) {
    comptes.value = trierComptes(donnees.comptes || [])
  }
}

async function reinitialiser(c) {
  const probleme = erreurReinitialisation(nouveau.value)
  if (probleme) { dire(probleme, true); return }
  const ok = await appeler(`/api/comptes/${encodeURIComponent(c.id)}/mot-de-passe`, 'POST',
    { nouveau: nouveau.value })
  if (!ok) return
  fermer()
  dire(`Mot de passe de « ${c.username} » modifié. Ses sessions ouvertes ont été fermées.`)
}

async function debloquer(c) {
  message.value = ''
  const vue = await appeler(`/api/comptes/${encodeURIComponent(c.id)}/debloquer`, 'POST')
  if (!vue) return
  comptes.value = trierComptes(remplacerCompte(comptes.value, { ...vue, id: c.id, bloque: false }))
  dire(`Le compte « ${c.username} » est débloqué.`)
}

async function changerRole(c, role) {
  message.value = ''
  const vue = await appeler(`/api/comptes/${encodeURIComponent(c.id)}/role`, 'PUT', { role })
  if (!vue) return
  comptes.value = trierComptes(remplacerCompte(comptes.value, { ...vue, id: c.id, role }))
  dire(`« ${c.username} » est maintenant ${libelleRole(role).toLowerCase()}.`)
}

async function supprimer(c) {
  const ok = await appeler(`/api/comptes/${encodeURIComponent(c.id)}`, 'DELETE')
  if (!ok) return
  comptes.value = comptes.value.filter(x => x.id !== c.id)
  fermer()
  dire(`Le compte « ${c.username} » a été supprimé.`)
}

onMounted(charger)
</script>

<style scoped>
.liste { list-style: none; margin: 12px 0 0; padding: 0; }
.ligne { padding: 10px 0; border-bottom: 1px solid var(--border); }
.ident { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.badge { font-size: 11px; padding: 2px 8px; border-radius: 10px;
         background: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
.badge.moi { border-color: var(--accent); }
.badge.bloque { color: var(--warn); border-color: var(--warn); }
.date { font-size: 12px; color: var(--muted); }
.actions { display: flex; flex-wrap: wrap; gap: 8px; }
.actions .ghost { background: var(--panel-2); color: var(--text); }
.danger { background: var(--danger); }
.confirmation label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
.confirmation input { width: 100%; margin-bottom: 8px; }
.hint, .warn { font-size: 12px; padding: 10px; border-radius: 4px; line-height: 1.5; }
.hint { color: var(--muted); background: var(--panel-2); }
.warn { color: var(--warn); background: rgba(245,158,11,0.08);
        border: 1px solid rgba(245,158,11,0.3); margin: 0 0 8px; }
.msg { font-size: 13px; padding: 10px; border-radius: 4px; margin: 12px 0; }
.erreur { color: var(--danger); background: rgba(239,68,68,0.08);
          border: 1px solid rgba(239,68,68,0.3); }
.succes { color: var(--text); background: rgba(34,197,94,0.1);
          border: 1px solid rgba(34,197,94,0.35); }
h3 { font-size: 14px; margin: 0 0 8px; }
</style>
