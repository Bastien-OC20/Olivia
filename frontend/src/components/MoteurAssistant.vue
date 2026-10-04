<template>
  <div
    v-if="moteur.visible"
    class="moteur"
    :class="{ info: bloquant === false }"
    role="region"
    aria-labelledby="moteur-titre"
  >
    <div class="corps">
      <h2
        id="moteur-titre"
        class="titre"
      >
        {{ titre }}
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
                :disabled="demandes.has(m.nom)"
                @click="telecharger(m.nom)"
              >
                {{ m.telechargement?.etat === 'erreur' ? '🔄 Réessayer' : '⬇ Télécharger' }}
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
          class="ghost"
          @click="aLancer.forEach((m) => telecharger(m.nom))"
        >
          ⬇ Tout télécharger
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
                class="ghost"
                @click="copier(m.nom)"
              >
                {{ copie === m.nom ? '✅ Copié' : '📋 Copier' }}
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
        :disabled="moteur.enCours"
        @click="moteur.verifier()"
      >
        {{ moteur.enCours ? '⏳ Vérification…' : '🔄 Vérifier à nouveau' }}
      </button>
      <button
        type="button"
        class="ghost"
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
  if (!etat.value.joignable) return "⚠️ Le moteur d'IA ne répond pas"
  if (bloquant.value) return '⚠️ Oliv\'IA n\'est pas encore prête à converser'
  return 'ℹ️ Recherche par le sens pas encore disponible'
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
   des contrôles sans que l'utilisatrice comprenne pourquoi ils ne répondent plus. */
.moteur {
  display: flex; gap: 16px; align-items: flex-start; flex-wrap: wrap;
  padding: 14px 20px; background: var(--panel);
  border-bottom: 1px solid var(--border);
  border-left: 4px solid var(--warn);
  font-size: 13px; line-height: 1.5;
}
.moteur.info { border-left-color: var(--accent); }
.corps { flex: 1; min-width: 280px; }
.titre { margin: 0 0 6px; font-size: 15px; }
.corps p, .corps ol { margin: 4px 0; }
.corps ol { padding-left: 20px; }
.corps a { color: var(--accent); text-decoration: underline; }
.note { color: var(--muted); }
.commandes { list-style: none; padding: 0; margin: 6px 0; display: grid; gap: 6px; }
.commandes li { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.commande {
  font-family: monospace; font-size: 13px; width: 340px; max-width: 100%;
  background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: 6px; padding: 5px 8px;
}
.role { color: var(--muted); font-size: 12px; }
.modeles { list-style: none; padding: 0; margin: 8px 0; display: grid; gap: 8px; max-width: 560px; }
.modeles .ligne { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.modeles progress { width: 100%; height: 10px; accent-color: var(--accent); }
.erreur { color: var(--danger); margin: 2px 0; }
details summary { cursor: pointer; }
.btns { display: flex; gap: 10px; }
.ghost { background: var(--panel-2); color: var(--text); }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
</style>
