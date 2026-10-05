<template>
  <section
    class="tableau"
    aria-label="Tableau blanc"
  >
    <header class="barre">
      <button
        class="ghost"
        type="button"
        @click="fermer"
      >
        ← Conversation
      </button>
      <label
        for="titre-tableau"
        class="sr-only"
      >Titre du tableau</label>
      <input
        id="titre-tableau"
        v-model="titre"
        class="titre"
        maxlength="80"
        @change="renommer"
        @keydown.enter="$event.target.blur()"
      >
      <span
        class="etat"
        :class="{ erreur: tableaux.sauvegarde === 'erreur' }"
        aria-live="polite"
      >{{ libelleEtat }}</span>
    </header>

    <!-- Excalidraw (React) est monté dans cette zone ; la page reste en Vue. -->
    <div class="zone">
      <div
        ref="racine"
        class="racine"
      />
      <p
        v-if="chargement"
        class="message"
      >
        Chargement du tableau blanc…
      </p>
      <p
        v-if="erreurChargement"
        class="message erreur"
      >
        {{ erreurChargement }}
      </p>
    </div>
  </section>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useTableauxStore } from '../stores/tableaux.js'

const tableaux = useTableauxStore()
const racine = ref(null)
const chargement = ref(true)
const erreurChargement = ref('')
const titre = ref(tableaux.courant?.titre || '')
// Identifiant FIGÉ au montage : en passant d'un tableau à l'autre, le store
// désigne déjà le nouveau quand celui-ci envoie sa dernière sauvegarde. Lire
// `tableaux.courant.id` à ce moment-là écraserait le nouveau tableau avec
// l'ancien dessin.
const idTableau = tableaux.courant?.id

// Sauvegarde automatique : on attend une pause dans le dessin plutôt que
// d'envoyer chaque déplacement de souris. Excalidraw appelle onChange en continu
// (sélection, zoom, survol) : seule une scène réellement différente de la
// dernière enregistrée part au serveur.
const DELAI_SAUVEGARDE_MS = 1500
let minuteur = null
let derniereScene = null      // dernière scène enregistrée (texte JSON)
let sceneEnAttente = null     // scène à enregistrer au prochain passage
let racineReact = null
let serialiser = null
let apiExcalidraw = null      // interface d'Excalidraw (remise par excalidrawAPI)
let cadre = false             // le cadrage de départ n'a lieu qu'une fois

// Cadre tout le contenu dans la vue à l'ouverture : un schéma plus grand que
// l'écran (typique d'un tableau produit par /tableau) ne doit pas déborder sous
// la barre d'outils. `fitToContent` ne dépasse jamais 100 % : un petit dessin
// reste à sa taille, simplement centré. Appelée depuis onChange car c'est le
// premier moment où la scène est chargée ET la taille de la zone connue — avant,
// le calcul porterait sur une zone de taille 0. Le zoom et le défilement ne font
// pas partie de la scène enregistrée (format 'local'), donc aucune sauvegarde
// inutile n'en découle.
function cadrerUneFois(elements, appState) {
  if (cadre || !apiExcalidraw || !appState.width || !appState.height) return
  cadre = true
  if (!elements.some(e => !e.isDeleted)) return       // tableau vide : rien à cadrer
  apiExcalidraw.scrollToContent(undefined, {
    fitToContent: true,
    viewportZoomFactor: 0.9,        // petite marge autour du dessin
    canvasOffsets: { top: 70 },     // la barre d'outils flotte sur le haut de la zone
    animate: false,
  })
}

const libelleEtat = computed(() => ({
  en_cours: 'Enregistrement…',
  enregistre: '✓ Enregistré',
  erreur: `⚠️ ${tableaux.erreurSauvegarde || 'Non enregistré'}`,
}[tableaux.sauvegarde] || ''))

onMounted(async () => {
  const tableau = tableaux.courant
  if (!tableau) return
  try {
    // Polices d'Excalidraw servies par Oliv'IA elle-même (copiées au build,
    // voir vite.config.js) : sans cette adresse, Excalidraw les chercherait sur
    // un CDN — refusé de toute façon par la politique de sécurité du backend.
    window.EXCALIDRAW_ASSET_PATH = new URL('excalidraw-assets/', document.baseURI).href
    const [React, { createRoot }, excalidraw] = await Promise.all([
      import('react'),
      import('react-dom/client'),
      import('@excalidraw/excalidraw'),
      import('@excalidraw/excalidraw/index.css'),
    ])
    serialiser = excalidraw.serializeAsJSON
    const scene = tableau.scene || {}
    derniereScene = JSON.stringify(scene)
    racineReact = createRoot(racine.value)
    racineReact.render(React.createElement(excalidraw.Excalidraw, {
      initialData: {
        elements: scene.elements || [],
        appState: { ...(scene.appState || {}), theme: scene.appState?.theme || 'dark' },
        files: scene.files || {},
      },
      excalidrawAPI: (api) => { apiExcalidraw = api },
      langCode: 'fr-FR',
      name: tableau.titre,
      // Fonctions d'IA d'Excalidraw (texte → diagramme…) : elles passent par un
      // service en ligne, contraire au fonctionnement 100 % local d'Oliv'IA.
      aiEnabled: false,
      // Contenus intégrés (vidéos, pages web) : ils chargeraient des sites
      // externes dans le tableau. Refusés.
      validateEmbeddable: () => false,
      onChange: (elements, appState, files) => {
        cadrerUneFois(elements, appState)
        sceneEnAttente = { elements, appState, files }
        clearTimeout(minuteur)
        minuteur = setTimeout(enregistrer, DELAI_SAUVEGARDE_MS)
      },
    }))
  } catch (e) {
    console.error('Excalidraw indisponible :', e)
    erreurChargement.value = "Le tableau blanc n'a pas pu se charger. Rechargez la page, puis réessayez."
  } finally {
    chargement.value = false
  }
})

async function enregistrer() {
  clearTimeout(minuteur)
  minuteur = null
  const id = idTableau
  if (!sceneEnAttente || !serialiser || !id) return
  const { elements, appState, files } = sceneEnAttente
  sceneEnAttente = null
  // Format .excalidraw « local » : sans l'état éphémère (sélection, outil
  // actif, collaborateurs), seulement ce qui décrit le dessin.
  const texte = serialiser(elements, appState, files, 'local')
  if (texte === derniereScene) return
  if (await tableaux.enregistrerScene(id, JSON.parse(texte))) derniereScene = texte
}

async function renommer() {
  const id = idTableau
  const nouveau = titre.value.trim()
  if (!id || !nouveau || nouveau === tableaux.courant?.titre) return
  if (!(await tableaux.renommer(id, nouveau))) alert("Le renommage n'a pas pu être enregistré.")
  titre.value = tableaux.courant?.titre || nouveau
}

async function fermer() {
  await enregistrer()             // rien ne se perd en revenant à la conversation
  tableaux.fermer()
}

onBeforeUnmount(() => {
  // Changement de tableau ou déconnexion : on envoie ce qui attend encore.
  if (sceneEnAttente) enregistrer()
  racineReact?.unmount()
  racineReact = null
  apiExcalidraw = null
})
</script>

<style scoped>
.tableau { display: flex; flex-direction: column; height: 100%; }
.barre {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 12px; border-bottom: 1px solid var(--border); background: var(--panel);
}
.barre .ghost { background: var(--panel-2); color: var(--text); }
.titre {
  flex: 1; min-width: 120px; max-width: 420px; font-size: 14px; font-weight: 600;
  background: transparent; border: 1px solid transparent; color: var(--text);
  padding: 5px 8px; border-radius: 6px;
}
.titre:hover, .titre:focus { border-color: var(--border); background: var(--panel-2); }
.etat { font-size: 12px; color: var(--muted); }
.etat.erreur { color: var(--danger); }
.zone { position: relative; flex: 1; min-height: 0; }
.racine { position: absolute; inset: 0; }
.message {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  margin: 0; color: var(--muted); font-size: 14px; pointer-events: none;
}
.message.erreur { color: var(--danger); }
</style>

<style>
/* Bibliothèque d'Excalidraw : « Parcourir les bibliothèques » ouvre
   libraries.excalidraw.com (qui renvoie ses formes par l'adresse de la page,
   impossible dans Oliv'IA) et « Publier » envoie la sélection à un service en
   ligne d'Excalidraw. Les deux sont retirés ; l'ajout et l'import de fichiers
   .excalidrawlib restent. */
.excalidraw .library-menu-browse-button,
.excalidraw [data-testid="lib-dropdown--remove"] { display: none !important; }
</style>
