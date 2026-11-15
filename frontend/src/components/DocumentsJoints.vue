<template>
  <!-- Documents joints : pastilles au-dessus de la saisie (accueil et conversation). -->
  <div
    v-if="chat.fileContextPlan.length"
    class="docs-joints"
    aria-live="polite"
  >
    <div class="docs-entete">
      <span>
        {{ chat.fileContextPlan.length }} document{{ chat.fileContextPlan.length > 1 ? 's' : '' }}
        dans la conversation
      </span>
      <button
        type="button"
        class="btn btn-fantome btn-compact"
        @click="chat.clearFileContexts()"
      >
        Tout retirer
      </button>
    </div>
    <ul class="docs-liste">
      <li
        v-for="doc in chat.fileContextPlan"
        :key="doc.path"
        class="doc-pastille"
      >
        <Icone
          nom="document"
          :taille="14"
        />
        <span
          class="doc-nom"
          :title="doc.path"
        >{{ doc.name }}</span>
        <span
          v-if="doc.truncated"
          class="doc-tronque"
          :title="`Seuls les ${doc.keptChars} premiers caractères sur ${doc.chars} sont transmis à Oliv'IA.`"
        >
          <Icone
            nom="alerte"
            :taille="12"
          />
          tronqué
        </span>
        <button
          type="button"
          class="btn-icone doc-retirer"
          :aria-label="`Retirer ${doc.name} de la conversation`"
          @click="chat.removeFileContext(doc.path)"
        >
          <Icone
            nom="fermer"
            :taille="14"
          />
        </button>
      </li>
    </ul>
    <p
      v-if="documentsTronques"
      class="avert"
    >
      <Icone
        nom="alerte"
        :taille="14"
      />
      <span>
        Certains documents sont trop longs : seul leur début est transmis à Oliv'IA.
        Retirez-en pour laisser plus de place aux autres.
      </span>
    </p>
    <p
      v-if="chat.fileContextNotice"
      class="avert"
    >
      <Icone
        nom="alerte"
        :taille="14"
      />
      <span>{{ chat.fileContextNotice }}</span>
    </p>
  </div>
  <!-- Aucun document rattaché (tous devenus illisibles) : le bandeau est absent,
       mais l'avis doit rester visible. -->
  <div
    v-else-if="chat.fileContextNotice"
    class="docs-joints"
    role="status"
  >
    <p class="avert">
      <Icone
        nom="alerte"
        :taille="14"
      />
      <span>{{ chat.fileContextNotice }}</span>
    </p>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useChatStore } from '../stores/chat.js'
import Icone from './Icone.vue'

const chat = useChatStore()

const documentsTronques = computed(() => chat.fileContextPlan.some((d) => d.truncated))
</script>

<style scoped>
/* Avertissement (texte + icône) */
.avert {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: var(--e-2) 0 0;
  font-size: var(--t-xs);
  color: var(--avert);
  line-height: 1.4;
}
.avert .icone { flex-shrink: 0; margin-top: 1px; }

.docs-joints { margin-bottom: var(--e-2); font-size: var(--t-s); }
.docs-entete {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--e-2);
  color: var(--discret);
}
.docs-liste {
  list-style: none;
  margin: var(--e-1) 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.doc-pastille {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  padding: 2px 2px 2px 10px;
  background: var(--surface-2);
  border: 1px solid var(--bordure);
  border-radius: var(--r-rond);
  color: var(--texte);
}
.doc-pastille > .icone { flex-shrink: 0; color: var(--accent-texte); }
.doc-nom {
  min-width: 0;
  max-width: 240px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.doc-tronque {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  flex-shrink: 0;
  color: var(--avert);
  font-size: var(--t-xs);
}
.doc-retirer { width: 26px; height: 26px; border-radius: var(--r-rond); flex-shrink: 0; }
</style>
