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

      <!-- Moteur injoignable : l'installer, ou le démarrer. -->
      <template v-if="!etat.joignable">
        <p>
          Oliv'IA a besoin du moteur d'IA <b>Ollama</b>, installé sur ce poste, pour converser.
          Les documents restent consultables en attendant.
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

      <!-- Moteur joignable, mais des modèles manquent. -->
      <template v-else-if="manquants.length">
        <p>
          {{ bloquant
            ? "Le moteur d'IA fonctionne, mais le modèle de conversation n'est pas encore installé."
            : "Oliv'IA peut converser. Un modèle supplémentaire permettrait aussi de retrouver un document d'après l'idée qu'il contient." }}
          Ouvrez {{ terminal }}, puis tapez :
        </p>
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
            <span class="role">{{ m.role }}</span>
          </li>
        </ul>
        <p class="note">
          Le téléchargement peut prendre plusieurs minutes. Ce message disparaît de lui-même
          une fois le modèle installé.
        </p>
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
.btns { display: flex; gap: 10px; }
.ghost { background: var(--panel-2); color: var(--text); }
.sr-only {
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0;
}
</style>
