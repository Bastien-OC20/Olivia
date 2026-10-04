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

      <!-- Installation neuve : aucun compte n'existe, le formulaire ne peut pas
           aboutir. On dit comment en créer un plutôt que de laisser échouer. -->
      <div
        v-if="aucunCompte"
        class="avis premier-compte"
        role="status"
      >
        <strong>Aucun compte n'a encore été créé sur ce poste.</strong>
        La personne qui s'occupe de l'informatique doit d'abord en créer un :
        <ul>
          <li>Olivia installée : menu Démarrer, <b>Créer un compte Olivia</b> ;</li>
          <li>sur le disque portable, double-cliquer sur <b>Creer-un-compte.bat</b> ;</li>
          <li>sinon, lancer <code>ai-webapp.exe init</code> dans le dossier d'Olivia.</li>
        </ul>
        Revenez ensuite sur cette page pour vous connecter.
      </div>

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

      <p
        v-if="!aucunCompte"
        class="aide"
      >
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
// Vrai seulement si le serveur confirme qu'AUCUN compte n'existe. Une erreur
// réseau ou un fichier de comptes illisible (`comptes: null`) laisse l'écran
// habituel : ce n'est pas la même situation.
const aucunCompte = ref(false)

async function verifierComptes() {
  try {
    const r = await fetch('/api/auth/etat')
    if (r.ok) aucunCompte.value = (await r.json()).comptes === false
  } catch (e) {
    console.warn('État des comptes indisponible :', e.message)
  }
}

onMounted(() => {
  champIdentifiant.value?.focus()
  verifierComptes()
})

async function soumettre() {
  if (enCours.value) return
  erreur.value = ''
  enCours.value = true
  const res = await auth.connexion(identifiant.value, motDePasse.value)
  enCours.value = false
  if (!res.ok) {
    erreur.value = res.error
    // Le compte a pu être créé depuis l'affichage de la page : on revérifie,
    // pour retirer (ou afficher) l'explication du premier compte.
    verifierComptes()
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
.premier-compte ul { margin: 6px 0; padding-left: 18px; }
.premier-compte li { margin: 2px 0; }
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
