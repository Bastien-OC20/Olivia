<template>
  <!-- Tant que `connecte` vaut null, la question n'est pas tranchée : on
       n'affiche rien plutôt qu'une application qui déclencherait aussitôt une
       rafale de 401 dans chacun de ses panneaux. -->
  <LoginView v-if="auth.connecte === false" />

  <div
    v-else-if="auth.connecte"
    class="layout"
  >
    <a
      href="#contenu"
      class="skip-link"
    >Aller au contenu principal</a>

    <!-- Rail : les trois sections, les Paramètres et le compte. Chaque onglet
         porte un libellé visible : des utilisatrices non techniques doivent
         lire, pas deviner une icône. -->
    <nav
      class="rail"
      aria-label="Navigation principale"
    >
      <h1 class="rail-logo">
        <img
          :src="logoUrl"
          alt="Oliv'IA"
          width="36"
          height="36"
        >
      </h1>

      <div
        class="rail-onglets"
        role="tablist"
        aria-orientation="vertical"
        aria-label="Sections du panneau"
      >
        <button
          v-for="t in sideTabs"
          :id="`tab-${t.id}`"
          :key="t.id"
          role="tab"
          type="button"
          class="rail-bouton"
          :class="{ actif: sideTab === t.id }"
          :aria-selected="sideTab === t.id"
          :aria-controls="`panel-${t.id}`"
          :tabindex="sideTab === t.id ? 0 : -1"
          @click="choisirOnglet(t.id)"
          @keydown="onTabKeydown"
        >
          <Icone
            :nom="t.icone"
            :taille="22"
          />
          <span class="rail-libelle">{{ t.label }}</span>
        </button>
      </div>

      <div class="rail-bas">
        <button
          type="button"
          class="rail-bouton"
          @click="settings.show()"
        >
          <Icone
            nom="engrenage"
            :taille="22"
          />
          <span class="rail-libelle">Paramètres</span>
        </button>

        <MenuDeroulant
          :etiquette="`Mon compte : ${auth.identite?.username || ''}`"
          etiquette-fenetre="Mon compte"
          :titre="`Connectée comme ${auth.identite?.username || ''}`"
          position="droite-haut"
          classe-declencheur="compte-pastille"
        >
          <template #declencheur>
            <span aria-hidden="true">{{ initiale }}</span>
          </template>
          <template #entete>
            <div class="compte-entete">
              <span class="compte-nom">{{ auth.identite?.username }}</span>
              <span class="compte-role">{{ libelleRole(auth.role) }}</span>
            </div>
          </template>
          <template #default="{ fermer }">
            <button
              type="button"
              role="menuitem"
              class="menu-item"
              tabindex="-1"
              @click="fermer(false); deconnexion()"
            >
              <Icone
                nom="sortie"
                :taille="18"
              />
              Se déconnecter
            </button>
          </template>
        </MenuDeroulant>
      </div>
    </nav>

    <!-- Voile sous le panneau quand il recouvre la zone principale (écran
         étroit) : un clic à côté le referme. -->
    <div
      v-if="etroit && panneauOuvert"
      class="voile"
      aria-hidden="true"
      @click="panneauOuvert = false"
    />

    <!-- Panneau : contenu de la section choisie dans le rail. Replié, il est
         masqué (v-show) mais reste monté : rien n'est perdu. -->
    <aside
      v-show="panneauOuvert"
      id="panneau"
      class="panneau"
      aria-labelledby="panneau-titre"
    >
      <div class="panneau-entete">
        <div class="marque">
          <span class="marque-nom">Oliv'IA</span>
          <span class="marque-sous-titre">votre assistante</span>
        </div>
        <div class="panneau-ligne">
          <h2
            id="panneau-titre"
            class="panneau-titre"
          >
            {{ ongletCourant.label }}
          </h2>
          <button
            ref="boutonReplier"
            type="button"
            class="btn-icone"
            aria-label="Replier le panneau"
            aria-controls="panneau"
            aria-expanded="true"
            @click="replier"
          >
            <Icone nom="panneau" />
          </button>
        </div>
      </div>

      <div class="panneau-corps">
        <div
          v-show="sideTab === 'conversations'"
          id="panel-conversations"
          role="tabpanel"
          aria-labelledby="tab-conversations"
          tabindex="0"
        >
          <ConversationList @ouverture="fermerSiEtroit" />
        </div>
        <div
          v-show="sideTab === 'documents'"
          id="panel-documents"
          role="tabpanel"
          aria-labelledby="tab-documents"
          tabindex="0"
        >
          <FileExplorer />
        </div>
        <div
          v-show="sideTab === 'tableaux'"
          id="panel-tableaux"
          role="tabpanel"
          aria-labelledby="tab-tableaux"
          tabindex="0"
        >
          <TableauList
            v-if="auth.connecte"
            @ouverture="fermerSiEtroit"
          />
        </div>
      </div>
    </aside>

    <main
      id="contenu"
      class="principal"
    >
      <header class="barre-haut">
        <button
          v-if="!panneauOuvert"
          ref="boutonDeplier"
          type="button"
          class="btn-icone"
          aria-label="Afficher le panneau"
          aria-controls="panneau"
          aria-expanded="false"
          @click="deplier"
        >
          <Icone nom="panneau" />
        </button>
        <h2
          class="titre-vue"
          :title="titreVue"
        >
          {{ titreVue }}
        </h2>

        <div class="barre-haut-actions">
          <ConnectedTools
            :simple="simple"
            @open-settings="settings.show()"
            @open-mail="settings.show()"
          />
          <MenuMoteur v-if="!simple" />
          <MenuDeroulant
            v-if="!tableaux.courant"
            etiquette="Plus d'actions"
          >
            <template #declencheur>
              <Icone nom="points" />
            </template>
            <template #default="{ fermer }">
              <button
                type="button"
                role="menuitem"
                class="menu-item"
                tabindex="-1"
                :aria-disabled="chat.messages.length === 0 ? 'true' : undefined"
                @click="effacer(fermer)"
              >
                <Icone
                  nom="corbeille"
                  :taille="18"
                />
                Effacer la conversation
              </button>
            </template>
          </MenuDeroulant>
        </div>
      </header>

      <MoteurAssistant />

      <!-- Un tableau ouvert remplace la conversation ; celle-ci reste montée
           (v-show) pour ne rien perdre d'une réponse en cours. -->
      <section
        v-show="!tableaux.courant"
        class="content"
        aria-label="Conversation"
      >
        <ChatPanel @ouvrir-documents="ouvrirDocuments" />
      </section>
      <section
        v-if="tableaux.courant"
        class="content"
        aria-label="Tableau blanc"
      >
        <TableauBlanc :key="tableaux.courant.id" />
      </section>

      <ConsentBanner @open-privacy="openPrivacy" />
    </main>

    <SettingsMenu ref="settingsMenu" />
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, ref, computed, watch, nextTick } from 'vue'
import { useChatStore } from './stores/chat.js'
import { useSettingsStore } from './stores/settings.js'
import { useAuthStore } from './stores/auth.js'
import { useMoteurStore } from './stores/moteur.js'
import LoginView from './components/LoginView.vue'
import FileExplorer from './components/FileExplorer.vue'
import ChatPanel from './components/ChatPanel.vue'
import TableauList from './components/TableauList.vue'
import TableauBlanc from './components/TableauBlanc.vue'
import { useTableauxStore } from './stores/tableaux.js'
import ConversationList from './components/ConversationList.vue'
import SettingsMenu from './components/SettingsMenu.vue'
import ConnectedTools from './components/ConnectedTools.vue'
import ConsentBanner from './components/ConsentBanner.vue'
import MoteurAssistant from './components/MoteurAssistant.vue'
import MenuDeroulant from './components/MenuDeroulant.vue'
import MenuMoteur from './components/MenuMoteur.vue'
import Icone from './components/Icone.vue'
import { libelleRole } from './roles.js'
import { indexApresTouche } from './clavier.js'
import logoUrl from './assets/logo-mark.png'

const chat = useChatStore()
const settings = useSettingsStore()
const auth = useAuthStore()
const moteur = useMoteurStore()
const tableaux = useTableauxStore()
const settingsMenu = ref(null)

const device = computed(() => settings.data.compute_device || 'gpu')
const simple = computed(() => settings.data.simple_mode !== false)

// Rail : conversations, documents et tableaux blancs.
// Visible dans les deux modes (simple et avancé).
const sideTabs = [
  { id: 'conversations', label: 'Conversations', icone: 'bulle' },
  { id: 'documents', label: 'Documents', icone: 'dossier' },
  { id: 'tableaux', label: 'Tableaux', icone: 'tableau' },
]
const sideTab = ref('conversations')
const ongletCourant = computed(() => sideTabs.find(t => t.id === sideTab.value) || sideTabs[0])

// Écran étroit (moins de 900 px) : le panneau passe par-dessus la zone
// principale et démarre replié. Simple état en mémoire : rien n'est stocké.
const requeteEtroit = window.matchMedia('(max-width: 900px)')
const etroit = ref(requeteEtroit.matches)
const panneauOuvert = ref(!etroit.value)
const boutonReplier = ref(null)
const boutonDeplier = ref(null)

function surChangementLargeur(e) {
  etroit.value = e.matches
  if (e.matches) panneauOuvert.value = false
}

/** Replie le panneau ; le focus passe au bouton qui le rouvre (sinon il se
 *  perdrait dans un panneau masqué). */
async function replier() {
  panneauOuvert.value = false
  await nextTick()
  boutonDeplier.value?.focus()
}

async function deplier() {
  panneauOuvert.value = true
  await nextTick()
  boutonReplier.value?.focus()
}

// Sur écran étroit, ouvrir une conversation ou un tableau depuis le panneau
// dégage la vue : le panneau recouvrirait ce qu'on vient d'ouvrir.
function fermerSiEtroit() {
  if (etroit.value) panneauOuvert.value = false
}

// Un clic sur l'onglet déjà actif replie ou déplie le panneau ; un autre
// onglet l'ouvre toujours (sinon le choix n'aurait aucun effet visible).
function choisirOnglet(id) {
  if (sideTab.value === id) {
    panneauOuvert.value = !panneauOuvert.value
    return
  }
  sideTab.value = id
  panneauOuvert.value = true
}

// « Joindre un document » (saisie) et la carte « Utiliser un document » de
// l'accueil : on montre l'onglet Documents, où l'on choisit le fichier.
function ouvrirDocuments() {
  sideTab.value = 'documents'
  panneauOuvert.value = true
}

// Titre de la zone principale : le tableau ouvert, sinon la conversation.
const titreVue = computed(() => {
  if (tableaux.courant) return tableaux.courant.titre || 'Sans titre'
  const conversation = chat.conversations.find(c => c.id === chat.currentId)
  if (conversation) return conversation.title || 'Sans titre'
  return 'Nouvelle conversation'
})

// Initiale du compte, dans la pastille du rail (Array.from : un caractère
// accentué ou hors du plan de base n'est pas coupé en deux).
const initiale = computed(() => (Array.from(auth.identite?.username || '')[0] || '?').toUpperCase())

onMounted(() => {
  auth.surveillerExpiration()
  auth.verifier()
  requeteEtroit.addEventListener('change', surChangementLargeur)
})

onBeforeUnmount(() => requeteEtroit.removeEventListener('change', surChangementLargeur))

// Le chargement suit l'état de la session plutôt qu'un évènement émis par
// l'écran de connexion : quand `connexion()` bascule `connecte` à vrai, Vue
// démonte LoginView avant que celui-ci n'ait pu émettre quoi que ce soit — un
// `@connecte` ne partait jamais. Ici, une seule voie sert les deux cas (cookie
// encore valide au démarrage, et connexion réussie).
watch(() => auth.connecte, (ouverte) => {
  if (ouverte) demarrer()
  else purger()                  // déconnexion OU session expirée
})

/** Vide tout ce qui appartient au compte qui vient de quitter la session.
 *
 *  Le poste peut être partagé : rien du compte précédent ne doit rester à
 *  l'écran ni en mémoire pour la personne qui se connectera ensuite. Appelée
 *  pour une déconnexion comme pour une session EXPIRÉE : auparavant seule la
 *  déconnexion explicite vidait la conversation et les documents joints, et
 *  après une expiration (8 h) le compte suivant retrouvait la conversation du
 *  précédent — dont les documents joints repartaient vers le modèle. */
function purger() {
  moteur.arreter()
  chat.stop()                    // une réponse en cours ne doit pas finir chez le suivant
  chat.clear()
  chat.clearFileContexts()
  chat.conversations = []
  tableaux.reinitialiser()
  settings.reset()
}

// Ouvrir une conversation depuis la liste ramène à la conversation : sinon le
// clic ne produirait aucun effet visible tant qu'un tableau est affiché. Le
// tableau en cours envoie sa dernière sauvegarde en se fermant (TableauBlanc.vue).
watch(() => chat.currentId, () => tableaux.fermer())

// La barre latérale suit la zone principale : un tableau qui s'ouvre depuis la
// conversation (bouton sous une réponse, commande /tableau) apparaît en
// surbrillance dans sa liste ; en revenant à la conversation, on retrouve la
// liste des conversations. L'onglet Documents n'est jamais touché : c'est là que
// l'utilisatrice travaille, y compris quand un ajout referme le tableau. Passer
// d'un tableau à un autre (identifiant différent, toujours ouvert) ne change rien.
watch(() => tableaux.courant?.id ?? null, (id, avant) => {
  const ouvert = id !== null
  if (ouvert === (avant !== null)) return
  if (ouvert && sideTab.value === 'conversations') sideTab.value = 'tableaux'
  else if (!ouvert && sideTab.value === 'tableaux') sideTab.value = 'conversations'
})

// Le modèle indispensable dépend du mode de calcul (⚡ / 🧩 / 🪶) : après un
// changement enregistré (barre du haut ou Paramètres), celui de l'autre mode
// peut manquer. On revérifie une fois la sauvegarde terminée, pas avant : le
// backend lit le réglage enregistré.
let peripheriqueVerifie = null
watch(() => settings.saving, (enCours) => {
  if (enCours || !auth.connecte) return
  if (settings.data.compute_device !== peripheriqueVerifie) {
    peripheriqueVerifie = settings.data.compute_device
    moteur.signalerPanne()
  }
})

/** Charge les données de l'organisation connectée. Pas de `location.reload()` :
 *  l'application est déjà montée, un rechargement ne ferait que refaire ces
 *  trois appels en repartant de zéro. */
async function demarrer() {
  await settings.load()
  peripheriqueVerifie = settings.data.compute_device
  chat.loadModels(settings.data.device_models?.[device.value] || [])
  chat.loadConversations()
  // Moteur d'IA prêt ? Sinon, panneau d'aide (poste neuf, Ollama arrêté). Quand
  // il le devient, la liste des modèles est rechargée pour choisir le bon.
  moteur.demarrer(() => chat.loadModels(settings.data.device_models?.[device.value] || []))
}

async function deconnexion() {
  // La purge suit le passage de `auth.connecte` à faux (voir le `watch` plus
  // haut). Appelée ici aussi, sans attendre : si la session était déjà fermée
  // côté serveur, `connecte` ne change pas et le `watch` ne se déclenche pas.
  await auth.deconnexion()
  purger()
}

// « Effacer la conversation » est désactivé par aria-disabled (il reste
// atteignable au clavier dans le menu) : le clic est donc ignoré ici.
function effacer(fermer) {
  if (chat.messages.length === 0) return
  fermer()
  chat.clear()
}

// Navigation clavier attendue pour un role="tablist" vertical (flèches Haut et
// Bas, ainsi que Gauche et Droite, Début, Fin). Changer d'onglet au clavier
// rouvre le panneau, comme un clic.
function onTabKeydown(e) {
  const i = sideTabs.findIndex(t => t.id === sideTab.value)
  const next = indexApresTouche(e.key, i, sideTabs.length, { horizontal: true })
  if (next === null) return
  e.preventDefault()
  sideTab.value = sideTabs[next].id
  panneauOuvert.value = true
  document.getElementById(`tab-${sideTabs[next].id}`)?.focus()
}

function openPrivacy() {
  settings.show()
  settingsMenu.value?.goToPrivacy?.()
}
</script>

<style scoped>
.layout {
  --largeur-rail: 88px;
  --largeur-panneau: 280px;
  position: relative;
  display: grid;
  grid-template-columns: var(--largeur-rail) auto minmax(0, 1fr);
  grid-template-areas: "rail panneau principal";
  height: 100vh;
}

/* ---------- Rail ---------- */
.rail {
  grid-area: rail;
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--e-2);
  padding: var(--e-3) var(--e-1);
  background: var(--surface);
  border-right: 1px solid var(--bordure);
  min-height: 0;
}
.rail-logo { margin: 0 0 var(--e-3); line-height: 0; }
.rail-logo img { width: 36px; height: 36px; display: block; }   /* tuile aux coins déjà arrondis */
.rail-onglets { display: flex; flex-direction: column; gap: var(--e-1); width: 100%; }
.rail-bouton {
  position: relative;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  width: 100%;
  padding: 8px 2px;
  background: transparent;
  color: var(--discret);
  border-radius: var(--r-2);
  font-size: 11px;
  font-weight: 500;
  line-height: 1.2;
}
.rail-bouton:hover { background: var(--surface-2); color: var(--texte); }
.rail-bouton.actif { background: var(--accent-doux); color: var(--accent-texte); }
/* Petite barre à gauche de l'onglet actif, contre le bord du rail. */
.rail-bouton.actif::before {
  content: "";
  position: absolute;
  left: calc(-1 * var(--e-1));
  top: 10px;
  bottom: 10px;
  width: 3px;
  border-radius: 0 3px 3px 0;
  background: var(--accent-texte);
}
.rail-libelle { white-space: nowrap; }
.rail-bas {
  margin-top: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--e-3);
  width: 100%;
}
/* Pastille du compte : rendue par MenuDeroulant, d'où :deep(). */
.rail-bas :deep(.compte-pastille) {
  width: 36px;
  height: 36px;
  padding: 0;
  border-radius: var(--r-rond);
  background: var(--accent-doux);
  color: var(--accent-texte);
  border: 1px solid var(--bordure-forte);
  font-size: var(--t-m);
  font-weight: 600;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}
.rail-bas :deep(.compte-pastille:hover),
.rail-bas :deep(.compte-pastille[aria-expanded="true"]) {
  background: var(--surface-3);
}
.compte-entete {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 10px 10px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--bordure);
}
.compte-nom { font-weight: 600; font-size: var(--t-m); overflow-wrap: anywhere; }
.compte-role { font-size: var(--t-xs); color: var(--discret); }

/* ---------- Panneau ---------- */
.panneau {
  grid-area: panneau;
  width: var(--largeur-panneau);
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: color-mix(in srgb, var(--surface) 55%, var(--fond));
  border-right: 1px solid var(--bordure);
}
.panneau-entete { padding: var(--e-4) var(--e-3) var(--e-2) var(--e-4); flex-shrink: 0; }
.marque { display: flex; align-items: baseline; gap: 6px; margin-bottom: var(--e-2); }
.marque-nom { font-size: var(--t-s); font-weight: 700; letter-spacing: 0.2px; }
.marque-sous-titre { font-size: var(--t-xs); color: var(--discret); }
.panneau-ligne { display: flex; align-items: center; justify-content: space-between; gap: var(--e-2); }
.panneau-titre { margin: 0; font-size: var(--t-xl); font-weight: 600; }
.panneau-corps { flex: 1; min-height: 0; overflow-y: auto; }
.panneau-corps [role="tabpanel"] { outline-offset: -2px; }

/* ---------- Zone principale ---------- */
.principal {
  grid-area: principal;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}
.barre-haut {
  position: relative;
  z-index: 10;               /* les menus déroulants passent au-dessus du contenu */
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: var(--e-2);
  height: 56px;
  padding: 0 var(--e-3) 0 var(--e-4);
  border-bottom: 1px solid var(--bordure);
}
.titre-vue {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: var(--t-l);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.barre-haut-actions {
  display: flex;
  align-items: center;
  gap: var(--e-2);
  min-width: 0;
  flex-shrink: 1;
}
.content { flex: 1; min-height: 0; overflow: hidden; }

/* ---------- Écran étroit : le panneau recouvre la zone principale ---------- */
@media (max-width: 900px) {
  .layout {
    grid-template-columns: var(--largeur-rail) minmax(0, 1fr);
    grid-template-areas: "rail principal";
  }
  .panneau {
    grid-area: auto;
    position: absolute;
    top: 0;
    bottom: 0;
    left: var(--largeur-rail);
    z-index: 25;
    max-width: calc(100vw - var(--largeur-rail));
    box-shadow: var(--ombre-2);
  }
  .voile {
    position: absolute;
    top: 0;
    bottom: 0;
    left: var(--largeur-rail);
    right: 0;
    z-index: 20;
    background: color-mix(in srgb, var(--fond) 45%, transparent);
  }
}
</style>
