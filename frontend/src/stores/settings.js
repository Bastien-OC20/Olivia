import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { copier, fusionner, restaurer } from '../reglages.js'
import { appliquerTheme, themeEffectif } from '../theme.js'

// Doit rester aligné sur DEVICE_MODELS de backend/settings.py.
const DEVICE_MODELS = {
  // mistral-nemo reste en 2e position : sur un poste pas encore mis à jour, il sert
  // en attendant que le panneau « pas encore prête » fasse télécharger ministral-3.
  gpu: ["ministral-3:8b", "mistral-nemo:12b-instruct-2407-q4_K_M", "qwen3:8b", "qwen2.5-coder:7b",
        "llama3.3:8b", "qwen2.5-vl:7b", "phi4-mini:3.8b"],
  cpu: ["qwen3:4b", "qwen3:1.7b", "phi4-mini:3.8b", "gemma2:2b"],
  leger: ["qwen2.5:1.5b"],
}

const DEFAULTS = {
  system_prompt: "Tu es un assistant IA local. Réponds en français, clair et structuré.",
  temperature: 0.7,
  reasoning_style: "balanced",
  tone: "neutral",
  compute_device: "gpu",
  device_models: DEVICE_MODELS,
  simple_mode: true,
  // Thème de l'interface : systeme | sombre | clair (aligné sur backend/settings.py).
  // « systeme » suit Windows ; c'est aussi ce qui s'affiche après la déconnexion.
  theme: "systeme",
  search_provider: "duckduckgo",
  searxng_url: "http://localhost:8888",
  // Clé Brave Search : secret, renvoyé masqué par le serveur (jamais en clair).
  search_brave_api_key: "",
  search_official_only: false,
  // Reconnaissance de caractères sur les documents scannés (voir backend/ocr.py).
  // Activée par défaut, comme côté backend : sans cela un PDF passé au scanner
  // resterait introuvable sans que l'utilisatrice comprenne pourquoi.
  ocr_enabled: true,
  ocr_tesseract_path: "",
  // Pas de réglage d'emplacement du modèle Word : il est fixé par le backend,
  // un par organisation (voir backend/docmodele.py, chemin_modele).
  docgen_appel: "",
  docgen_formule_politesse: "",
  docgen_lieu: "",
  docgen_signature: "",
  fs_roots: [],
  // Consultation autonome des documents, mails et agenda (lecture seule) ; réglage
  // du responsable, absent de CLES_MEMBRE. Sans effet hors mode GPU (côté serveur).
  outils_actifs: true,
  privacy_consent: false,
  connectors: {
    imap: { enabled: false, label: "Boîte pro", host: "", user: "", password: "", folder: "INBOX" },
    calendar_ics: { enabled: false, path: "" },
    obsidian: { enabled: false, vault_path: "" },
    notion: { enabled: false, api_token: "" },
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const data = ref(copier(DEFAULTS))
  // Dernière version ENREGISTRÉE (reçue du serveur). Les champs de la fenêtre sont liés
  // directement à `data` : « Annuler » rétablit cette copie. Elle suit tous les
  // enregistrements, y compris ceux de la barre du haut (⚡ 🧩 🪶) : ils ne sont donc
  // jamais défaits par une annulation.
  const enregistre = ref(copier(DEFAULTS))
  const open = ref(false)
  const saving = ref(false)
  // Vrai une fois les réglages de l'organisation reçus du serveur. Avant, `data`
  // contient les valeurs par défaut (ex. privacy_consent = false) qui ne doivent
  // déclencher aucun affichage, comme le bandeau de confidentialité.
  const charge = ref(false)
  // { chiffres: bool, a_ressaisir: [noms] } d'après le serveur ; null si inconnu.
  const etatSecrets = ref(null)

  // Thème : il suit `data` (et non `enregistre`) pour un aperçu immédiat dans les
  // Paramètres. « Annuler » (hide → restaurer) et la déconnexion (reset) remplacent
  // `data`, ce qui réapplique le thème enregistré ou « Suivre Windows » sans autre code.
  // matchMedia peut manquer (contexte sans fenêtre) : on suppose alors le sombre.
  const mq = typeof window !== 'undefined' && typeof window.matchMedia === 'function'
    ? window.matchMedia('(prefers-color-scheme: dark)')
    : null
  function appliquer() {
    if (typeof document === 'undefined') return
    appliquerTheme(document.documentElement, themeEffectif(data.value.theme, mq ? mq.matches : true))
  }
  watch(() => data.value.theme, appliquer, { immediate: true })
  // Windows passe du clair au sombre : seul « systeme » doit suivre ; les deux
  // autres réglages donnent le même résultat, réappliquer est sans effet.
  mq?.addEventListener?.('change', appliquer)

  /** Réglages reçus du serveur : ils deviennent à la fois l'affichage et la référence. */
  function adopter(recus) {
    // `etat_secrets` n'est pas un réglage : il est gardé à part pour ne jamais
    // repartir dans le PUT.
    const { etat_secrets: etat, ...reglages } = recus || {}
    etatSecrets.value = etat && typeof etat === 'object' ? etat : null
    data.value = fusionner(DEFAULTS, reglages)
    enregistre.value = copier(data.value)
    charge.value = true
  }

  async function load() {
    try {
      const r = await fetch('/api/settings')
      if (r.ok) adopter(await r.json())
    } catch (e) { console.error('Impossible de charger les paramètres :', e) }
  }

  async function save(patch) {
    saving.value = true
    try {
      const r = await fetch('/api/settings', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(patch ?? data.value)
      })
      const body = await r.json().catch(() => null)
      if (r.ok) {
        adopter(body)
        return { ok: true }
      }
      const error = body?.detail || `HTTP ${r.status}`
      console.error('Sauvegarde échouée :', error)
      return { ok: false, error }
    } catch (e) {
      console.error('Sauvegarde échouée :', e)
      return { ok: false, error: e.message }
    } finally { saving.value = false }
  }

  function show() { open.value = true }
  /** Ferme la fenêtre. Ce qui n'a pas été enregistré est abandonné : après un
   *  enregistrement réussi, `data` et `enregistre` sont identiques, rien ne change. */
  function hide() {
    if (open.value) data.value = restaurer(enregistre.value)
    open.value = false
  }

  /** Revient aux valeurs par défaut (déconnexion). Les réglages appartiennent à
   *  l'organisation et contiennent des secrets (identifiants de connecteurs) :
   *  ceux du compte précédent ne doivent pas rester en mémoire pour le suivant. */
  function reset() {
    data.value = copier(DEFAULTS)
    enregistre.value = copier(DEFAULTS)
    etatSecrets.value = null
    charge.value = false
    open.value = false
  }

  return { data, open, saving, charge, etatSecrets, load, save, show, hide, reset }
})
