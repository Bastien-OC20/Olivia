<template>
  <div class="ecran">
    <form
      class="carte formulaire"
      @submit.prevent="soumettre"
    >
      <img
        :src="logoUrl"
        alt=""
        class="logo"
      >
      <h1 class="titre">
        Oliv'IA
      </h1>
      <p class="sous-titre">
        votre assistante — connectez-vous pour commencer
      </p>

      <p
        v-if="auth.avis"
        class="avis"
        role="status"
      >
        <Icone
          nom="alerte"
          :taille="16"
        />
        <span>{{ auth.avis }}</span>
      </p>

      <!-- Installation neuve : aucun compte n'existe, le formulaire ne peut pas
           aboutir. On dit comment en créer un plutôt que de laisser échouer. -->
      <div
        v-if="aucunCompte"
        class="info premier-compte"
        role="status"
      >
        <Icone
          nom="utilisateur"
          :taille="18"
          class="info-icone"
        />
        <div>
          <strong>Aucun compte n'a encore été créé sur ce poste.</strong>
          La personne qui s'occupe de l'informatique doit d'abord en créer un.
          <!-- Application de bureau : l'assistant s'ouvre directement (desktop/preload.js). -->
          <template v-if="bureau">
            <button
              type="button"
              class="btn btn-secondaire"
              @click="ouvrirAssistant"
            >
              Ouvrir l'assistant de création de compte
            </button>
            <span class="discret">
              (aussi dans le menu, et sur l'icône d'Oliv'IA : « Créer un compte… »)
            </span>
          </template>
          <ul v-else>
            <li>Oliv'IA installée : menu Démarrer, <b>Créer un compte Oliv'IA</b> ;</li>
            <li>sur le disque portable, double-cliquer sur <b>Creer-un-compte.bat</b> ;</li>
            <li>sinon, lancer <code>ai-webapp.exe init</code> dans le dossier d'Oliv'IA.</li>
          </ul>
          Revenez ensuite sur cette page pour vous connecter.
        </div>
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
        <Icone
          nom="alerte"
          :taille="16"
        />
        <span>{{ erreur }}</span>
      </p>

      <button
        type="submit"
        class="btn btn-primaire connexion"
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
import Icone from './Icone.vue'
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
// Exposé par l'application de bureau (desktop/preload.js) ; absent dans un
// navigateur ordinaire.
const bureau = typeof window !== 'undefined' ? window.oliviaBureau : undefined

function ouvrirAssistant() {
  bureau?.creerCompte()
}

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
  padding: var(--e-5);
  overflow-y: auto;
}
/* Fond : celui du body (halo) ; la carte est centrée dessus. */
.formulaire {
  width: 100%; max-width: 400px;
  margin: auto;
  display: flex; flex-direction: column; gap: 6px;
  padding: var(--e-6) var(--e-6) var(--e-5);
  border-radius: var(--r-4);
  box-shadow: var(--lueur);
}
.logo { width: 64px; height: 64px; align-self: center; }
.titre { margin: var(--e-3) 0 0; text-align: center; font-size: var(--t-xxl); }
.sous-titre {
  margin: 0 0 var(--e-4); text-align: center;
  font-size: var(--t-s); color: var(--discret);
}
label { margin-top: var(--e-3); font-size: var(--t-s); color: var(--discret); }
.connexion { width: 100%; margin-top: var(--e-5); padding: 10px 16px; font-size: var(--t-l); }
.avis, .erreur, .info {
  display: flex; align-items: flex-start; gap: var(--e-2);
  margin: 0 0 4px; padding: 10px 12px;
  border-radius: var(--r-1); font-size: var(--t-s); line-height: 1.4;
  color: var(--texte);
}
.avis > .icone, .erreur > .icone, .info-icone { flex-shrink: 0; margin-top: 1px; }
.avis { background: var(--surface-2); border: 1px solid var(--bordure); }
.avis > .icone { color: var(--avert); }
.info { background: var(--accent-doux); border: 1px solid var(--bordure); }
.info-icone { color: var(--accent-texte); }
.premier-compte ul { margin: 6px 0; padding-left: 18px; }
.premier-compte .btn { display: flex; width: 100%; margin: 10px 0 4px; }
.premier-compte .discret { display: block; margin-bottom: 6px; font-size: var(--t-xs); color: var(--discret); }
.premier-compte li { margin: 2px 0; }
.erreur {
  margin-top: 14px;
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  border: 1px solid var(--danger);
}
.erreur > .icone { color: var(--danger); }
.aide {
  margin: var(--e-4) 0 0; text-align: center;
  font-size: var(--t-xs); line-height: 1.5; color: var(--discret);
}
</style>
