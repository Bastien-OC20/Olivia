<template>
  <Transition name="fade">
    <div
      v-if="settings.open"
      class="overlay"
      @click.self="settings.hide()"
      @keydown.esc="settings.hide()"
    >
      <div
        ref="modalEl"
        class="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <header>
          <h2 id="settings-title">
            ⚙️ Paramètres
          </h2>
          <button
            ref="closeBtn"
            class="x"
            aria-label="Fermer les paramètres"
            @click="settings.hide()"
          >
            ✕
          </button>
        </header>

        <nav
          class="tabs"
          aria-label="Sections des paramètres"
        >
          <button
            v-for="t in tabs"
            :key="t.id"
            :class="{ active: tab === t.id }"
            :aria-pressed="tab === t.id"
            @click="tab = t.id"
          >
            {{ t.label }}
          </button>
        </nav>

        <div class="body">
          <!-- RAISONNEMENT & TON -->
          <section
            v-if="tab === 'reasoning'"
            aria-label="Raisonnement et ton"
          >
            <div class="field">
              <label for="f-style">Style de raisonnement</label>
              <select
                id="f-style"
                v-model="settings.data.reasoning_style"
              >
                <option value="concise">
                  Concis (court, direct)
                </option>
                <option value="balanced">
                  Équilibré
                </option>
                <option value="detailed">
                  Détaillé (étape par étape)
                </option>
                <option value="creative">
                  Créatif (idées originales)
                </option>
                <option value="analytical">
                  Analytique (POURQUOI → ÉTAPES → CONSÉQUENCES)
                </option>
              </select>
            </div>
            <div class="field">
              <label for="f-tone">Ton de réponse</label>
              <select
                id="f-tone"
                v-model="settings.data.tone"
              >
                <option value="neutral">
                  Neutre
                </option>
                <option value="friendly">
                  Amical
                </option>
                <option value="formal">
                  Formel
                </option>
                <option value="teacher">
                  Pédagogue
                </option>
              </select>
            </div>
            <div
              v-if="!simple"
              class="field"
            >
              <label for="f-device">Périphérique de calcul</label>
              <select
                id="f-device"
                v-model="settings.data.compute_device"
              >
                <option value="gpu">
                  GPU (rapide, cartes récentes)
                </option>
                <option value="cpu">
                  CPU (compatible partout, petits modèles)
                </option>
              </select>
              <p class="hint">
                Le choix filtre les modèles recommandés et force le calcul CPU si besoin
                (<code>num_gpu=0</code>). Modifiable aussi depuis la barre du haut.
              </p>
            </div>
            <div
              v-if="!simple"
              class="field"
            >
              <label for="f-fsroots">📁 Dossiers de documents accessibles</label>
              <textarea
                id="f-fsroots"
                v-model="fsRootsText"
                rows="3"
                placeholder="C:\Users\vous\Documents"
              />
              <p class="hint">
                Un dossier par ligne. Ajoutez un libellé après une barre verticale :
                C:\Dossier | Mes documents. Olivia ne peut lire et écrire que dans ces dossiers.
                Laissez vide pour utiliser Documents. Appliqué après Enregistrer.
              </p>
            </div>
            <div class="field">
              <label for="f-temp">Température : {{ Number(settings.data.temperature).toFixed(2) }}</label>
              <input
                id="f-temp"
                v-model.number="settings.data.temperature"
                type="range"
                min="0"
                max="2"
                step="0.05"
              >
            </div>
            <div
              v-if="!simple"
              class="field"
            >
              <label for="f-sys">Prompt système personnalisé</label>
              <textarea
                id="f-sys"
                v-model="settings.data.system_prompt"
                rows="5"
                placeholder="Laisse vide pour utiliser uniquement les directives de style/ton."
              />
            </div>
          </section>

          <!-- RECHERCHE WEB -->
          <section
            v-if="tab === 'search'"
            aria-label="Recherche web"
          >
            <div class="field">
              <label for="f-prov">Fournisseur de recherche</label>
              <select
                id="f-prov"
                v-model="settings.data.search_provider"
              >
                <option value="duckduckgo">
                  DuckDuckGo (sans clé, scraping fragile)
                </option>
                <option value="searxng">
                  SearXNG local (recommandé)
                </option>
                <option value="brave">
                  Brave Search (clé API requise)
                </option>
              </select>
            </div>
            <div
              v-if="settings.data.search_provider === 'searxng'"
              class="field"
            >
              <label for="f-searx">URL SearXNG</label>
              <input
                id="f-searx"
                v-model="settings.data.searxng_url"
                placeholder="http://localhost:8888"
              >
              <p class="hint">
                Métamoteur installé sur cette machine : il interroge plusieurs moteurs à la
                fois (Google, DuckDuckGo…) sans qu'aucun compte ni clé ne soit nécessaire.
                Son fichier <code>settings.yml</code> doit autoriser le format
                <code>json</code>, sinon la recherche renvoie une erreur 403.
              </p>
            </div>
            <div
              v-if="settings.data.search_provider === 'brave'"
              class="field"
            >
              <p class="hint">
                Définissez la variable d'environnement
                <code>BRAVE_API_KEY=votre-clé</code> avant de lancer le backend.
              </p>
            </div>

            <div class="field">
              <label for="f-testq">Tester la recherche</label>
              <div class="row">
                <input
                  id="f-testq"
                  v-model="testQuery"
                  placeholder="Ex : météo Paris"
                  @keydown.enter.prevent="testSearch"
                >
                <button
                  :disabled="!testQuery.trim() || searching"
                  @click="testSearch"
                >
                  {{ searching ? '…' : '🔍 Tester' }}
                </button>
              </div>
            </div>
            <div
              v-if="searchTest"
              class="search-test"
              aria-live="polite"
            >
              <div
                v-for="(r, i) in searchTest"
                :key="i"
                class="result"
              >
                <a
                  :href="r.url"
                  target="_blank"
                  rel="noopener noreferrer"
                >{{ r.title || r.url }}</a>
                <div class="snippet">
                  {{ r.snippet }}
                </div>
              </div>
              <div
                v-if="searchTest.length === 0"
                class="hint"
              >
                Aucun résultat.
              </div>
            </div>
          </section>

          <!-- CONNECTEURS -->
          <section
            v-if="tab === 'connectors'"
            aria-label="Connexions externes"
          >
            <p class="hint">
              ℹ️ Ces connexions sont en général préparées <b>une seule fois</b> par votre
              service informatique. Une fois activées, elles apparaissent dans la barre d'outils.
            </p>
            <h3>📬 Boîte mail professionnelle (IMAP)</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.imap.enabled"
                type="checkbox"
              >
              Activer la connexion IMAP
            </label>
            <div class="field">
              <label>Libellé affiché</label>
              <input
                v-model="settings.data.connectors.imap.label"
                placeholder="Boîte pro"
              >
            </div>
            <div class="field">
              <label>Serveur IMAP</label>
              <input
                v-model="settings.data.connectors.imap.host"
                placeholder="imap.gmail.com"
              >
            </div>
            <div class="field">
              <label>Utilisateur (email)</label>
              <input
                v-model="settings.data.connectors.imap.user"
                placeholder="vous@pro.fr"
              >
            </div>
            <div class="field">
              <label>Mot de passe d'application</label>
              <input
                v-model="settings.data.connectors.imap.password"
                type="password"
                placeholder="16 caractères Gmail / token Outlook"
                autocomplete="off"
              >
            </div>
            <div class="field">
              <label>Dossier</label>
              <input
                v-model="settings.data.connectors.imap.folder"
                placeholder="INBOX"
              >
            </div>
            <p class="warn">
              ⚠️ Stocké en clair dans <code>backend/settings.json</code> local.
              <strong>Activez uniquement sur une machine de confiance.</strong>
              Production : lib <code>keyring</code> (coffre OS) prévue dans requirements.txt.
            </p>

            <h3>🎓 Outil métier — École Directe</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.ecole_directe.enabled"
                type="checkbox"
              >
              Activer École Directe
            </label>
            <div class="field">
              <label>Identifiant</label>
              <input
                v-model="settings.data.connectors.ecole_directe.username"
                autocomplete="off"
              >
            </div>
            <div class="field">
              <label>Mot de passe</label>
              <input
                v-model="settings.data.connectors.ecole_directe.password"
                type="password"
                autocomplete="off"
              >
            </div>
            <p class="warn">
              🟡 Squelette : École Directe n'a pas d'API publique officielle. L'appel réel
              (API non officielle) reste à implémenter côté utilisateur.
            </p>

            <h3>🏛️ Outil métier — Service-Public / gouv.fr</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.service_public.enabled"
                type="checkbox"
              >
              Activer Service-Public / gouv.fr
            </label>
            <div class="field">
              <label>URL de base</label>
              <input v-model="settings.data.connectors.service_public.base_url">
            </div>
            <div class="field">
              <label>client_id (FranceConnect)</label>
              <input v-model="settings.data.connectors.service_public.client_id">
            </div>
            <p class="warn">
              🟡 Squelette : FranceConnect exige un enregistrement partenaire officiel
              (habilitation + secrets délivrés par l'État).
            </p>

            <h3>📅 Calendrier (.ics local)</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.calendar_ics.enabled"
                type="checkbox"
              >
              Activer calendrier local
            </label>
            <div class="field">
              <label>Chemin du fichier .ics</label>
              <input
                v-model="settings.data.connectors.calendar_ics.path"
                placeholder="C:\\Users\\vous\\cal.ics"
              >
            </div>

            <h3>🔐 OAuth Gmail</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.gmail_oauth.enabled"
                type="checkbox"
              >
              Activer Gmail OAuth
            </label>
            <div class="field">
              <label>client_id</label>
              <input v-model="settings.data.connectors.gmail_oauth.client_id">
            </div>
            <div class="field">
              <label>Chemin de client_secret.json</label>
              <input v-model="settings.data.connectors.gmail_oauth.client_secret_path">
            </div>

            <h3>🔐 OAuth Microsoft / Outlook</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.outlook_oauth.enabled"
                type="checkbox"
              >
              Activer Outlook OAuth
            </label>
            <div class="field">
              <label>client_id</label>
              <input v-model="settings.data.connectors.outlook_oauth.client_id">
            </div>
            <div class="field">
              <label>tenant_id</label>
              <input v-model="settings.data.connectors.outlook_oauth.tenant_id">
            </div>

            <h3>📝 Obsidian</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.obsidian.enabled"
                type="checkbox"
              >
              Activer Obsidian
            </label>
            <div class="field">
              <label>Chemin du coffre</label>
              <input v-model="settings.data.connectors.obsidian.vault_path">
            </div>

            <h3>🔗 Notion</h3>
            <label class="checkbox">
              <input
                v-model="settings.data.connectors.notion.enabled"
                type="checkbox"
              >
              Activer Notion
            </label>
            <div class="field">
              <label>Token d'intégration</label>
              <input
                v-model="settings.data.connectors.notion.api_token"
                type="password"
                placeholder="secret_..."
                autocomplete="off"
              >
            </div>
          </section>

          <!-- CONFIDENTIALITÉ / RGPD -->
          <section
            v-if="tab === 'privacy'"
            aria-label="Confidentialité et données personnelles"
          >
            <h3>🔒 Vos données</h3>
            <p class="hint">
              Olivia fonctionne <b>entièrement sur cette machine</b>. Aucune donnée
              (conversations, fichiers, identifiants) n'est transmise à un serveur externe.
              Les paramètres sont stockés dans <code>backend/settings.json</code>.
            </p>

            <h3>Droit d'accès et de portabilité</h3>
            <p class="hint">
              Exportez l'ensemble de vos paramètres et données locales au format JSON.
            </p>
            <button @click="exportData">
              ⬇ Exporter mes données
            </button>

            <h3>Droit à l'effacement</h3>
            <p class="warn">
              Réinitialise <strong>tous les paramètres</strong> et supprime les fichiers importés
              via l'application (dossier <code>_uploads</code>). Vos autres documents ne sont pas touchés.
              Action irréversible.
            </p>
            <button
              class="danger"
              @click="deleteData"
            >
              🗑 Supprimer mes données locales
            </button>
            <p
              v-if="privacyMsg"
              class="hint"
              aria-live="polite"
            >
              {{ privacyMsg }}
            </p>
          </section>
        </div>

        <footer>
          <button
            class="link-btn"
            type="button"
            @click="toggleAdvanced"
          >
            {{ simple ? '🔧 Réglages avancés' : '← Revenir au mode simple' }}
          </button>
          <div class="footer-actions">
            <button
              class="ghost"
              @click="settings.hide()"
            >
              Annuler
            </button>
            <button
              :disabled="settings.saving"
              @click="save"
            >
              💾 Enregistrer
            </button>
          </div>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch, nextTick } from 'vue'
import { useSettingsStore } from '../stores/settings.js'

const settings = useSettingsStore()
const tab = ref('reasoning')
const simple = computed(() => settings.data.simple_mode !== false)
const allTabs = [
  { id: 'reasoning', label: 'Préférences', simple: true },
  { id: 'search', label: 'Recherche web', simple: false },
  { id: 'connectors', label: 'Connexions', simple: false },
  { id: 'privacy', label: 'Confidentialité', simple: true },
]
const tabs = computed(() => (simple.value ? allTabs.filter(t => t.simple) : allTabs))

// Textarea "un dossier par ligne" <-> tableau fs_roots.
// Chaque ligne : "chemin" ou "chemin | libellé". Entrées objet {path, label}
// ou chaînes héritées en entrée ; toujours des objets en sortie.
const fsRootsText = computed({
  get: () => (settings.data.fs_roots || []).map((entry) => {
    if (entry && typeof entry === 'object') {
      return entry.label ? `${entry.path} | ${entry.label}` : entry.path
    }
    return entry
  }).join('\n'),
  set: (val) => {
    settings.data.fs_roots = val.split('\n').map((line) => {
      const trimmed = line.trim()
      if (!trimmed) return null
      const idx = trimmed.indexOf('|')
      if (idx === -1) return { path: trimmed, label: '' }
      return { path: trimmed.slice(0, idx).trim(), label: trimmed.slice(idx + 1).trim() }
    }).filter(Boolean)
  },
})

// Bascule mode simple ↔ avancé (persistée)
async function toggleAdvanced() {
  const goSimple = !simple.value
  settings.data.simple_mode = goSimple
  if (goSimple && !allTabs.find(t => t.id === tab.value)?.simple) tab.value = 'reasoning'
  await settings.save({ simple_mode: goSimple })
}

const testQuery = ref('')
const searchTest = ref(null)
const searching = ref(false)
const privacyMsg = ref('')
const modalEl = ref(null)
const closeBtn = ref(null)

// Accessibilité : au focus à l'ouverture de la modale
watch(() => settings.open, async (o) => {
  if (o) { await nextTick(); closeBtn.value?.focus() }
})

async function testSearch() {
  if (!testQuery.value.trim()) return
  searching.value = true
  searchTest.value = null
  try {
    const r = await fetch('/api/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: testQuery.value, limit: 5 })
    })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
    searchTest.value = data.results || []
  } catch (e) {
    alert('Erreur recherche : ' + e.message)
  } finally {
    searching.value = false
  }
}

async function exportData() {
  try {
    const r = await fetch('/api/privacy/export')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const blob = await r.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'mes-donnees-local-ai.json'
    a.click()
    URL.revokeObjectURL(url)
  } catch (e) {
    alert('Export impossible : ' + e.message)
  }
}

async function deleteData() {
  if (!confirm('Supprimer TOUS vos paramètres et les fichiers importés via l\'app ? Cette action est irréversible.')) return
  try {
    const r = await fetch('/api/privacy/delete', { method: 'POST' })
    const data = await r.json()
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`)
    await settings.load()
    privacyMsg.value = `Données supprimées (${data.uploads_removed} fichier(s) importé(s) retiré(s)). Paramètres réinitialisés.`
  } catch (e) {
    alert('Suppression impossible : ' + e.message)
  }
}

async function save() {
  const result = await settings.save()
  if (!result?.ok) {
    alert('Enregistrement impossible : ' + (result?.error || 'erreur inconnue'))
    return
  }
  settings.hide()
}

// Exposé pour permettre à App.vue d'ouvrir directement l'onglet RGPD
defineExpose({ goToPrivacy: () => { tab.value = 'privacy' } })
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  background: var(--panel); width: 720px; max-width: 90vw;
  max-height: 88vh; border-radius: 10px;
  display: flex; flex-direction: column; overflow: hidden;
  border: 1px solid var(--border);
}
header { display: flex; justify-content: space-between; align-items: center;
         padding: 14px 20px; border-bottom: 1px solid var(--border); }
header h2 { margin: 0; font-size: 17px; }
.tabs { display: flex; gap: 4px; padding: 8px 12px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.tabs button { background: var(--panel-2); color: var(--text); padding: 6px 12px; font-size: 13px; }
.tabs button.active { background: var(--accent); color: white; }
.body { padding: 20px; overflow-y: auto; flex: 1; }
.field { margin-bottom: 14px; }
.field label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 4px; }
.field textarea, .field input, .field select { width: 100%; }
.row { display: flex; gap: 8px; align-items: stretch; }
.row input { flex: 1; }
.row button { white-space: nowrap; }
.checkbox { display: flex; gap: 8px; align-items: center; margin: 10px 0; }
.checkbox input[type="checkbox"] { width: auto; margin: 0; }
.hint, .warn { font-size: 12px; padding: 10px; border-radius: 4px; line-height: 1.5; }
.hint { color: var(--muted); background: var(--panel-2); }
.warn { color: var(--warn); background: rgba(245,158,11,0.08); border: 1px solid rgba(245,158,11,0.3); margin: 8px 0; }
.hint code, .warn code { background: rgba(255,255,255,0.08); padding: 1px 4px; border-radius: 3px; font-family: monospace; }
h3 { font-size: 14px; margin: 20px 0 8px; padding-top: 12px; border-top: 1px solid var(--border); }
h3:first-child { border-top: none; padding-top: 0; margin-top: 0; }
.search-test { margin-top: 12px; }
.result { padding: 8px; border-bottom: 1px solid var(--border); }
.result a { color: var(--accent); text-decoration: none; font-size: 13px; }
.result .snippet { font-size: 12px; color: var(--muted); margin-top: 4px; line-height: 1.4; }
.danger { background: var(--danger); }
footer { padding: 12px 20px; border-top: 1px solid var(--border);
         display: flex; justify-content: space-between; align-items: center; gap: 10px; }
.footer-actions { display: flex; gap: 10px; }
footer .ghost { background: var(--panel-2); color: var(--text); }
.link-btn { background: transparent; color: var(--muted); padding: 6px 8px; font-size: 13px; }
.link-btn:hover { color: var(--accent); opacity: 1; }
.x { background: transparent; font-size: 18px; }
</style>
