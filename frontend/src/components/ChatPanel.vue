<template>
  <div class="chat">
    <!-- Conversation vide : écran d'accueil, avec la saisie au centre. -->
    <AccueilVue
      v-if="chat.messages.length === 0"
      @action="lancerAction"
      @ouvrir-conversation="ouvrirConversation"
      @ouvrir-tableau="tableaux.ouvrir($event)"
    >
      <template #saisie>
        <!-- Documents joints : même bandeau qu'en conversation. -->
        <DocumentsJoints />

        <ZoneSaisie
          ref="saisieEl"
          v-model="input"
          v-model:recherche="webSearch"
          accueil
          :en-cours="chat.isStreaming"
          @envoyer="send"
          @stop="chat.stop()"
          @joindre="emit('ouvrir-documents')"
        />
      </template>
    </AccueilVue>

    <template v-else>
      <div
        ref="messagesEl"
        class="messages"
      >
        <div class="stream">
          <div
            v-for="(m, i) in chat.messages"
            :key="i"
            :class="['msg', m.role]"
          >
            <strong
              v-if="m.role === 'user'"
              class="sr-only"
            >Vous</strong>
            <div
              v-else
              class="auteur"
            >
              <img
                :src="logoUrl"
                alt=""
                class="auteur-logo"
                width="26"
                height="26"
              >
              <strong>Oliv'IA</strong>
            </div>
            <div
              v-if="m.role === 'user'"
              class="bulle"
            >
              {{ m.content }}
            </div>
            <div
              v-else
              class="reponse"
            >
              <MessageBubble
                :content="m.content"
                :streaming="chat.isStreaming && i === chat.messages.length - 1"
              />
            </div>
            <p
              v-if="m.searchNote"
              class="avert"
            >
              <Icone
                nom="alerte"
                :taille="14"
              />
              <span>{{ m.searchNote }}</span>
            </p>
            <!-- Erreur du moteur d'IA sur ce tour : affichée à part, jamais mêlée
                 au texte de la réponse (qui est renvoyé au modèle). -->
            <p
              v-if="m.erreur"
              class="erreur-modele"
              role="alert"
            >
              <Icone
                nom="alerte"
                :taille="16"
              />
              <span>{{ m.erreur }}</span>
            </p>
            <details
              v-if="m.sources && m.sources.length"
              class="sources"
            >
              <summary>
                <Icone
                  nom="globe"
                  :taille="14"
                />
                {{ m.sources.length }} source{{ m.sources.length > 1 ? 's' : '' }} web
              </summary>
              <ol>
                <li
                  v-for="(s, j) in m.sources"
                  :key="j"
                >
                  <a
                    :href="s.url"
                    target="_blank"
                    rel="noopener noreferrer"
                  >{{ s.title || s.url }}</a>
                </li>
              </ol>
            </details>

            <div
              v-if="m.tableau || peutCreerDocument(m, i)"
              class="reponse-actions"
            >
              <!-- Tableau blanc créé par la commande /tableau. -->
              <button
                v-if="m.tableau"
                type="button"
                class="btn btn-fantome btn-compact"
                @click="tableaux.ouvrir(m.tableau.id)"
              >
                <Icone
                  nom="tableau"
                  :taille="16"
                />
                Ouvrir le tableau
              </button>

              <!-- Transformer une réponse d'Olivia en document Word. C'est le geste
                   attendu par un secrétariat : la réponse existe, il ne reste qu'à
                   la mettre en page. Toujours visible, y compris en mode simple. -->
              <button
                v-if="peutCreerDocument(m, i)"
                type="button"
                class="btn btn-fantome btn-compact"
                @click="ouvrirCreation(i)"
              >
                <Icone
                  nom="document"
                  :taille="16"
                />
                Créer un document Word
              </button>
            </div>

            <div
              v-if="creation.index === i"
              class="carte doc-form"
            >
              <fieldset class="doc-types">
                <legend>Type de document</legend>
                <button
                  v-for="t in typesDocument"
                  :key="t.id"
                  type="button"
                  class="doc-type"
                  :class="{ actif: creation.type === t.id }"
                  :aria-pressed="creation.type === t.id"
                  @click="creation.type = t.id"
                >
                  {{ t.libelle }}
                </button>
              </fieldset>

              <label :for="`doc-titre-${i}`">Titre</label>
              <input
                :id="`doc-titre-${i}`"
                v-model="creation.titre"
                placeholder="Titre du document"
              >

              <template v-if="besoinObjet">
                <label :for="`doc-objet-${i}`">Objet</label>
                <input
                  :id="`doc-objet-${i}`"
                  v-model="creation.objet"
                  placeholder="Ex. : conseil de classe du 12 octobre"
                >
                <label :for="`doc-dest-${i}`">Destinataire</label>
                <textarea
                  :id="`doc-dest-${i}`"
                  v-model="creation.destinataire"
                  rows="2"
                  placeholder="Aux responsables légaux&#10;des élèves de seconde"
                />
                <label :for="`doc-signature-${i}`">Signature</label>
                <input
                  :id="`doc-signature-${i}`"
                  v-model="creation.signature"
                  placeholder="Ex. : La Proviseure"
                >
              </template>

              <template v-if="creation.type === 'compte_rendu'">
                <label :for="`doc-part-${i}`">Participants</label>
                <textarea
                  :id="`doc-part-${i}`"
                  v-model="creation.participants"
                  rows="2"
                  placeholder="Un participant par ligne"
                />
              </template>

              <p
                v-if="modeleAbsent"
                class="avert"
              >
                <Icone
                  nom="alerte"
                  :taille="14"
                />
                <span>{{ modeleEtat.message }}</span>
              </p>

              <div class="doc-actions">
                <button
                  type="button"
                  class="btn btn-primaire"
                  :disabled="!!creation.etape"
                  @click="creerDocument"
                >
                  <Icone
                    v-if="!creation.etape"
                    nom="coche"
                    :taille="16"
                  />
                  {{ creation.etape || 'Créer le document' }}
                </button>
                <button
                  type="button"
                  class="btn btn-secondaire"
                  @click="creation.index = null"
                >
                  Annuler
                </button>
              </div>
              <p
                v-if="creation.erreur"
                class="avert"
                aria-live="polite"
              >
                <Icone
                  nom="alerte"
                  :taille="14"
                />
                <span>{{ creation.erreur }}</span>
              </p>
            </div>

            <div
              v-if="documentCree && documentCree.index === i"
              class="carte doc-done"
              aria-live="polite"
            >
              <p class="doc-done-titre">
                <Icone
                  nom="coche"
                  :taille="18"
                  class="ok"
                />
                <span><strong>{{ documentCree.name }}</strong> créé dans vos documents.</span>
              </p>
              <p
                v-if="documentCree.avertissement"
                class="avert"
              >
                <Icone
                  nom="alerte"
                  :taille="14"
                />
                <span>{{ documentCree.avertissement }}</span>
              </p>
              <div class="doc-actions">
                <button
                  type="button"
                  class="btn btn-secondaire"
                  @click="apercuOuvert = !apercuOuvert"
                >
                  <Icone
                    nom="oeil"
                    :taille="16"
                  />
                  {{ apercuOuvert ? 'Masquer l’aperçu' : 'Aperçu' }}
                </button>
                <a
                  class="btn btn-secondaire"
                  :href="`/api/fs/download?path=${encodeURIComponent(documentCree.path)}`"
                  download
                >
                  <Icone
                    nom="telecharger"
                    :taille="16"
                  />
                  Télécharger
                </a>
              </div>
              <FilePreview
                v-if="apercuOuvert"
                :path="documentCree.path"
                @close="apercuOuvert = false"
              />
            </div>
          </div>
          <div
            v-if="chat.isSearching"
            class="searching"
            aria-live="polite"
          >
            <Icone
              nom="globe"
              :taille="16"
            />
            Recherche sur le web…
          </div>
          <div
            v-if="chat.isStreaming && !chat.isSearching
              && (chat.messages[chat.messages.length-1]?.content || '') === ''"
            class="typing"
          >
            <span /><span /><span />
          </div>
        </div>
      </div>

      <div class="composer">
        <div class="composer-inner">
          <!-- Documents joints : rangée de pastilles juste au-dessus de la saisie. -->
          <DocumentsJoints />

          <ZoneSaisie
            ref="saisieEl"
            v-model="input"
            v-model:recherche="webSearch"
            :en-cours="chat.isStreaming"
            @envoyer="send"
            @stop="chat.stop()"
            @joindre="emit('ouvrir-documents')"
          />
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onMounted, reactive } from 'vue'
import { useChatStore } from '../stores/chat.js'
import { useTableauxStore } from '../stores/tableaux.js'
import { sujetCommandeTableau } from '../tableauIA.js'
import MessageBubble from './MessageBubble.vue'
import FilePreview from './FilePreview.vue'
import AccueilVue from './AccueilVue.vue'
import ZoneSaisie from './ZoneSaisie.vue'
import DocumentsJoints from './DocumentsJoints.vue'
import Icone from './Icone.vue'
import logoUrl from '../assets/logo-mark.png'

const emit = defineEmits(['ouvrir-documents'])

const chat = useChatStore()
const tableaux = useTableauxStore()
const input = ref('')
const messagesEl = ref(null)
const saisieEl = ref(null)
// Recherche web : choix explicite de l'utilisatrice, conservé d'un message à l'autre.
const webSearch = ref(false)

/** Carte d'action de l'accueil (voir ACTIONS_ACCUEIL dans accueil.js). */
async function lancerAction(action) {
  if (action.type === 'envoyer') {
    chat.send(action.texte, webSearch.value)
  } else if (action.type === 'preremplir') {
    // Reformuler ou résumer sans texte n'a pas de sens : la demande est posée
    // dans la saisie, l'utilisatrice la complète.
    input.value = action.texte
    await nextTick()
    saisieEl.value?.focus()
  } else if (action.type === 'documents') {
    emit('ouvrir-documents')
  }
}

// Même geste que dans la liste des conversations : ouvrir ramène à la conversation.
function ouvrirConversation(id) {
  chat.openConversation(id)
  tableaux.fermer()
}

const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches

function scrollToBottom(smooth = false) {
  const el = messagesEl.value
  if (!el) return
  el.scrollTo({ top: el.scrollHeight, behavior: smooth && !prefersReduced ? 'smooth' : 'auto' })
}

// Nouveau message ajouté → défilement doux
watch(() => chat.messages.length, async () => {
  await nextTick()
  scrollToBottom(true)
})

// Contenu du dernier message qui grandit (streaming) → suivi instantané
watch(() => chat.messages[chat.messages.length - 1]?.content, async () => {
  await nextTick()
  scrollToBottom(false)
})

function send() {
  if (!input.value.trim()) return
  // « /tableau <sujet> » : schéma dessiné dans un tableau blanc, pas une réponse écrite.
  if (sujetCommandeTableau(input.value) !== null) chat.creerTableau(input.value)
  else chat.send(input.value, webSearch.value)
  input.value = ''
}

// ---------- Production de documents Word ----------
// Le texte de la réponse EST le contenu : aucun appel supplémentaire au modèle.
// La mise en page (styles, en-tête, logo) est faite côté serveur par docgen.
const TYPES_REPLI = [
  { id: 'circulaire', libelle: 'Circulaire' },
  { id: 'courrier', libelle: 'Courrier aux familles' },
  { id: 'convocation', libelle: 'Convocation' },
  { id: 'compte_rendu', libelle: 'Compte rendu' },
]
const typesDocument = ref(TYPES_REPLI)
const modeleEtat = ref({ disponible: true, message: '' })
const modeleAbsent = computed(() => modeleEtat.value.disponible === false)

const creation = reactive({
  index: null, type: 'circulaire', titre: '', objet: '',
  destinataire: '', signature: '', participants: '',
  etape: '', erreur: '',
})
const documentCree = ref(null)
const apercuOuvert = ref(false)

// Le formulaire et la carte « document créé » sont repérés par le NUMÉRO du message :
// sans remise à zéro, le 2e message de n'importe quelle autre conversation héritait
// de la carte (ou du formulaire ouvert) de la précédente. Le store remplace le
// tableau `messages` à chaque changement de conversation (ouverture, nouvelle,
// effacement, suppression : `changerContexte`), jamais pendant un échange (ajouts
// seulement) ni quand l'enregistrement attribue l'identifiant : c'est donc le signal
// juste, sans regarder en profondeur. Un document en cours de création reste créé
// dans les Documents ; seule sa carte n'est pas affichée ailleurs.
watch(() => chat.messages, () => {
  creation.index = null
  creation.erreur = ''
  documentCree.value = null
  apercuOuvert.value = false
})

const besoinObjet = computed(
  () => creation.type === 'courrier' || creation.type === 'convocation'
)

/** Bouton proposé sur une réponse d'Olivia terminée et non vide. */
function peutCreerDocument(m, i) {
  if (m.role !== 'assistant') return false
  // Le message d'un tableau créé n'est pas un texte à mettre en page.
  if (m.tableau) return false
  if (chat.isStreaming && i === chat.messages.length - 1) return false
  return (m.content || '').trim().length > 0
}

/** Titre pré-rempli : premier titre Markdown, sinon début de la réponse. */
function titreSuggere(texte) {
  const propre = (texte || '').replace(/<think>[\s\S]*?<\/think>/gi, '')
  for (const ligne of propre.split('\n')) {
    const nue = ligne.trim()
    if (!nue) continue
    const titre = nue.match(/^#{1,6}\s+(.*)$/)
    if (titre) return titre[1].trim().slice(0, 90)
    // La réponse commence parfois par sa propre ligne "Objet : …" — sans ce
    // retrait, ce champ pré-remplit aussi `creation.objet` (voir
    // ouvrirCreation), et docgen.py y ajoute SON PROPRE préfixe "Objet : " :
    // le document afficherait "Objet : Objet : …".
    const sansObjet = nue.replace(/^objet\s*:\s*/i, '')
    return sansObjet.replace(/\*\*/g, '').split(' ').slice(0, 10).join(' ').slice(0, 90)
  }
  return ''
}

function ouvrirCreation(i) {
  creation.index = i
  creation.erreur = ''
  creation.titre = titreSuggere(chat.messages[i]?.content)
  creation.objet = creation.objet || creation.titre
  documentCree.value = null
  apercuOuvert.value = false
}

async function chargerEtatModele() {
  try {
    const r = await fetch('/api/documents/status')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const data = await r.json()
    modeleEtat.value = data
    if (Array.isArray(data.types) && data.types.length) typesDocument.value = data.types
  } catch (e) {
    // Un back-end plus ancien n'expose pas cette route : le bouton reste utile,
    // il échouera proprement s'il n'y a vraiment rien en face.
    console.warn('État du modèle de document indisponible :', e.message)
  }
}

// Rédaction dirigée : la réponse d'Olivia, telle qu'affichée dans la conversation,
// est une lettre complète (objet, appel, corps, formule de politesse, signature).
// Le document produit par docgen.py pose déjà ces éléments lui-même (voir
// PROFILS) : les garder ferait doublon. Un nettoyage par expressions régulières
// existe côté serveur (`_degarnir`) mais reste approximatif — chaque
// reformulation invente sa propre clôture. On demande donc au modèle de
// reformuler SON PROPRE texte en corps seul avant de le transmettre : mesuré à
// l'usage, ça élimine fiablement objet/appel/clôture/signature/titre en
// quelques secondes. `_degarnir` reste le filet de sécurité si cet appel
// échoue ou si le modèle laisse malgré tout un résidu.
const DIRECTIVE_REDACTION = (texte) => (
  "Reformule le texte suivant pour qu'il devienne UNIQUEMENT le corps d'un document " +
  "administratif déjà mis en forme : retire tout titre, tout objet, toute formule " +
  "d'ouverture (Madame/Monsieur ou équivalent), toute formule de politesse de clôture " +
  "et toute signature — le document les ajoute déjà lui-même séparément, les répéter " +
  'ferait doublon. Commence directement par la première phrase utile du message. Garde ' +
  'le contenu en paragraphes clairs, sans aucune mise en forme (pas de gras, pas de ' +
  "markdown), sans commentaire ni note. Réponds uniquement par le texte reformulé.\n\n" +
  `Texte à reformuler :\n${texte}`
)

/** Repli sur le texte d'origine si la réécriture échoue : jamais bloquant. */
async function redigerCorps(texteOriginal) {
  if (!chat.currentModel || !texteOriginal.trim()) return texteOriginal
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: chat.currentModel,
        messages: [{ role: 'user', content: DIRECTIVE_REDACTION(texteOriginal) }],
        stream: false,
      }),
    })
    if (!r.ok) return texteOriginal
    const data = await r.json()
    const reecrit = (data?.message?.content || '')
      .replace(/<think>[\s\S]*?<\/think>/gi, '').trim()
    return reecrit || texteOriginal
  } catch {
    return texteOriginal
  }
}

async function creerDocument() {
  // Conversation et message figés au départ : la rédaction prend plusieurs
  // secondes, et l'utilisatrice peut changer de conversation entre-temps. Le
  // document est créé quoi qu'il arrive ; sa carte (ou l'erreur) ne s'affiche que
  // si la même conversation est toujours à l'écran.
  const conversation = chat.messages
  const index = creation.index
  const message = conversation[index]
  if (!message) return
  creation.erreur = ''
  try {
    creation.etape = 'Rédaction…'
    const corps = await redigerCorps(message.content || '')
    creation.etape = 'Création…'
    const r = await fetch('/api/documents/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        type: creation.type,
        titre: creation.titre,
        objet: besoinObjet.value ? creation.objet : '',
        destinataire: besoinObjet.value ? creation.destinataire : '',
        signature: besoinObjet.value ? creation.signature : '',
        participants: creation.type === 'compte_rendu'
          ? creation.participants.split('\n').map((s) => s.trim()).filter(Boolean)
          : [],
        texte: corps,
      }),
    })
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    if (chat.messages !== conversation) return
    documentCree.value = { ...data, index }
    creation.index = null
    apercuOuvert.value = false
  } catch (e) {
    if (chat.messages !== conversation) return
    creation.erreur = `Création impossible : ${e.message}`
  } finally {
    creation.etape = ''
  }
}

onMounted(chargerEtatModele)
</script>

<style scoped>
.chat { display: flex; flex-direction: column; height: 100%; }

/* Avertissement (texte + icône) : documents, recherche web, modèle de document */
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

/* ---------- Messages ---------- */
.messages { flex: 1; overflow-y: auto; padding: var(--e-5) var(--e-4) var(--e-4); }
/* Colonne de lecture centrée (confort de lecture, style Claude Desktop) */
.stream { max-width: 760px; margin: 0 auto; }
.msg { margin-bottom: var(--e-5); animation: msg-in 0.22s ease; }
@keyframes msg-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

/* Message tapé par l'utilisatrice : texte brut, bulle alignée à droite */
.msg.user { display: flex; flex-direction: column; align-items: flex-end; }
.bulle {
  max-width: 80%;
  padding: 10px 14px;
  background: var(--bulle-utilisatrice);
  color: var(--texte);
  border-radius: var(--r-3) var(--r-3) var(--r-1) var(--r-3);
  white-space: pre-wrap;
  word-wrap: break-word;
  overflow-wrap: anywhere;
  line-height: 1.5;
}

/* Réponse d'Olivia : pleine largeur, sans bulle (comme Claude Desktop) */
.auteur { display: flex; align-items: center; gap: var(--e-2); margin-bottom: 6px; }
.auteur-logo { width: 26px; height: 26px; display: block; flex-shrink: 0; }
.auteur strong { font-size: var(--t-s); font-weight: 600; color: var(--texte); }
.reponse { padding: 2px 0; word-wrap: break-word; }

.erreur-modele {
  display: flex;
  align-items: flex-start;
  gap: var(--e-2);
  margin: var(--e-2) 0 0;
  padding: 10px 12px;
  font-size: var(--t-s);
  line-height: 1.4;
  color: var(--texte);
  background: color-mix(in srgb, var(--danger) 12%, transparent);
  border: 1px solid var(--danger);
  border-radius: var(--r-2);
}
.erreur-modele .icone { flex-shrink: 0; color: var(--danger); margin-top: 1px; }

.sources { margin-top: var(--e-2); font-size: var(--t-xs); color: var(--discret); }
.sources summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  padding: 2px 0;
}
.sources ol { margin: 6px 0 0; padding-left: 22px; }
.sources li { margin-bottom: 4px; line-height: 1.4; }
.sources a { color: var(--accent-texte); }

.reponse-actions { display: flex; flex-wrap: wrap; gap: var(--e-1); margin-top: 6px; margin-left: -10px; }

.searching {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: var(--t-s);
  color: var(--discret);
  padding: 4px 0;
}
.typing span { display: inline-block; width: 8px; height: 8px;
               background: var(--discret); border-radius: 50%;
               margin-right: 4px; animation: blink 1.4s infinite; }
.typing span:nth-child(2) { animation-delay: 0.2s; }
.typing span:nth-child(3) { animation-delay: 0.4s; }
@keyframes blink { 0%, 60%, 100% { opacity: 0.3; } 30% { opacity: 1; } }

/* ---------- Production de documents Word ---------- */
.doc-form,
.doc-done { margin-top: var(--e-2); padding: var(--e-4); font-size: var(--t-s); }
.doc-form label {
  display: block;
  margin: var(--e-3) 0 var(--e-1);
  color: var(--discret);
  font-size: var(--t-xs);
  font-weight: 500;
}
.doc-form input, .doc-form textarea { width: 100%; font-family: inherit; font-size: var(--t-s); }
.doc-types { border: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.doc-types legend { padding: 0 0 6px; color: var(--discret); font-size: var(--t-xs); font-weight: 500; }
/* Types de document : pastilles bascule */
.doc-type {
  padding: 5px 12px;
  background: var(--surface-2);
  color: var(--texte);
  border: 1px solid var(--bordure);
  border-radius: var(--r-rond);
  font-size: var(--t-s);
}
.doc-type:hover:not(:disabled) { background: var(--surface-3); border-color: var(--bordure-forte); }
.doc-type.actif,
.doc-type.actif:hover:not(:disabled) {
  background: var(--accent-doux);
  color: var(--accent-texte);
  border-color: var(--accent-texte);
}
.doc-actions {
  display: flex;
  align-items: center;
  gap: var(--e-2);
  margin-top: var(--e-3);
  flex-wrap: wrap;
}
.doc-done p { margin: 0; line-height: 1.5; }
.doc-done-titre { display: flex; align-items: flex-start; gap: var(--e-2); }
.doc-done-titre .ok { flex-shrink: 0; color: var(--ok); margin-top: 1px; }

/* ---------- Saisie en bas de la conversation ---------- */
.composer { flex-shrink: 0; padding: var(--e-2) var(--e-4) var(--e-3); }
.composer-inner { max-width: 760px; margin: 0 auto; }
</style>
