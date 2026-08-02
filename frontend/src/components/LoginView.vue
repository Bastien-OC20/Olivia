<template>
  <div class="ecran">
    <form
      class="carte"
      @submit.prevent="soumettre"
    >
      <img
        :src="logoUrl"
        alt=""
        class="logo"
      >
      <h1 class="titre">
        Olivia
      </h1>
      <p class="sous-titre">
        votre assistante — connectez-vous pour commencer
      </p>

      <p
        v-if="auth.avis"
        class="avis"
        role="status"
      >
        {{ auth.avis }}
      </p>

      <label for="champ-identifiant">Identifiant</label>
      <input
        id="champ-identifiant"
        ref="champIdentifiant"
        v-model="identifiant"
        type="text"
        autocomplete="username"
        :disabled="enCours"
        required
      >

      <label for="champ-motdepasse">Mot de passe</label>
      <input
        id="champ-motdepasse"
        v-model="motDePasse"
        type="password"
        autocomplete="current-password"
        :disabled="enCours"
        required
      >

      <p
        v-if="erreur"
        class="erreur"
        role="alert"
      >
        {{ erreur }}
      </p>

      <button
        type="submit"
        :disabled="enCours"
      >
        {{ enCours ? 'Connexion en cours…' : 'Se connecter' }}
      </button>

      <p class="aide">
        Pas encore d'identifiant ? Demandez-le à la personne qui s'occupe de
        l'informatique : les comptes sont créés par elle.
      </p>
    </form>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import logoUrl from '../assets/logo-mark.png'

const auth = useAuthStore()

const identifiant = ref('')
const motDePasse = ref('')
const erreur = ref('')
const enCours = ref(false)
const champIdentifiant = ref(null)

onMounted(() => champIdentifiant.value?.focus())

async function soumettre() {
  if (enCours.value) return
  erreur.value = ''
  enCours.value = true
  const res = await auth.connexion(identifiant.value, motDePasse.value)
  enCours.value = false
  if (!res.ok) {
    erreur.value = res.error
    // Seul le mot de passe est vidé : réécrire son identifiant à chaque faute
    // de frappe serait pénible, et il n'a rien de secret.
    motDePasse.value = ''
  }
  // En cas de succès, rien à faire ici : `auth.connecte` passe à vrai et App.vue
  // remplace cet écran par l'application.
}
</script>

<style scoped>
.ecran {
  height: 100vh;
  display: flex; align-items: center; justify-content: center;
  padding: 20px;
  background: var(--bg);
}
.carte {
  width: 100%; max-width: 380px;
  display: flex; flex-direction: column; gap: 6px;
  padding: 28px 28px 24px;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 10px 40px rgba(0,0,0,0.35);
}
.logo {
  width: 48px; height: 48px; align-self: center;
  border-radius: 10px; background: #fff; padding: 2px;
}
.titre { margin: 10px 0 0; text-align: center; font-size: 24px; }
.sous-titre {
  margin: 0 0 18px; text-align: center;
  font-size: 13px; color: var(--muted);
}
label { margin-top: 12px; font-size: 13px; color: var(--muted); }
button[type="submit"] { margin-top: 20px; padding: 10px 16px; font-size: 15px; }
.avis, .erreur {
  margin: 0 0 4px; padding: 10px 12px;
  border-radius: 6px; font-size: 13px; line-height: 1.4;
}
.avis { background: var(--panel-2); color: var(--text); border: 1px solid var(--border); }
.erreur {
  margin-top: 14px;
  background: rgba(239,68,68,0.12); color: var(--text);
  border: 1px solid var(--danger);
}
.aide {
  margin: 16px 0 0; text-align: center;
  font-size: 12px; line-height: 1.5; color: var(--muted);
}
</style>
