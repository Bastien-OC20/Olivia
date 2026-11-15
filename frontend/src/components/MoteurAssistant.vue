<template>
  <div
    v-if="moteur.visible"
    class="moteur carte"
    :class="{ info: bloquant === false }"
    role="region"
    aria-labelledby="moteur-titre"
  >
    <div class="corps">
      <h2
        id="moteur-titre"
        class="titre"
      >
        <Icone
          :nom="bloquant === false ? 'etincelles' : 'alerte'"
          :taille="20"
          class="titre-icone"
        />
        <span>{{ titre }}</span>
      </h2>

      <!-- Moteur injoignable : le redémarrer, l'installer, ou le démarrer. -->
      <template v-if="!etat.joignable">
        <p v-if="bureau">
          Le moteur d'IA livré avec Oliv'IA ne répond pas. Redémarrez Oliv'IA : cliquez sur son
          icône (barre des menus sur Mac, zone de notification sous Windows), puis
          « Redémarrer Oliv'IA ». Les documents restent consultables en attendant.
        </p>
        <p v-else>
          Oliv'IA a besoin du moteur d'IA <b>Ollama</b>, installé sur ce poste, pour converser.
          Les documents restent consultables en attendant.
        </p>
        <p
          v-if="bureau"
          class="note"
        >
          Si le problème persiste, Oliv'IA peut aussi utiliser un Ollama installé séparément :
        </p>
        <ol>
          <li>
            <b>S'il n'est pas installé</b> : téléchargez-le sur
            <a
              href="https://ollama.com/download"
              target="_blank"
              rel="noopener noreferrer"
            >ollama.com/download</a>, puis installez-le.
          </li>
          <li>
            <b>S'il est déjà installé</b> : ouvrez l'application Ollama
            ({{ ouOuvrirOllama }}).
          </li>
        </ol>
        <p
          v-if="!bureau"
          class="note"
        >
          Version portable ou installée par le service informatique : le moteur est livré avec
          Oliv'IA et démarre avec elle. S'il ne répond pas, fermez Oliv'IA puis relancez-la.
        </p>
      </template>

      <!-- Moteur joignable, mais des modèles manquent : Oliv'IA les télécharge. -->
      <template v-else-if="manquants.length">
        <p>
          {{ bloquant
            ? "Le moteur d'IA fonctionne, mais le modèle de conversation n'est pas encore installé."
            : "Oliv'IA peut converser. Un modèle supplémentaire permettrait aussi de retrouver un document d'après l'idée qu'il contient." }}
          Oliv'IA peut le télécharger : une seule fois, avec une connexion Internet. Ensuite,
          tout reste sur ce poste.
        </p>
        <ul class="modeles">
          <li
            v-for="m in manquants"
            :key="m.nom"
          >
            <div class="ligne">
              <span><b>{{ m.nom }}</b> <span class="role">— {{ m.role }}</span></span>
              <button
                v-if="!enCoursPour(m)"
                type="button"
                class="btn btn-primaire"
                :disabled="demandes.has(m.nom)"
                @click="telecharger(m.nom)"
              >
                <Icone
                  :nom="m.telechargement?.etat === 'erreur' ? 'actualiser' : 'telecharger'"
                  :taille="16"
                />
                {{ m.telechargement?.etat === 'erreur' ? 'Réessayer' : 'Télécharger' }}
              </button>
            </div>
            <template v-if="enCoursPour(m)">
              <progress
                :value="m.telechargement.fait"
                :max="m.telechargement.total || 1"
                :aria-label="`Téléchargement de ${m.nom}`"
              />
              <span class="role">{{ avancement(m.telechargement) }}</span>
            </template>
            <p
              v-else-if="m.telechargement?.etat === 'erreur'"
              class="erreur"
            >
              {{ m.telechargement.message }}
            </p>
          </li>
        </ul>
        <button
          v-if="aLancer.length > 1"
          type="button"
          class="btn btn-secondaire"
          @click="aLancer.forEach((m) => telecharger(m.nom))"
        >
          <Icone
            nom="telecharger"
            :taille="16"
          />
          Tout télécharger
        </button>
        <p class="note">
          Plusieurs Go : comptez de quelques minutes à une heure selon la connexion. Ce message
          disparaît de lui-même une fois les modèles installés ; Oliv'IA reste utilisable pendant
          ce temps pour les documents.
        </p>
        <details class="note">
          <summary>Autre méthode : ligne de commande (service informatique)</summary>
          <p>Ouvrez {{ terminal }}, puis tapez :</p>
          <ul class="commandes">
            <li
              v-for="m in manquants"
              :key="m.nom"
            >
              <input
                :ref="(el) => { champs[m.nom] = el }"
                class="commande"
                :value="`ollama pull ${m.nom}`"
                :aria-label="`Commande à taper pour installer ${m.nom}`"
                readonly
                @focus="$event.target.select()"
              >
              <button
                type="button"
                class="btn btn-secondaire"
                @click="copier(m.nom)"
              >
                <Icone
                  :nom="copie === m.nom ? 'coche' : 'copier'"
                  :taille="16"
                />
                {{ copie === m.nom ? 'Copié' : 'Copier' }}
              </button>
            </li>
          </ul>
        </details>
      </template>

      <p class="note">
        Pas les droits pour installer un logiciel ? Transmettez ce message au service informatique.
      </p>
      <p
        class="sr-only"
        aria-live="polite"
      >
        {{ moteur.enCours ? 'Vérification en cours…' : '' }}
      </p>
    </div>

    <div class="btns">
      <button
        type="button"
        class="btn btn-primaire"
        :disabled="moteur.enCours"
        @click="moteur.verifier()"
      >
        <Icone
          nom="actualiser"
          :taille="16"
        />
        {{ moteur.enCours ? 'Vérification…' : 'Vérifier à nouveau' }}
      </button>
      <button
        type="button"
        class="btn btn-secondaire"
        @click="moteur.masquer()"
      >
        Masquer
      </button>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useMoteurStore } from '../stores/moteur.js'
import Icone from './Icone.vue'

const moteur = useMoteurStore()
const etat = computed(() => moteur.etat || {})

// Présent seulement dans l'application de bureau (desktop/preload.js).
const bureau = typeof window !== 'undefined' ? window.oliviaBureau : undefined
const plateforme = bureau?.plateforme
  || (/Mac/i.test(navigator.platform || '') ? 'darwin'
    : /Win/i.test(navigator.platform || '') ? 'win32' : '')

const ouOuvrirOllama = computed(() => ({
  darwin: 'dossier Applications',
  win32: 'menu Démarrer',
}[plateforme] || 'dossier Applications sur Mac, menu Démarrer sous Windows'))

const terminal = computed(() => ({
  darwin: "l'application Terminal",
  win32: "l'Invite de commandes (menu Démarrer → « cmd »)",
}[plateforme] || "le Terminal (Mac) ou l'Invite de commandes (Windows)"))

// Modèles à installer : indispensables et conseillés. Le modèle « facultatif »
// (celui de l'autre mode de calcul) n'est pas réclamé : il ne sert que si l'on
// change de mode, et le panneau le redemandera alors.
const manquants = computed(() => (etat.value.modeles || [])
  .filter((m) => m.installe === false && m.niveau !== 'facultatif'))

// Bloquant = Olivia ne peut pas converser. Sinon, simple information.
const bloquant = computed(() => !etat.value.pret)

const titre = computed(() => {
  // L'icône (alerte ou information) est dessinée devant le titre, dans le gabarit.
  if (!etat.value.joignable) return "Le moteur d'IA ne répond pas"
  if (bloquant.value) return 'Oliv\'IA n\'est pas encore prête à converser'
  return 'Recherche par le sens pas encore disponible'
})

// Téléchargement par Oliv'IA (POST /api/moteur/telecharger, backend/moteur.py).
const demandes = ref(new Set())          // clic envoyé, réponse pas encore reçue
const enCoursPour = (m) => m.telechargement?.etat === 'en_cours'
const aLancer = computed(() => manquants.value
  .filter((m) => !enCoursPour(m) && !demandes.value.has(m.nom)))

async function telecharger(nom) {
  demandes.value = new Set(demandes.value).add(nom)
  try {
    await moteur.telecharger(nom)
  } finally {
    const reste = new Set(demandes.value)
    reste.delete(nom)
    demandes.value = reste
  }
}

const go = (octets) => (octets / 1e9).toLocaleString('fr-FR',
  { minimumFractionDigits: 1, maximumFractionDigits: 1 })

/** « 2,3 Go sur 7,5 Go (31 %) », ou l'étape annoncée par Ollama avant. */
function avancement(t) {
  if (!t.total) return t.message || 'Préparation…'
  const pourcent = Math.floor((100 * t.fait) / t.total)
  return `${go(t.fait)} Go sur ${go(t.total)} Go (${pourcent} %)`
}

const champs = {}
const copie = ref('')

async function copier(nom) {
  const texte = `ollama pull ${nom}`
  try {
    await navigator.clipboard.writeText(texte)
  } catch {
    // Presse-papiers refusé : on sélectionne la commande et on passe par
    // l'ancienne API, encore acceptée lors d'un clic.
    const champ = champs[nom]
    champ?.focus()
    champ?.select()
    try { document.execCommand('copy') } catch { return }
  }
  copie.value = nom
  setTimeout(() => { if (copie.value === nom) copie.value = '' }, 2000)
}
</script>

<style scoped>
/* Dans le flux, comme la bannière RGPD : un panneau en position fixe masquerait
   des contrôles sans que l'utilisatrice comprenne pourquoi ils ne répondent plus.
   Carte posée sous la barre du haut, au-dessus de la conversation. */
.moteur {
  display: flex; gap: var(--e-4); align-items: flex-start; flex-wrap: wrap;
  margin: var(--e-3) var(--e-4) 0;
  padding: var(--e-4) var(--e-5);
  border-radius: var(--r-3);
  font-size: var(--t-s); line-height: 1.5;
  flex-shrink: 0;
}
.corps { flex: 1; min-width: 280px; }
.titre {
  display: flex; align-items: center; gap: var(--e-2);
  margin: 0 0 6px; font-size: 15px;
}
.titre-icone { color: var(--avert); flex-shrink: 0; }
.moteur.info .titre-icone { color: var(--accent-texte); }
.corps p, .corps ol { margin: 4px 0; }
.corps ol { padding-left: 20px; }
.corps a { color: var(--accent-texte); text-decoration: underline; }
.note { color: var(--discret); }
.commandes { list-style: none; padding: 0; margin: 6px 0; display: grid; gap: 6px; }
.commandes li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.commande {
  font-family: monospace; font-size: var(--t-s); width: 340px; max-width: 100%;
  background: var(--surface-2); color: var(--texte);
  border: 1px solid var(--bordure); border-radius: var(--r-1); padding: 5px 8px;
}
.role { color: var(--discret); font-size: var(--t-xs); }
.modeles { list-style: none; padding: 0; margin: 8px 0; display: grid; gap: 8px; max-width: 560px; }
.modeles .ligne { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.modeles progress { width: 100%; height: 10px; accent-color: var(--accent); }
.erreur { color: var(--danger); margin: 2px 0; }
details summary { cursor: pointer; }
.btns { display: flex; gap: 10px; flex-wrap: wrap; }
</style>
