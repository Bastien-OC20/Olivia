import { defineStore } from 'pinia'
import { ref } from 'vue'

// Doit rester aligné sur DEVICE_MODELS de backend/settings.py.
const DEVICE_MODELS = {
  gpu: ["mistral-nemo:12b-instruct-2407-q4_K_M", "qwen3:8b", "qwen2.5-coder:7b",
        "llama3.3:8b", "qwen2.5-vl:7b", "phi4-mini:3.8b"],
  cpu: ["qwen3:4b", "qwen3:1.7b", "phi4-mini:3.8b", "gemma2:2b"],
}

const DEFAULTS = {
  system_prompt: "Tu es un assistant IA local. Réponds en français, clair et structuré.",
  temperature: 0.7,
  reasoning_style: "balanced",
  tone: "neutral",
  compute_device: "gpu",
  device_models: DEVICE_MODELS,
  simple_mode: true,
  search_provider: "duckduckgo",
  searxng_url: "http://localhost:8888",
  search_official_only: false,
  // Reconnaissance de caractères sur les documents scannés (voir backend/ocr.py).
  // Activée par défaut, comme côté backend : sans cela un PDF passé au scanner
  // resterait introuvable sans que l'utilisatrice comprenne pourquoi.
  ocr_enabled: true,
  ocr_tesseract_path: "",
  // Modèle Word de l'établissement (voir backend/docgen.py). Vide = modèle par
  // défaut dans modeles/, à côté de l'application.
  docgen_template_path: "",
  docgen_appel: "",
  docgen_formule_politesse: "",
  docgen_lieu: "",
  docgen_signature: "",
  fs_roots: [],
  privacy_consent: false,
  connectors: {
    imap: { enabled: false, label: "Boîte pro", host: "", user: "", password: "", folder: "INBOX" },
    calendar_ics: { enabled: false, path: "" },
    obsidian: { enabled: false, vault_path: "" },
    notion: { enabled: false, api_token: "" },
  }
}

export const useSettingsStore = defineStore('settings', () => {
  const data = ref(JSON.parse(JSON.stringify(DEFAULTS)))
  const open = ref(false)
  const saving = ref(false)

  function _merge(base, loaded) {
    const out = JSON.parse(JSON.stringify(base))
    for (const k in loaded) {
      if (loaded[k] && typeof loaded[k] === 'object' && !Array.isArray(loaded[k]) && out[k]) {
        out[k] = { ...out[k], ...loaded[k] }
        // fusion profonde du niveau connecteurs
        if (k === 'connectors') {
          for (const c in loaded[k]) out[k][c] = { ...(base.connectors[c] || {}), ...loaded[k][c] }
        }
      } else {
        out[k] = loaded[k]
      }
    }
    return out
  }

  async function load() {
    try {
      const r = await fetch('/api/settings')
      if (r.ok) data.value = _merge(DEFAULTS, await r.json())
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
        data.value = _merge(DEFAULTS, body)
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
  function hide() { open.value = false }

  /** Revient aux valeurs par défaut (déconnexion). Les réglages appartiennent à
   *  l'organisation et contiennent des secrets (identifiants de connecteurs) :
   *  ceux du compte précédent ne doivent pas rester en mémoire pour le suivant. */
  function reset() {
    data.value = JSON.parse(JSON.stringify(DEFAULTS))
    open.value = false
  }

  return { data, open, saving, load, save, show, hide, reset }
})
