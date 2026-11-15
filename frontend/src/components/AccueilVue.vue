<template>
  <div class="accueil">
    <div class="accueil-contenu">
      <header class="accueil-entete">
        <img
          :src="logoUrl"
          alt=""
          class="accueil-logo"
          width="64"
          height="64"
        >
        <h2 class="accueil-titre">
          {{ titre }}
        </h2>
        <p class="accueil-sous-titre">
          Que puis-je faire pour vous aujourd'hui ?
        </p>
      </header>

      <div class="accueil-saisie">
        <slot name="saisie" />
      </div>

      <ul
        class="accueil-actions"
        aria-label="Pour commencer"
      >
        <li
          v-for="action in ACTIONS_ACCUEIL"
          :key="action.id"
        >
          <button
            type="button"
            class="action-carte"
            @click="emit('action', action)"
          >
            <span class="action-pastille">
              <Icone
                :nom="action.icone"
                :taille="20"
              />
            </span>
            <span class="action-texte">
              <span class="action-titre">{{ action.titre }}</span>
              <span class="action-description">{{ action.description }}</span>
            </span>
          </button>
        </li>
      </ul>

      <div
        v-if="conversationsRecentes.length || tableauxRecents.length"
        class="accueil-widgets"
      >
        <section
          v-if="conversationsRecentes.length"
          class="carte widget"
          aria-labelledby="widget-conversations"
        >
          <h3
            id="widget-conversations"
            class="widget-titre"
          >
            <Icone
              nom="bulle"
              :taille="18"
            />
            Reprendre une conversation
          </h3>
          <ul class="widget-liste">
            <li
              v-for="c in conversationsRecentes"
              :key="c.id"
            >
              <button
                type="button"
                class="widget-ligne"
                @click="emit('ouvrir-conversation', c.id)"
              >
                <span class="widget-nom">{{ c.title || 'Sans titre' }}</span>
                <span class="widget-date">{{ dateRelative(c.updated_at) }}</span>
              </button>
            </li>
          </ul>
        </section>

        <section
          v-if="tableauxRecents.length"
          class="carte widget"
          aria-labelledby="widget-tableaux"
        >
          <h3
            id="widget-tableaux"
            class="widget-titre"
          >
            <Icone
              nom="tableau"
              :taille="18"
            />
            Tableaux récents
          </h3>
          <ul class="widget-liste">
            <li
              v-for="t in tableauxRecents"
              :key="t.id"
            >
              <button
                type="button"
                class="widget-ligne"
                @click="emit('ouvrir-tableau', t.id)"
              >
                <span class="widget-nom">{{ t.titre || 'Sans titre' }}</span>
                <span class="widget-date">{{ dateRelative(t.modifie_le) }}</span>
              </button>
            </li>
          </ul>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useAuthStore } from '../stores/auth.js'
import { useChatStore } from '../stores/chat.js'
import { useTableauxStore } from '../stores/tableaux.js'
import { ACTIONS_ACCUEIL, salutation, nomAffiche, recentes } from '../accueil.js'
import { dateRelative } from '../dates.js'
import Icone from './Icone.vue'
import logoUrl from '../assets/logo-mark.png'

const emit = defineEmits(['action', 'ouvrir-conversation', 'ouvrir-tableau'])

const auth = useAuthStore()
const chat = useChatStore()
const tableaux = useTableauxStore()

// Salutation calculée à l'affichage de l'accueil (pas d'horloge qui tourne :
// l'écran change à chaque nouvelle conversation, c'est assez).
const titre = computed(() => {
  const nom = nomAffiche(auth.identite?.username)
  return nom ? `${salutation(new Date())}, ${nom}` : salutation(new Date())
})

const conversationsRecentes = computed(() => recentes(chat.conversations, 'updated_at'))
const tableauxRecents = computed(() => recentes(tableaux.liste, 'modifie_le'))
</script>

<style scoped>
/* La largeur de la zone (et non de la fenêtre) décide du nombre de colonnes :
   le panneau latéral peut être ouvert ou replié. */
.accueil {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  container-type: inline-size;
  padding: var(--e-6) var(--e-4) var(--e-5);
}
.accueil-contenu {
  max-width: 760px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: var(--e-5);
}

.accueil-entete { text-align: center; }
.accueil-logo { width: 64px; height: 64px; display: block; margin: 0 auto var(--e-3); }
.accueil-titre {
  margin: 0;
  font-size: var(--t-xxl);
  font-weight: 600;
  color: var(--texte);
  line-height: 1.25;
  overflow-wrap: anywhere;
}
.accueil-sous-titre { margin: var(--e-2) 0 0; color: var(--discret); font-size: var(--t-l); }

/* Cartes d'actions : 3 colonnes sur une zone large, 2 en dessous, 1 très étroite. */
.accueil-actions {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: var(--e-3);
}
@container (min-width: 900px) {
  .accueil-actions { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
@container (max-width: 480px) {
  .accueil-actions { grid-template-columns: minmax(0, 1fr); }
}
.accueil-actions li { display: flex; }

.action-carte {
  display: flex;
  align-items: flex-start;
  gap: var(--e-3);
  width: 100%;
  padding: var(--e-4);
  text-align: left;
  background: var(--surface);
  color: var(--texte);
  border: 1px solid var(--bordure);
  border-radius: var(--r-3);
  box-shadow: var(--ombre-1);
}
.action-carte:hover {
  background: var(--surface);
  border-color: var(--bordure-forte);
  box-shadow: var(--ombre-2);
  transform: translateY(-2px);
}
.action-carte:active { transform: translateY(0); }
.action-pastille {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--r-rond);
  background: var(--accent-doux);
  color: var(--accent-texte);
}
.action-texte { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
.action-titre { font-size: var(--t-m); font-weight: 600; line-height: 1.3; }
.action-description { font-size: var(--t-s); color: var(--discret); line-height: 1.4; }

/* Widgets : côte à côte, l'un sous l'autre sur une zone étroite. */
.accueil-widgets {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: var(--e-3);
}
.widget { padding: var(--e-3) var(--e-3) var(--e-2); min-width: 0; }
.widget-titre {
  display: flex;
  align-items: center;
  gap: var(--e-2);
  margin: 0 0 var(--e-2);
  padding: 0 var(--e-2);
  font-size: var(--t-s);
  font-weight: 600;
  color: var(--discret);
}
.widget-liste { list-style: none; margin: 0; padding: 0; }
.widget-ligne {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--e-3);
  width: 100%;
  padding: 8px var(--e-2);
  background: transparent;
  color: var(--texte);
  border-radius: var(--r-1);
  text-align: left;
  font-size: var(--t-m);
}
.widget-ligne:hover { background: var(--surface-2); }
.widget-nom { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.widget-date { flex-shrink: 0; font-size: var(--t-xs); color: var(--discret); }

@media (prefers-reduced-motion: reduce) {
  .action-carte:hover { transform: none; }
}
</style>
