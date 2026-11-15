import { defineStore } from 'pinia'
import { ref, computed, nextTick } from 'vue'
import { useMoteurStore } from './moteur.js'
import { useTableauxStore } from './tableaux.js'
import {
  sujetCommandeTableau, messagesTableau,
  analyserSchema, schemaExploitable, titreTableau, versMermaid, sceneDepuisMermaid,
} from '../tableauIA.js'
import {
  DOC_MAX, reponseApplicable, idAAppliquerApresEnregistrement, normaliserDocuments,
  documentsPourEnvoi, documentDepuisTexte, avisDocumentsIndisponibles, fusionnerDocuments,
} from '../conversationDocs.js'

// Recherche web : nombre de résultats injectés et longueur max de la requête
// envoyée au moteur (une demande de chat peut être un paragraphe entier).
const WEB_SEARCH_LIMIT = 5
const WEB_QUERY_MAX = 300

// Moteur d'IA (Ollama) injoignable : même texte que MESSAGE_OLLAMA_INJOIGNABLE
// côté backend (main.py), pour que l'utilisatrice lise la même consigne quel que
// soit le moment où la panne est constatée. Le détail (installer ou démarrer
// Ollama, modèles à tirer) est dans le panneau MoteurAssistant.vue.
const MESSAGE_MOTEUR_ETEINT = "Le moteur d'IA (Ollama) ne répond pas : il n'est pas "
  + 'démarré, ou pas installé sur ce poste. Suivez les indications affichées en haut '
  + 'de la fenêtre, puis réessayez.'
// Olivia elle-même ne répond plus (le backend s'est arrêté). Le remède dépend de
// la façon dont elle a été lancée : dans l'application de bureau, pas de fenêtre
// noire, mais l'icône Olivia (desktop/main.js, menu « Redémarrer Olivia ») ;
// sinon, c'est la fenêtre noire du lanceur qui a été fermée.
const MESSAGE_OLIVIA_INJOIGNABLE = (typeof window !== 'undefined' && window.oliviaBureau)
  ? "Oliv'IA ne répond plus. Cliquez sur l'icône Oliv'IA (barre des menus sur Mac, zone "
    + 'de notification sous Windows), choisissez « Redémarrer Oliv\'IA », puis réessayez.'
  : "Oliv'IA ne répond pas. Vérifiez que sa fenêtre noire est toujours ouverte (sinon, "
    + 'relancez Oliv\'IA), puis réessayez.'

// ---------- Contexte documentaire ----------
// Un petit modèle local n'a qu'une fenêtre de contexte limitée : on borne donc
// ce qui est injecté, par document ET au total. Quand un document est coupé,
// l'interface DOIT le dire (voir `fileContextPlan`) — Olivia ne doit jamais
// répondre sur un extrait partiel sans que cela se voie.
const DOC_CHARS_MAX = 8000         // par document (un seul document : inchangé)
const DOC_CHARS_TOTAL = 24000      // budget global, tous documents confondus
const DOC_CHARS_MIN = 1200         // part plancher pour qu'un document reste utile

/** Répartit le budget de contexte entre les documents retenus. */
function planDocuments(docs) {
  if (!docs.length) return []
  const part = Math.max(DOC_CHARS_MIN, Math.floor(DOC_CHARS_TOTAL / docs.length))
  const budget = Math.min(DOC_CHARS_MAX, part)
  return docs.map((d) => {
    const full = d.content || ''
    const kept = full.slice(0, budget)
    return {
      path: d.path,
      name: d.name || d.path,
      chars: full.length,
      keptChars: kept.length,
      content: kept,
      // `sourceTruncated` : le document était déjà trop long côté serveur.
      truncated: kept.length < full.length || !!d.sourceTruncated,
    }
  })
}

/** Bloc de contexte injecté avant la demande : un document par section. */
function withDocuments(plan) {
  const blocs = plan.map((d) => {
    const fin = d.truncated ? '\n[… suite du document non transmise …]' : ''
    return `--- Document : ${d.name} (${d.path}) ---\n${d.content}${fin}`
  }).join('\n\n')
  const pluriel = plan.length > 1 ? 's' : ''
  return `Voici le contenu de ${plan.length} document${pluriel} fourni${pluriel} par ` +
    `l'utilisatrice. Appuie-toi dessus si c'est pertinent, et précise de quel ` +
    `document vient chaque information.\n\n${blocs}`
}

async function fetchWebResults(query, signal) {
  const r = await fetch('/api/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query: query.slice(0, WEB_QUERY_MAX), limit: WEB_SEARCH_LIMIT }),
    signal
  })
  const data = await r.json().catch(() => null)
  if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
  return data?.results || []
}

/** Reformule la demande de l'utilisateur en y joignant les résultats web numérotés. */
function withWebContext(question, results) {
  const today = new Date().toLocaleDateString('fr-FR',
    { day: 'numeric', month: 'long', year: 'numeric' })
  const sources = results.map((r, i) =>
    `[${i + 1}] ${r.title || r.url}\n${r.url}\n${r.snippet || ''}`.trim()).join('\n\n')
  return `Résultats d'une recherche web effectuée le ${today} :\n\n${sources}\n\n` +
    'Appuie-toi sur ces résultats pour répondre à la demande ci-dessous et cite tes ' +
    'sources par leur numéro entre crochets ([1], [2]…). Si les résultats ne ' +
    "permettent pas de répondre, dis-le simplement plutôt que d'inventer.\n\n" +
    `Demande : ${question}`
}

/** Titre par défaut d'une conversation : début de la première demande. */
function deriveTitle(msgs) {
  const first = msgs.find((m) => m.role === 'user')
  const raw = (first?.content || '').replace(/\s+/g, ' ').trim()
  if (!raw) return 'Nouvelle conversation'
  return raw.length > 60 ? `${raw.slice(0, 60)}…` : raw
}

export const useChatStore = defineStore('chat', () => {
  const messages = ref([])
  const isStreaming = ref(false)
  const isSearching = ref(false)
  const currentModel = ref('')
  const availableModels = ref([])
  const abortController = ref(null)

  // Documents joints à la conversation (plusieurs, contrairement à l'ancien
  // « contexte actif » qui n'en acceptait qu'un).
  const fileContexts = ref([])
  const fileContextPlan = computed(() => planDocuments(fileContexts.value))
  const fileContextNotice = ref('')

  /** Ajoute un document au contexte (sans doublon). Renvoie false si refusé. */
  function addFileContext(doc) {
    if (!doc || !doc.path) return false
    if (fileContexts.value.some((d) => d.path === doc.path)) {
      fileContextNotice.value = `« ${doc.name || doc.path} » est déjà dans la conversation.`
      return true
    }
    if (fileContexts.value.length >= DOC_MAX) {
      fileContextNotice.value = `Maximum ${DOC_MAX} documents à la fois — retirez-en un.`
      return false
    }
    fileContexts.value.push(doc)
    fileContextNotice.value = ''
    enregistrerDocuments()
    return true
  }

  function removeFileContext(path) {
    fileContexts.value = fileContexts.value.filter((d) => d.path !== path)
    fileContextNotice.value = ''
    enregistrerDocuments()
  }

  function clearFileContexts() {
    fileContexts.value = []
    fileContextNotice.value = ''
    enregistrerDocuments()
  }

  // Historique des conversations (persistées côté backend).
  const conversations = ref([])
  const currentId = ref(null)
  // Vrai si le backend ne sait pas gérer l'historique : l'interface le signale
  // sans se casser (les routes peuvent être absentes d'une ancienne version).
  const historyUnavailable = ref(false)

  // Contexte = une « visite » d'une conversation (ouverte, ou nouvelle). Un nouveau
  // contexte est créé à chaque ouverture ou nouvelle conversation. Tout ce qui est
  // asynchrone (enregistrement, rechargement des documents) garde le contexte qui
  // l'a lancé et ne touche l'écran que si c'est encore le contexte actif : sinon la
  // réponse tardive d'une conversation A venait écraser la conversation B affichée.
  //   id       : identifiant de la conversation enregistrée (null si jamais enregistrée)
  //   messages : tableau des messages de CETTE conversation (reste valable hors écran)
  //   docs     : documents joints, figés quand on quitte le contexte
  let contexte = { id: null, messages: messages.value, docs: null }
  // Jeton de la dernière ouverture demandée : deux clics rapides, seule la dernière compte.
  let demandeOuverture = {}

  function docsDe(ctx) { return ctx === contexte ? fileContexts.value : (ctx.docs || []) }

  /** Bascule l'affichage sur une autre conversation (ou une vierge). */
  function changerContexte(id, msgs, docs) {
    contexte.docs = fileContexts.value
    messages.value = msgs
    fileContexts.value = docs
    fileContextNotice.value = ''
    currentId.value = id
    contexte = { id, messages: messages.value, docs: null }
  }

  /**
   * `recommandes` : noms de modèles déjà triés par pertinence pour l'appareil
   * de calcul actuel (voir `DEVICE_MODELS` dans backend/settings.py). Sans ce
   * paramètre, le choix par défaut retomberait sur `availableModels[0]` —
   * l'ordre renvoyé par Ollama, qui ne reflète ni une recommandation ni même
   * un ordre stable (un modèle tout juste installé peut apparaître en tête).
   */
  // Raison pour laquelle aucun modèle n'est disponible (moteur éteint, aucun
  // modèle installé), affichée si l'utilisatrice envoie quand même un message.
  const modelsErreur = ref('')
  // Derniers modèles conseillés reçus : réutilisés quand `send()` retente le
  // chargement (moteur démarré après l'ouverture de la page).
  let derniersRecommandes = []

  async function loadModels(recommandes = derniersRecommandes) {
    derniersRecommandes = recommandes
    try {
      const r = await fetch('/api/models')
      const data = await r.json().catch(() => ({}))
      if (!r.ok) {
        availableModels.value = []
        modelsErreur.value = r.status === 502 ? MESSAGE_MOTEUR_ETEINT
          : `Liste des modèles indisponible (erreur ${r.status}).`
        if (r.status === 502) useMoteurStore().signalerPanne()
        return
      }
      availableModels.value = data.models || []
      modelsErreur.value = availableModels.value.length ? ''
        : "Aucun modèle de conversation n'est installé sur ce poste. "
          + 'Suivez les indications affichées en haut de la fenêtre.'
      if (!availableModels.value.length) useMoteurStore().signalerPanne()
      if (availableModels.value.length && !currentModel.value) {
        const noms = new Set(availableModels.value.map((m) => m.name))
        const conseille = recommandes.find((n) => noms.has(n))
        currentModel.value = conseille || availableModels.value[0].name
      }
    } catch (e) {
      console.error('Impossible de charger les modèles :', e)
      modelsErreur.value = MESSAGE_OLIVIA_INJOIGNABLE
    }
  }

  // ---------- Historique des conversations ----------

  /** Ne conserve que les champs utiles (dont sources / searchNote, qui doivent
   *  survivre à un rechargement de page). */
  function serialize(msgs) {
    return msgs.map((m) => ({
      role: m.role,
      content: m.content,
      sources: m.sources || [],
      searchNote: m.searchNote || '',
      erreur: m.erreur || '',
      // Tableau créé par /tableau : garde le bouton « Ouvrir le tableau ».
      ...(m.tableau ? { tableau: m.tableau } : {}),
    }))
  }

  async function loadConversations() {
    try {
      const r = await fetch('/api/conversations')
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      conversations.value = Array.isArray(data) ? data : (data.conversations || [])
      historyUnavailable.value = false
    } catch (e) {
      conversations.value = []
      historyUnavailable.value = true
      console.warn('Historique des conversations indisponible :', e.message)
    }
  }

  /** Contenu d'un document joint, rechargé depuis le disque (jamais stocké avec la
   *  conversation). Même objet que celui que FileExplorer.vue passe à addFileContext. */
  async function chargerDocument(d) {
    const r = await fetch(`/api/fs/text?path=${encodeURIComponent(d.path)}`)
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    return documentDepuisTexte(d.path, d.name, data)
  }

  /** Recharge les documents d'une conversation ouverte. Un document devenu illisible
   *  (supprimé, dossier retiré) n'est pas rattaché, et l'utilisatrice en est prévenue. */
  async function rechargerDocuments(ctx, liste) {
    const resultats = await Promise.all(liste.map(async (d) => {
      try { return { doc: await chargerDocument(d) } } catch { return { nom: d.name } }
    }))
    if (ctx !== contexte) return        // on a changé de conversation entre-temps
    const recharges = resultats.filter((r) => r.doc).map((r) => r.doc)
    fileContexts.value = fusionnerDocuments(fileContexts.value, recharges)
    fileContextNotice.value = avisDocumentsIndisponibles(
      resultats.filter((r) => !r.doc).map((r) => r.nom))
  }

  async function openConversation(id) {
    if (isStreaming.value) stop()
    const jeton = {}
    demandeOuverture = jeton
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`)
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const data = await r.json()
      // Un clic plus récent (autre conversation, ou « Nouvelle ») a pris la main.
      if (!reponseApplicable(jeton, demandeOuverture)) return
      if (isStreaming.value) stop()
      changerContexte(data.id ?? id, (data.messages || []).map((m) => ({
        role: m.role,
        content: m.content || '',
        sources: m.sources || [],
        searchNote: m.searchNote || '',
        erreur: m.erreur || '',
        ...(m.tableau ? { tableau: m.tableau } : {}),
      })), [])
      historyUnavailable.value = false
      const aRecharger = normaliserDocuments(data.documents)
      if (aRecharger.length) await rechargerDocuments(contexte, aRecharger)
    } catch (e) {
      if (!reponseApplicable(jeton, demandeOuverture)) return
      historyUnavailable.value = true
      console.warn('Ouverture de la conversation impossible :', e.message)
    }
  }

  /** Repart d'une conversation vierge, sans document joint. Rien n'est envoyé au
   *  backend tant que le premier échange n'est pas terminé : une conversation vide
   *  ne crée aucune entrée dans l'historique. */
  function newConversation() {
    if (isStreaming.value) stop()
    demandeOuverture = {}              // annule une ouverture encore en attente
    changerContexte(null, [], [])
  }

  async function renameConversation(id, titre) {
    const title = (titre || '').trim()
    if (!title) return false
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title }),
      })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      const item = conversations.value.find((c) => c.id === id)
      if (item) item.title = title
      await loadConversations()
      return true
    } catch (e) {
      console.warn('Renommage impossible :', e.message)
      return false
    }
  }

  async function deleteConversation(id) {
    try {
      const r = await fetch(`/api/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!r.ok) throw new Error(`HTTP ${r.status}`)
      conversations.value = conversations.value.filter((c) => c.id !== id)
      if (currentId.value === id) newConversation()
      return true
    } catch (e) {
      console.warn('Suppression impossible :', e.message)
      return false
    }
  }

  // Les écritures partent l'une après l'autre : deux enregistrements d'une conversation
  // neuve ne créent pas deux entrées, et un envoi tardif n'écrase pas un plus récent.
  let fileEcriture = Promise.resolve()
  function enfiler(tache) {
    const suite = fileEcriture.then(tache, tache)
    fileEcriture = suite.catch(() => {})
    return suite
  }

  /** Écrit la conversation `ctx` (messages et documents joints). Le contenu des
   *  documents n'est jamais envoyé, seulement leur chemin et leur nom. */
  function ecrire(ctx, avecMessages) {
    return enfiler(async () => {
      const msgs = ctx.messages || []
      if (avecMessages && !msgs.length) return
      const body = { documents: documentsPourEnvoi(docsDe(ctx)) }
      if (avecMessages) body.messages = serialize(msgs)
      try {
        let r
        if (ctx.id) {
          r = await fetch(`/api/conversations/${encodeURIComponent(ctx.id)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
        } else {
          if (!avecMessages) return        // rien à enregistrer pour l'instant
          body.title = deriveTitle(msgs)
          r = await fetch('/api/conversations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
        }
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        const data = await r.json().catch(() => null)
        // Création : l'identifiant revient à CETTE conversation, qu'elle soit encore
        // à l'écran ou non ; l'affichage n'est touché que si elle y est toujours.
        if (!ctx.id && data?.id) ctx.id = data.id
        const aAppliquer = idAAppliquerApresEnregistrement(ctx, contexte, ctx.id)
        if (aAppliquer) currentId.value = aAppliquer
        historyUnavailable.value = false
        if (avecMessages) await loadConversations()
      } catch (e) {
        historyUnavailable.value = true
        console.warn('Sauvegarde de la conversation impossible :', e.message)
      }
    })
  }

  /** Sauvegarde d'une conversation (par défaut la courante). Appelée UNIQUEMENT à la
   *  fin du streaming (ou quand l'utilisatrice interrompt) — jamais à chaque token.
   *  `ctx` est capturé au départ de l'échange : la fin d'une réponse de A ne doit
   *  jamais enregistrer ce qui est affiché pour B. */
  function persist(ctx = contexte) { return ecrire(ctx, true) }

  /** Documents joints ajoutés ou retirés dans une conversation DÉJÀ enregistrée :
   *  enregistrés tout de suite, pour ne rien perdre si l'on change de conversation
   *  avant le prochain message. Sans identifiant, ils partent avec le premier échange. */
  function enregistrerDocuments() {
    if (contexte.id) ecrire(contexte, false)
  }

  async function send(userMessage, useWebSearch = false) {
    if (isStreaming.value) return
    const ctx = contexte
    // Aucun modèle choisi : le plus souvent, Ollama était éteint au chargement
    // de la page. Il a pu démarrer depuis, on retente une fois. Auparavant,
    // l'envoi était abandonné en silence — et la zone de saisie déjà vidée :
    // le message tapé disparaissait sans réponse ni explication.
    if (!currentModel.value) await loadModels()
    if (ctx !== contexte || isStreaming.value) return   // l'écran a changé pendant l'attente
    if (!currentModel.value) {
      messages.value.push({ role: 'user', content: userMessage })
      messages.value.push({
        role: 'assistant', content: '', sources: [], searchNote: '',
        erreur: modelsErreur.value || MESSAGE_MOTEUR_ETEINT,
      })
      await persist(ctx)
      return
    }
    messages.value.push({ role: 'user', content: userMessage })
    isStreaming.value = true
    messages.value.push({ role: 'assistant', content: '', sources: [], searchNote: '', erreur: '' })
    // On reprend l'élément DEPUIS le tableau : Vue renvoie alors un proxy réactif.
    // Écrire sur l'objet brut d'origine ne déclencherait aucun rendu — la réponse
    // n'apparaîtrait qu'à la toute fin du streaming, et la comparaison
    // « m === assistantMsg » plus bas échouerait (proxy ≠ objet brut).
    const assistantMsg = messages.value[messages.value.length - 1]
    abortController.value = new AbortController()

    // Recherche web (bouton 🌐 du composeur) : on interroge le moteur AVANT
    // d'appeler le modèle, puis on injecte les résultats dans la demande.
    // Un échec du moteur ne bloque pas la réponse : on prévient et on continue.
    let webResults = []
    if (useWebSearch) {
      isSearching.value = true
      try {
        webResults = await fetchWebResults(userMessage, abortController.value.signal)
        assistantMsg.sources = webResults
        if (webResults.length === 0) {
          assistantMsg.searchNote = 'Aucun résultat web trouvé — réponse basée sur les '
            + 'seules connaissances du modèle.'
        }
      } catch (e) {
        if (e.name === 'AbortError') {
          isSearching.value = false
          isStreaming.value = false
          abortController.value = null
          return
        }
        assistantMsg.searchNote = `Recherche web indisponible (${e.message}) — réponse `
          + 'basée sur les seules connaissances du modèle.'
      } finally {
        isSearching.value = false
      }
    }

    // Contexte documentaire : tous les documents joints, dans la limite du budget.
    const ollamaMessages = []
    const plan = fileContextPlan.value
    if (plan.length) {
      ollamaMessages.push({ role: 'user', content: withDocuments(plan) })
    }
    for (const m of ctx.messages) {
      if (m === assistantMsg) continue
      // Un tour d'Olivia sans texte est une réponse en échec (son erreur vit à
      // part, dans `erreur`) : l'envoyer au modèle comme une réponse vide ne
      // lui apprendrait rien et pourrait l'inciter à répondre vide à son tour.
      if (m.role === 'assistant' && !(m.content || '').trim()) continue
      ollamaMessages.push({ role: m.role, content: m.content })
    }

    // Les résultats web enrichissent la DERNIÈRE demande (et non le début de
    // l'historique) : les petits modèles locaux suivent mieux un contexte récent.
    if (webResults.length) {
      const last = ollamaMessages[ollamaMessages.length - 1]
      last.content = withWebContext(userMessage, webResults)
    }

    try {
      const r = await fetch('/api/chat/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: currentModel.value,
          messages: ollamaMessages,
          stream: true
        }),
        signal: abortController.value.signal
      })
      if (!r.ok) throw new Error(`Oliv'IA ne répond pas (erreur ${r.status}).`)
      const reader = r.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let termine = false
      lecture: while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''
        for (const line of lines) {
          if (!line.startsWith('data:')) continue
          let payload
          try {
            payload = JSON.parse(line.slice(5).trim())
          } catch {
            continue           // ligne incomplète ou étrangère au protocole
          }
          // Erreur du moteur (Ollama éteint, modèle absent…), envoyée par le
          // backend ou par Ollama en cours de réponse. Auparavant ignorée :
          // l'utilisatrice voyait une bulle vide, sans explication.
          if (payload.error) {
            assistantMsg.erreur = String(payload.error)
            termine = true
            break lecture
          }
          if (payload.message?.content) {
            assistantMsg.content += payload.message.content
          }
          if (payload.done) {
            // Plafond de génération atteint (num_predict, voir backend) : la
            // réponse est coupée, il faut le dire avant qu'elle soit recopiée.
            if (payload.done_reason === 'length') {
              assistantMsg.erreur = 'Réponse coupée : longueur maximale atteinte. '
                + 'Demandez la suite, ou une version plus courte.'
            }
            termine = true
            break lecture
          }
        }
      }
      if (!termine) {
        assistantMsg.erreur = 'La réponse s\'est interrompue avant la fin. Réessayez.'
      } else if (!assistantMsg.content.trim() && !assistantMsg.erreur) {
        assistantMsg.erreur = 'Le modèle n\'a produit aucun texte. Réessayez, '
          + 'éventuellement en reformulant la demande.'
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        // TypeError = le navigateur n'a pas pu joindre Olivia elle-même
        // (« Failed to fetch ») : message en anglais, inutile tel quel.
        assistantMsg.erreur = e instanceof TypeError
          ? MESSAGE_OLIVIA_INJOIGNABLE
          : (e.message || 'Erreur inconnue.')
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
      // Échec sans aucun texte produit : moteur arrêté, modèle désinstallé…
      // On revérifie l'état du moteur pour réafficher le panneau d'aide si
      // besoin (sans effet si le moteur va bien : l'erreur venait d'ailleurs).
      if (assistantMsg.erreur && !assistantMsg.content) useMoteurStore().signalerPanne()
      // Sauvegarde en fin de streaming, y compris après un « Stop ».
      await persist(ctx)
    }
  }

  // ---------- Commande /tableau ----------

  const AIDE_TABLEAU = 'Écrivez ce que vous voulez schématiser après /tableau, par exemple : '
    + "/tableau étapes de l'inscription d'un élève"
  const ECHEC_SCHEMA = "Oliv'IA n'a pas réussi à produire un schéma à partir de cette demande. "
    + 'Reformulez-la plus simplement (par exemple « /tableau étapes de … »), '
    + 'puis réessayez.'
  const ECHEC_DESSIN = "Oliv'IA a imaginé un schéma, mais n'a pas pu le dessiner dans le "
    + 'tableau blanc. Réessayez, ou reformulez la demande.'

  /**
   * `/tableau <sujet>` : Oliv'IA fait écrire un schéma par le modèle (format simple,
   * voir tableauIA.js), le dessine dans un nouveau tableau blanc Excalidraw, puis
   * l'ouvre. Même cycle de vie que `send()` : composeur bloqué et bouton Stop
   * pendant le travail, erreurs affichées sur la réponse, sauvegarde en fin.
   */
  async function creerTableau(userMessage) {
    if (isStreaming.value) return
    const ctx = contexte
    const sujet = sujetCommandeTableau(userMessage)
    if (sujet === null) return
    const texteSaisi = userMessage.trim()

    if (!sujet) {
      messages.value.push({ role: 'user', content: texteSaisi })
      messages.value.push({
        role: 'assistant', content: AIDE_TABLEAU, sources: [], searchNote: '', erreur: '',
      })
      await persist(ctx)
      return
    }
    if (!currentModel.value) await loadModels()
    if (ctx !== contexte || isStreaming.value) return   // l'écran a changé pendant l'attente
    if (!currentModel.value) {
      messages.value.push({ role: 'user', content: texteSaisi })
      messages.value.push({
        role: 'assistant', content: '', sources: [], searchNote: '',
        erreur: modelsErreur.value || MESSAGE_MOTEUR_ETEINT,
      })
      await persist(ctx)
      return
    }

    messages.value.push({ role: 'user', content: texteSaisi })
    isStreaming.value = true
    messages.value.push({ role: 'assistant', content: '', sources: [], searchNote: '', erreur: '' })
    // Proxy réactif repris depuis le tableau, comme dans send().
    const assistantMsg = messages.value[messages.value.length - 1]
    abortController.value = new AbortController()
    const signal = abortController.value.signal
    let aOuvrir = null

    // Historique transmis au modèle : la conversation jusqu'ici (documents joints
    // compris), sans les anciennes commandes /tableau ni leurs confirmations, qui
    // l'inciteraient à répondre par une phrase plutôt que par le format demandé.
    const base = []
    const plan = fileContextPlan.value
    if (plan.length) base.push({ role: 'user', content: withDocuments(plan) })
    for (const m of ctx.messages.slice(0, -2)) {
      if (m.tableau || (m.role === 'user' && sujetCommandeTableau(m.content) !== null)) continue
      if (m.role === 'assistant' && !(m.content || '').trim()) continue
      base.push({ role: m.role, content: m.content })
    }

    // Réponse non diffusée : il faut le texte entier avant de pouvoir dessiner.
    async function demanderSchema(consignes) {
      const r = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          model: currentModel.value,
          messages: [...base, ...consignes],
          stream: false,
          // Format strict à respecter : on bride la fantaisie du modèle.
          temperature: 0.2,
        }),
        signal,
      })
      if (!r.ok) {
        if (r.status === 502) throw new Error(MESSAGE_MOTEUR_ETEINT)
        throw new Error(`Oliv'IA ne répond pas (erreur ${r.status}).`)
      }
      const data = await r.json().catch(() => null)
      return data?.message?.content || ''
    }

    try {
      let schema = analyserSchema(await demanderSchema(messagesTableau(sujet)))
      // Un petit modèle rate parfois le format : une seule nouvelle tentative,
      // avec un rappel plus strict.
      if (!schemaExploitable(schema)) {
        schema = analyserSchema(await demanderSchema(messagesTableau(sujet, true)))
      }
      if (!schemaExploitable(schema)) {
        assistantMsg.erreur = ECHEC_SCHEMA
      } else {
        let scene = null
        try {
          scene = await sceneDepuisMermaid(versMermaid(schema))
        } catch (e) {
          console.error('Dessin du schéma impossible :', e)
          assistantMsg.erreur = ECHEC_DESSIN
        }
        // Stop pressé pendant le dessin : rien n'est créé.
        if (scene && !signal.aborted) {
          const cree = await useTableauxStore().creerAvecScene(titreTableau(schema, sujet), scene)
          assistantMsg.content = `J'ai créé le tableau « ${cree.titre} » : `
            + `${schema.noeuds.length} éléments reliés. Vous pouvez le modifier librement ; `
            + "il est aussi dans l'onglet 🎨 Tableaux."
          assistantMsg.tableau = { id: cree.id, titre: cree.titre }
          aOuvrir = cree.id
        }
      }
    } catch (e) {
      if (e.name !== 'AbortError') {
        assistantMsg.erreur = e instanceof TypeError
          ? MESSAGE_OLIVIA_INJOIGNABLE
          : (e.message || 'Erreur inconnue.')
      }
    } finally {
      isStreaming.value = false
      abortController.value = null
      if (assistantMsg.erreur && !assistantMsg.content) useMoteurStore().signalerPanne()
      // Sauvegarde AVANT d'ouvrir le tableau : à la première sauvegarde d'une
      // conversation neuve, `currentId` change et App.vue ferme alors tout tableau
      // ouvert (watch sur chat.currentId).
      await persist(ctx)
    }
    // Pas d'ouverture si l'utilisatrice a changé de conversation pendant ce temps.
    if (aOuvrir && ctx === contexte) {
      await nextTick()
      try {
        await useTableauxStore().ouvrir(aOuvrir)
      } catch (e) {
        console.warn('Ouverture du tableau impossible :', e.message)
      }
    }
  }

  function stop() {
    if (abortController.value) abortController.value.abort()
  }

  /** Vide l'affichage. La conversation déjà enregistrée reste dans l'historique :
   *  on se détache simplement d'elle (équivalent d'une nouvelle conversation). */
  function clear() { newConversation() }

  return { messages, isStreaming, isSearching, currentModel, availableModels, modelsErreur,
           conversations, currentId, historyUnavailable,
           fileContexts, fileContextPlan, fileContextNotice,
           addFileContext, removeFileContext, clearFileContexts,
           loadModels, send, creerTableau, stop, clear,
           loadConversations, openConversation, newConversation,
           renameConversation, deleteConversation }
})
