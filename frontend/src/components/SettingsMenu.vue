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
        class="modal carte"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
      >
        <header>
          <h2 id="settings-title">
            <Icone
              nom="engrenage"
              :taille="20"
            />
            Paramètres
          </h2>
          <button
            ref="closeBtn"
            class="btn-icone"
            type="button"
            aria-label="Fermer les paramètres"
            @click="settings.hide()"
          >
            <Icone
              nom="fermer"
              :taille="18"
            />
          </button>
        </header>

        <div class="centre">
          <nav
            class="tabs"
            aria-label="Sections des paramètres"
          >
            <button
              v-for="t in tabs"
              :key="t.id"
              type="button"
              class="onglet"
              :class="{ active: tab === t.id }"
              :aria-pressed="tab === t.id"
              @click="tab = t.id"
            >
              <Icone
                :nom="iconeOnglet(t.id)"
                :taille="18"
              />
              <span>{{ t.label }}</span>
            </button>
          </nav>

          <div class="body">
            <!-- RAISONNEMENT & TON -->
            <section
              v-if="tab === 'reasoning'"
              aria-label="Raisonnement et ton"
            >
              <!-- Apparence : visible de tous les comptes, dans les deux modes. L'aperçu
                   est immédiat (le store applique le thème) ; « Annuler » le défait. -->
              <fieldset class="groupe apparence">
                <legend>Apparence</legend>
                <div class="themes">
                  <label
                    v-for="th in THEMES"
                    :key="th.id"
                    class="theme"
                    :class="{ actif: settings.data.theme === th.id }"
                  >
                    <input
                      v-model="settings.data.theme"
                      type="radio"
                      class="sr-only"
                      name="apparence-theme"
                      :value="th.id"
                    >
                    <span class="theme-icone">
                      <Icone
                        :nom="th.icone"
                        :taille="20"
                      />
                    </span>
                    <span class="theme-texte">
                      <span class="theme-nom">{{ th.nom }}</span>
                      <span class="theme-aide">{{ th.aide }}</span>
                    </span>
                    <Icone
                      v-if="settings.data.theme === th.id"
                      nom="coche"
                      :taille="16"
                      class="theme-coche"
                    />
                  </label>
                </div>
              </fieldset>

              <div class="groupe">
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
                    <option value="leger">
                      Léger (postes anciens ou peu puissants, plus petit modèle)
                    </option>
                  </select>
                  <p class="hint">
                    Le choix filtre les modèles recommandés et force le calcul CPU si besoin
                    (<code>num_gpu=0</code>). Modifiable aussi depuis la barre du haut.
                  </p>
                </div>
                <div class="field">
                  <label for="f-temp">Température : {{ Number(settings.data.temperature).toFixed(2) }}</label>
                  <input
                    id="f-temp"
                    v-model.number="settings.data.temperature"
                    class="curseur"
                    type="range"
                    min="0"
                    max="2"
                    step="0.05"
                  >
                </div>
                <div
                  v-if="!simple && auth.estResponsable"
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
              </div>
            </section>

            <!-- DOCUMENTS -->
            <section
              v-if="tab === 'documents'"
              aria-label="Documents"
            >
              <p
                v-if="!auth.estResponsable"
                class="hint intro"
              >
                Les dossiers de travail, la lecture des documents scannés et le modèle
                des documents Word. {{ MESSAGE_RESERVE }}
              </p>
              <div
                v-if="!simple && auth.estResponsable"
                class="groupe"
              >
                <div class="field">
                  <label for="f-fsroots">
                    <Icone
                      nom="dossier"
                      :taille="16"
                    />
                    Dossiers de documents accessibles
                  </label>
                  <textarea
                    id="f-fsroots"
                    v-model="fsRootsText"
                    rows="3"
                    placeholder="C:\Users\vous\Documents"
                  />
                  <p class="hint">
                    Un dossier par ligne. Ajoutez un libellé après une barre verticale :
                    C:\Dossier | Mes documents. Oliv'IA ne peut lire et écrire que dans ces dossiers.
                    Laissez vide pour utiliser Documents. Appliqué après Enregistrer.
                  </p>
                </div>
              </div>

              <div
                v-if="auth.estResponsable"
                class="groupe"
              >
                <h3>
                  <Icone
                    nom="loupe"
                    :taille="18"
                  />
                  Documents scannés
                </h3>
                <div class="field">
                  <label class="checkbox">
                    <input
                      v-model="settings.data.ocr_enabled"
                      type="checkbox"
                    >
                    Lire le texte des documents scannés et des images
                  </label>
                  <p class="hint">
                    Une circulaire passée au scanner ou un courrier reçu par fax est un
                    document fait d'images : sans cette option, son texte n'apparaît dans
                    aucune recherche. Oliv'IA le déchiffre alors sur cette machine, sans
                    rien envoyer sur Internet. C'est plus lent la première fois (environ
                    une à trois secondes par page), puis le résultat est mémorisé.
                    La lecture automatique n'est jamais parfaite : les résultats obtenus
                    ainsi sont signalés par la mention « texte reconnu ».
                    Appliqué après <b>Enregistrer</b>.
                  </p>
                </div>
                <p
                  v-if="ocrState"
                  class="etat ocr-state"
                  :class="ocrState.disponible ? 'ok' : 'avert'"
                  aria-live="polite"
                >
                  <Icone
                    :nom="ocrState.disponible ? 'coche' : 'alerte'"
                    :taille="16"
                  />
                  <span>
                    {{ ocrState.message }}
                    <template v-if="ocrState.chemin">
                      <br>
                      <code>{{ ocrState.chemin }}</code>
                    </template>
                  </span>
                </p>
                <div
                  v-if="!simple"
                  class="field"
                >
                  <label for="f-ocr-path">Chemin du moteur de reconnaissance (facultatif)</label>
                  <input
                    id="f-ocr-path"
                    v-model="settings.data.ocr_tesseract_path"
                    placeholder="Laisser vide : moteur livré dans le dossier tesseract/"
                  >
                  <p class="hint">
                    Utile seulement si Tesseract est installé ailleurs sur le poste.
                    Oliv'IA cherche d'abord le moteur livré avec elle, puis celui du système.
                    Le chemin doit désigner <code>tesseract.exe</code> ou le dossier qui le
                    contient : par sécurité, tout autre programme est refusé.
                  </p>
                </div>
              </div>

              <div class="groupe">
                <h3>
                  <Icone
                    nom="etincelles"
                    :taille="18"
                  />
                  Recherche par le sens
                </h3>
                <p class="hint">
                  En plus de la recherche par mots-clés, Oliv'IA peut retrouver un document
                  d'après l'idée qu'il contient, même si les mots exacts diffèrent. L'index
                  se construit et se met à jour tout seul (au démarrage d'Oliv'IA, et après
                  chaque import de fichier), à partir du modèle local <code>bge-m3</code>
                  (via Ollama, sans rien envoyer sur Internet). Le bouton ci-dessous ne sert
                  qu'à forcer une mise à jour immédiate — par exemple après avoir modifié des
                  documents en dehors d'Oliv'IA.
                </p>
                <p
                  v-if="docIndexState"
                  class="etat doc-index-state"
                  :class="docIndexState.modele_disponible ? 'ok' : 'avert'"
                  aria-live="polite"
                >
                  <Icone
                    :nom="docIndexState.modele_disponible ? 'coche' : 'alerte'"
                    :taille="16"
                  />
                  <span>
                    {{ docIndexState.message }}
                    <template v-if="docIndexState.index_construit">
                      <br>
                      {{ docIndexState.documents }} document(s), {{ docIndexState.extraits }} extrait(s),
                      construit le {{ formatDate(docIndexState.construit_le) }}.
                    </template>
                  </span>
                </p>
                <p
                  v-if="docIndexState?.en_cours"
                  class="etat doc-index-progress"
                  aria-live="polite"
                >
                  <Icone
                    nom="actualiser"
                    :taille="16"
                  />
                  <span>
                    Indexation en cours…
                    {{ docIndexState.progression?.fait ?? 0 }}/{{ docIndexState.progression?.total ?? 0 }} document(s)
                    <template v-if="docIndexState.progression?.fichier">
                      — {{ docIndexState.progression.fichier }}
                    </template>
                  </span>
                </p>
                <div class="row">
                  <button
                    type="button"
                    class="btn btn-secondaire"
                    :disabled="!docIndexState?.modele_disponible || docIndexState?.en_cours"
                    @click="construireIndex"
                  >
                    <Icone
                      nom="actualiser"
                      :taille="16"
                    />
                    Construire / mettre à jour l'index
                  </button>
                  <button
                    v-if="docIndexState?.en_cours"
                    type="button"
                    class="btn btn-fantome"
                    @click="annulerIndex"
                  >
                    <Icone
                      nom="fermer"
                      :taille="16"
                    />
                    Annuler
                  </button>
                </div>
              </div>

              <div
                v-if="auth.estResponsable"
                class="groupe"
              >
                <h3>
                  <Icone
                    nom="document"
                    :taille="18"
                  />
                  Documents Word créés par Oliv'IA
                </h3>
                <p
                  v-if="modeleEtat"
                  class="etat"
                  :class="modeleEtat.disponible ? 'ok' : 'avert'"
                  aria-live="polite"
                >
                  <Icone
                    :nom="modeleEtat.disponible ? 'coche' : 'alerte'"
                    :taille="16"
                  />
                  <span>
                    {{ modeleEtat.message }}
                    <template v-if="modeleEtat.chemin">
                      <br>
                      <code>{{ modeleEtat.chemin }}</code>
                    </template>
                  </span>
                </p>
                <div class="field">
                  <label for="f-modele-source">Reprendre l'en-tête d'un document existant</label>
                  <input
                    id="f-modele-source"
                    v-model="modeleSource"
                    placeholder="r0/documents/Circulaire de rentrée.docx"
                  >
                  <p class="hint">
                    Indiquez un document Word de l'établissement (chemin affiché sous son
                    nom dans Documents). Oliv'IA en retire tout le texte et n'en garde
                    que l'identité : logo, en-tête, pied de page, polices et marges. C'est
                    ce modèle qui habille ensuite les circulaires, courriers, convocations
                    et comptes rendus. À refaire le jour où la charte du lycée change.
                  </p>
                  <div class="row">
                    <button
                      type="button"
                      class="btn btn-secondaire"
                      :disabled="!modeleSource.trim() || modeleEnCours"
                      @click="fabriquerModele"
                    >
                      <Icone
                        :nom="modeleEnCours ? 'actualiser' : 'document'"
                        :taille="16"
                      />
                      {{ modeleEnCours ? 'Fabrication…' : 'Fabriquer le modèle' }}
                    </button>
                  </div>
                  <p
                    v-if="modeleMsg"
                    class="hint"
                    aria-live="polite"
                  >
                    {{ modeleMsg }}
                  </p>
                </div>
              </div>
            </section>

            <!-- FORMULES DE POLITESSE -->
            <section
              v-if="tab === 'formules'"
              aria-label="Formules de politesse"
            >
              <div class="groupe">
                <h3>
                  <Icone
                    nom="plume"
                    :taille="18"
                  />
                  Formules utilisées dans les documents
                </h3>
                <p class="hint">
                  Oliv'IA les insère dans les courriers, convocations et comptes rendus
                  qu'elle produit. Laissez un champ vide pour garder la formule d'usage
                  indiquée en exemple. Appliqué après <b>Enregistrer</b>.
                </p>
                <div class="field">
                  <label for="f-docgen-appel">Appel</label>
                  <input
                    id="f-docgen-appel"
                    v-model="settings.data.docgen_appel"
                    placeholder="Madame, Monsieur,"
                  >
                </div>
                <div class="field">
                  <label for="f-docgen-politesse">Formule de politesse</label>
                  <textarea
                    id="f-docgen-politesse"
                    v-model="settings.data.docgen_formule_politesse"
                    rows="2"
                    placeholder="Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations distinguées."
                  />
                </div>
                <div class="field">
                  <label for="f-docgen-lieu">Ville (pour la formule « Fait à … »)</label>
                  <input
                    id="f-docgen-lieu"
                    v-model="settings.data.docgen_lieu"
                    placeholder="Marseille"
                  >
                </div>
                <div class="field">
                  <label for="f-docgen-signature">Signature par défaut</label>
                  <input
                    id="f-docgen-signature"
                    v-model="settings.data.docgen_signature"
                    placeholder="La direction"
                  >
                  <p class="hint">
                    Reprise si aucune signature n'est saisie au moment de créer le document.
                  </p>
                </div>
              </div>
            </section>

            <!-- RECHERCHE WEB -->
            <section
              v-if="tab === 'search'"
              aria-label="Recherche web"
            >
              <div class="groupe">
                <h3>
                  <Icone
                    nom="globe"
                    :taille="18"
                  />
                  Moteur de recherche
                </h3>
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
                  <label for="f-brave-key">Clé d'accès Brave Search</label>
                  <input
                    id="f-brave-key"
                    v-model="settings.data.search_brave_api_key"
                    type="password"
                    autocomplete="off"
                    aria-describedby="f-brave-note"
                  >
                  <p
                    v-if="noteBrave"
                    id="f-brave-note"
                    :class="noteBrave === 'a_ressaisir' ? 'warn' : 'hint'"
                    :role="noteBrave === 'a_ressaisir' ? 'alert' : null"
                  >
                    <Icone
                      v-if="noteBrave === 'a_ressaisir'"
                      nom="alerte"
                      :taille="16"
                    />
                    <span>{{ noteBrave === 'a_ressaisir' ? AVERTISSEMENT_A_RESSAISIR : NOTE_EN_CLAIR }}</span>
                  </p>
                </div>

                <div class="field">
                  <label class="checkbox">
                    <input
                      v-model="settings.data.search_official_only"
                      type="checkbox"
                    >
                    Privilégier les sites officiels (education.gouv.fr, Légifrance,
                    Service-Public…)
                  </label>
                  <p class="hint">
                    Limite la recherche aux sites de l'administration française
                    (education.gouv.fr, eduscol, Légifrance, Service-Public.fr, gouv.fr,
                    Onisep). Si aucun de ces sites n'a de réponse, Oliv'IA l'indique
                    clairement au lieu de proposer un résultat non officiel. Prend effet
                    après <b>Enregistrer</b> — le bouton « Tester » ci-dessous applique
                    ce réglage une fois enregistré.
                  </p>
                </div>
              </div>

              <div class="groupe">
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
                      type="button"
                      class="btn btn-secondaire"
                      :disabled="!testQuery.trim() || searching"
                      @click="testSearch"
                    >
                      <Icone
                        nom="loupe"
                        :taille="16"
                      />
                      {{ searching ? '…' : 'Tester' }}
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
              </div>
            </section>

            <!-- CONNECTEURS -->
            <section
              v-if="tab === 'connectors'"
              aria-label="Connexions externes"
            >
              <p class="hint intro">
                Ces connexions sont en général préparées <b>une seule fois</b> par votre
                service informatique. Une fois activées, elles apparaissent dans la barre d'outils.
              </p>

              <div class="groupe">
                <h3>
                  <Icone
                    nom="mail"
                    :taille="18"
                  />
                  Boîte mail professionnelle (IMAP)
                </h3>
                <label class="checkbox">
                  <input
                    v-model="settings.data.connectors.imap.enabled"
                    type="checkbox"
                  >
                  Activer la connexion IMAP
                </label>
                <div class="field">
                  <label for="f-imap-label">Libellé affiché</label>
                  <input
                    id="f-imap-label"
                    v-model="settings.data.connectors.imap.label"
                    placeholder="Boîte pro"
                  >
                </div>
                <div class="field">
                  <label for="f-imap-host">Serveur IMAP</label>
                  <input
                    id="f-imap-host"
                    v-model="settings.data.connectors.imap.host"
                    placeholder="imap.gmail.com"
                  >
                </div>
                <div class="field">
                  <label for="f-imap-user">Utilisateur (email)</label>
                  <input
                    id="f-imap-user"
                    v-model="settings.data.connectors.imap.user"
                    placeholder="vous@pro.fr"
                  >
                </div>
                <div class="field">
                  <label for="f-imap-password">Mot de passe d'application</label>
                  <input
                    id="f-imap-password"
                    v-model="settings.data.connectors.imap.password"
                    type="password"
                    placeholder="16 caractères Gmail / token Outlook"
                    autocomplete="off"
                    aria-describedby="f-imap-note"
                  >
                  <p
                    v-if="noteImap"
                    id="f-imap-note"
                    :class="noteImap === 'a_ressaisir' ? 'warn' : 'hint'"
                    :role="noteImap === 'a_ressaisir' ? 'alert' : null"
                  >
                    <Icone
                      v-if="noteImap === 'a_ressaisir'"
                      nom="alerte"
                      :taille="16"
                    />
                    <span>{{ noteImap === 'a_ressaisir' ? AVERTISSEMENT_A_RESSAISIR : NOTE_EN_CLAIR }}</span>
                  </p>
                </div>
                <div class="field">
                  <label for="f-imap-folder">Dossier</label>
                  <input
                    id="f-imap-folder"
                    v-model="settings.data.connectors.imap.folder"
                    placeholder="INBOX"
                  >
                </div>
                <p class="warn">
                  <Icone
                    nom="alerte"
                    :taille="16"
                  />
                  <span>
                    <strong>Activez uniquement sur un poste de confiance.</strong>
                    Le mot de passe donne accès à la boîte mail.
                  </span>
                </p>
              </div>

              <div class="groupe">
                <h3>
                  <Icone
                    nom="calendrier"
                    :taille="18"
                  />
                  Calendrier (.ics local)
                </h3>
                <label class="checkbox">
                  <input
                    v-model="settings.data.connectors.calendar_ics.enabled"
                    type="checkbox"
                  >
                  Activer calendrier local
                </label>
                <div class="field">
                  <label for="f-ics-path">Chemin du fichier .ics</label>
                  <input
                    id="f-ics-path"
                    v-model="settings.data.connectors.calendar_ics.path"
                    placeholder="C:\\Users\\vous\\cal.ics"
                  >
                </div>
              </div>

              <p class="hint intro">
                Google Drive et OneDrive ne nécessitent aucune connexion : ils se
                synchronisent déjà dans un dossier de l'ordinateur. Désignez-le simplement
                via <strong>Documents → Parcourir</strong>.
              </p>

              <div class="groupe">
                <h3>
                  <Icone
                    nom="livre"
                    :taille="18"
                  />
                  Obsidian
                </h3>
                <label class="checkbox">
                  <input
                    v-model="settings.data.connectors.obsidian.enabled"
                    type="checkbox"
                  >
                  Activer Obsidian
                </label>
                <div class="field">
                  <label for="f-obsidian-path">Chemin du coffre</label>
                  <input
                    id="f-obsidian-path"
                    v-model="settings.data.connectors.obsidian.vault_path"
                  >
                </div>
              </div>

              <div class="groupe">
                <h3>
                  <Icone
                    nom="document"
                    :taille="18"
                  />
                  Notion
                </h3>
                <label class="checkbox">
                  <input
                    v-model="settings.data.connectors.notion.enabled"
                    type="checkbox"
                  >
                  Activer Notion
                </label>
                <div class="field">
                  <label for="f-notion-token">Jeton d'intégration</label>
                  <input
                    id="f-notion-token"
                    v-model="settings.data.connectors.notion.api_token"
                    type="password"
                    placeholder="secret_..."
                    autocomplete="off"
                    aria-describedby="f-notion-note"
                  >
                  <p
                    v-if="noteNotion"
                    id="f-notion-note"
                    :class="noteNotion === 'a_ressaisir' ? 'warn' : 'hint'"
                    :role="noteNotion === 'a_ressaisir' ? 'alert' : null"
                  >
                    <Icone
                      v-if="noteNotion === 'a_ressaisir'"
                      nom="alerte"
                      :taille="16"
                    />
                    <span>{{ noteNotion === 'a_ressaisir' ? AVERTISSEMENT_A_RESSAISIR : NOTE_EN_CLAIR }}</span>
                  </p>
                </div>
              </div>
            </section>

            <!-- CONFIDENTIALITÉ / RGPD -->
            <section
              v-if="tab === 'privacy'"
              aria-label="Confidentialité et données personnelles"
            >
              <div class="groupe">
                <h3>
                  <Icone
                    nom="cadenas"
                    :taille="18"
                  />
                  Vos données
                </h3>
                <p class="hint">
                  Oliv'IA fonctionne <b>entièrement sur cette machine</b>. Vos conversations,
                  fichiers et identifiants ne sont transmis à aucun serveur externe.
                  Les paramètres et les conversations sont stockés sur ce poste, dans le
                  dossier des données d'Oliv'IA, séparément pour chaque organisation.
                </p>
                <p class="hint">
                  Seules exceptions, désactivées tant que vous ne les activez pas :
                  la <b>recherche web</b> envoie votre question au moteur de recherche choisi ;
                  les <b>mises à jour automatiques</b> de l'application de bureau interrogent
                  GitHub (adresse du poste et version installée, rien d'autre).
                </p>
              </div>

              <div class="groupe">
                <h3>Droit d'accès et de portabilité</h3>
                <p class="hint">
                  {{ exportTexte }}
                  Par sécurité, les mots de passe et clés d'accès enregistrés (boîte mail,
                  moteur de recherche…) y sont masqués : le fichier peut circuler sans les
                  divulguer.
                </p>
                <button
                  type="button"
                  class="btn btn-secondaire"
                  @click="exportData"
                >
                  <Icone
                    nom="telecharger"
                    :taille="16"
                  />
                  Exporter mes données
                </button>
              </div>

              <div
                v-if="auth.estResponsable"
                class="groupe groupe-danger"
              >
                <h3>Droit à l'effacement</h3>
                <p class="warn">
                  <Icone
                    nom="alerte"
                    :taille="16"
                  />
                  <span>
                    Réinitialise <strong>tous les paramètres</strong> et supprime les fichiers importés
                    via l'application (dossier <code>_uploads</code>). Vos autres documents ne sont pas touchés.
                    Action irréversible.
                  </span>
                </p>
                <button
                  type="button"
                  class="btn btn-danger"
                  @click="deleteData"
                >
                  <Icone
                    nom="corbeille"
                    :taille="16"
                  />
                  Supprimer mes données locales
                </button>
              </div>
              <p
                v-if="privacyMsg"
                class="hint"
                aria-live="polite"
              >
                {{ privacyMsg }}
              </p>
            </section>

            <!-- MON COMPTE (tout compte) -->
            <section
              v-if="tab === 'compte'"
              aria-label="Mon compte"
            >
              <MonCompte />
            </section>

            <!-- COMPTES DE L'ORGANISATION (responsable) : la liste est rechargée à
                 chaque ouverture de l'onglet, et ne survit pas à un changement de compte. -->
            <section v-if="tab === 'comptes' && auth.estResponsable">
              <ComptesOrganisation />
            </section>
          </div>
        </div>

        <footer>
          <button
            class="btn btn-fantome"
            type="button"
            @click="toggleAdvanced"
          >
            <Icone
              v-if="!simple"
              nom="chevron-gauche"
              :taille="16"
            />
            {{ simple ? 'Réglages avancés' : 'Revenir au mode simple' }}
          </button>
          <div class="footer-actions">
            <button
              class="btn btn-secondaire"
              type="button"
              @click="settings.hide()"
            >
              Annuler
            </button>
            <button
              class="btn btn-primaire"
              type="button"
              :disabled="settings.saving"
              @click="save"
            >
              <Icone
                nom="coche"
                :taille="16"
              />
              Enregistrer
            </button>
          </div>
        </footer>
      </div>
    </div>
  </Transition>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { useSettingsStore } from '../stores/settings.js'
import { useAuthStore } from '../stores/auth.js'
import MonCompte from './MonCompte.vue'
import ComptesOrganisation from './ComptesOrganisation.vue'
import Icone from './Icone.vue'
import {
  onglets, ongletDisponible, reglagesAEnvoyer, texteExport, MESSAGE_RESERVE,
} from '../roles.js'
import {
  noteSecret, NOMS_SECRETS, NOTE_EN_CLAIR, AVERTISSEMENT_A_RESSAISIR,
} from '../secrets.js'

const settings = useSettingsStore()
const auth = useAuthStore()
const tab = ref('reasoning')
const simple = computed(() => settings.data.simple_mode !== false)
// Un membre ne voit ni les dossiers, ni les connexions, ni la recherche web, ni les
// formules : le serveur les lui refuserait (403). Voir roles.js.
const tabs = computed(() => onglets(auth.role, simple.value))
const exportTexte = computed(() => texteExport(auth.role))
const noteImap = computed(() => noteSecret(settings.etatSecrets, NOMS_SECRETS.imap))
const noteNotion = computed(() => noteSecret(settings.etatSecrets, NOMS_SECRETS.notion))
const noteBrave = computed(() => noteSecret(settings.etatSecrets, NOMS_SECRETS.brave))

// Icône de chaque onglet (décor) ; un onglet inconnu retombe sur l'engrenage.
const ICONES_ONGLETS = {
  reasoning: 'etincelles',
  documents: 'dossier',
  formules: 'plume',
  search: 'globe',
  connectors: 'mail',
  privacy: 'cadenas',
  compte: 'utilisateur',
  comptes: 'utilisateurs',
}
function iconeOnglet(id) { return ICONES_ONGLETS[id] || 'engrenage' }

// Apparence : trois cartes radio liées à settings.data.theme (aperçu immédiat).
const THEMES = [
  {
    id: 'systeme',
    nom: 'Suivre Windows',
    icone: 'ecran',
    aide: 'S\'adapte au réglage clair ou sombre de l\'ordinateur',
  },
  { id: 'sombre', nom: 'Sombre', icone: 'lune', aide: 'Fond sombre, reposant le soir' },
  { id: 'clair', nom: 'Clair', icone: 'soleil', aide: 'Fond clair, lumineux en journée' },
]

// L'onglet affiché doit toujours être proposé (changement de mode ou de compte).
watch(tabs, () => {
  if (!ongletDisponible(tab.value, auth.role, simple.value)) tab.value = 'reasoning'
})

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
  if (!ongletDisponible(tab.value, auth.role, goSimple)) tab.value = 'reasoning'
  await settings.save({ simple_mode: goSimple })
}

const testQuery = ref('')
const searchTest = ref(null)
const searching = ref(false)
const privacyMsg = ref('')
const modalEl = ref(null)
const closeBtn = ref(null)

// État du moteur de reconnaissance de caractères (onglet Documents). Le back-end
// le calcule en inspectant le disque : présence du binaire, langues installées.
// Rechargé à chaque ouverture ET après enregistrement, car le chemin du moteur
// est lui-même un réglage : sans cela, l'utilisatrice corrigerait le chemin sans
// jamais voir si sa correction a pris.
const ocrState = ref(null)

async function loadOcrState() {
  try {
    const r = await fetch('/api/ocr/status')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    ocrState.value = await r.json()
  } catch (e) {
    // Un back-end plus ancien n'expose pas cette route : on l'annonce sans
    // casser l'affichage du reste des réglages.
    ocrState.value = {
      disponible: false,
      chemin: '',
      message: `État du moteur de reconnaissance indisponible (${e.message}).`,
    }
  }
}

// État du modèle Word de l'établissement (onglet Documents). Même motif que
// l'OCR : c'est le back-end qui inspecte le disque, et l'état est rechargé après
// chaque fabrication — sinon l'utilisatrice ne verrait pas si elle a réussi.
const modeleEtat = ref(null)
const modeleSource = ref('')
const modeleEnCours = ref(false)
const modeleMsg = ref('')

async function loadModeleState() {
  try {
    const r = await fetch('/api/documents/status')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    modeleEtat.value = await r.json()
  } catch (e) {
    modeleEtat.value = {
      disponible: false,
      chemin: '',
      message: `État du modèle de documents indisponible (${e.message}).`,
    }
  }
}

async function fabriquerModele() {
  modeleEnCours.value = true
  modeleMsg.value = ''
  try {
    const r = await fetch('/api/documents/modele', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: modeleSource.value.trim() }),
    })
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    modeleMsg.value = 'Modèle fabriqué : le texte du document d\'origine a été retiré, '
      + 'seule son identité visuelle est conservée.'
    await loadModeleState()
  } catch (e) {
    modeleMsg.value = `Fabrication impossible : ${e.message}`
  } finally {
    modeleEnCours.value = false
  }
}

// État de l'index vectoriel de recherche par le sens (onglet Documents). Même
// motif que l'OCR et le modèle Word : c'est le back-end qui connaît l'état réel
// (index construit ou non, modèle Ollama disponible), rechargé à chaque ouverture.
const docIndexState = ref(null)
let docIndexPoll = null

async function loadDocIndexState() {
  try {
    const r = await fetch('/api/docindex/status')
    if (!r.ok) throw new Error(`HTTP ${r.status}`)
    docIndexState.value = await r.json()
  } catch {
    // Back-end plus ancien ou route indisponible : la section reste simplement
    // masquée, sans casser l'affichage du reste des réglages.
    docIndexState.value = null
  }
}

function formatDate(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' })
}

// Suit la progression pendant une construction d'index, et s'arrête d'elle-même
// dès que le back-end signale que la construction est terminée.
function demarrerSuiviIndex() {
  if (docIndexPoll) return
  docIndexPoll = setInterval(async () => {
    await loadDocIndexState()
    if (!docIndexState.value?.en_cours) {
      clearInterval(docIndexPoll)
      docIndexPoll = null
    }
  }, 1500)
}

async function construireIndex() {
  try {
    const r = await fetch('/api/docindex/build', { method: 'POST' })
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    docIndexState.value = data
    demarrerSuiviIndex()
  } catch (e) {
    alert('Construction de l\'index impossible : ' + e.message)
  }
}

async function annulerIndex() {
  try {
    const r = await fetch('/api/docindex/cancel', { method: 'POST' })
    const data = await r.json().catch(() => null)
    if (!r.ok) throw new Error(data?.detail || `HTTP ${r.status}`)
    docIndexState.value = data
  } catch (e) {
    alert('Annulation impossible : ' + e.message)
  }
}

onUnmounted(() => {
  if (docIndexPoll) clearInterval(docIndexPoll)
})

// Accessibilité : au focus à l'ouverture de la modale
watch(() => settings.open, async (o) => {
  if (o) {
    loadOcrState()
    loadModeleState()
    await loadDocIndexState()
    // Une construction laissée en cours (ex. paramètres refermés puis rouverts)
    // doit reprendre son suivi automatiquement.
    if (docIndexState.value?.en_cours) demarrerSuiviIndex()
    await nextTick()
    closeBtn.value?.focus()
  }
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
    if (!r.ok) {
      const corps = await r.json().catch(() => null)
      throw new Error(corps?.detail || `HTTP ${r.status}`)
    }
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
  // Un membre n'envoie que ses réglages de confort (voir reglagesAEnvoyer).
  const result = await settings.save(reglagesAEnvoyer(settings.data, auth.role))
  if (!result?.ok) {
    alert('Enregistrement impossible : ' + (result?.error || 'erreur inconnue'))
    return
  }
  loadOcrState()   // le chemin du moteur a pu changer
  settings.hide()
}

// Exposé pour permettre à App.vue d'ouvrir directement l'onglet RGPD
defineExpose({ goToPrivacy: () => { tab.value = 'privacy' } })
</script>

<style scoped>
.overlay {
  position: fixed; inset: 0;
  background: color-mix(in srgb, var(--fond) 70%, transparent);
  display: flex; align-items: center; justify-content: center; z-index: 1000;
}
.modal {
  width: 960px; max-width: 94vw;
  height: min(720px, 88vh);
  border-radius: var(--r-4);
  box-shadow: var(--ombre-2);
  display: flex; flex-direction: column; overflow: hidden;
}
header {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--e-3) var(--e-5); border-bottom: 1px solid var(--bordure);
}
header h2 {
  display: flex; align-items: center; gap: var(--e-2);
  margin: 0; font-size: var(--t-l);
}
header h2 .icone { color: var(--accent-texte); }

/* Navigation verticale à gauche, contenu défilant à droite. */
.centre { flex: 1; min-height: 0; display: grid; grid-template-columns: 210px 1fr; }
.tabs {
  display: flex; flex-direction: column; gap: 2px;
  padding: var(--e-3);
  background: color-mix(in srgb, var(--surface-2) 70%, transparent);
  border-right: 1px solid var(--bordure);
  overflow-y: auto;
}
.onglet {
  display: flex; align-items: center; gap: var(--e-3);
  width: 100%; padding: 9px 12px;
  background: transparent; color: var(--texte);
  font-size: var(--t-m); text-align: left;
  border-radius: var(--r-2);
}
.onglet:hover { background: var(--surface-3); }
.onglet.active, .onglet.active:hover {
  background: var(--accent-doux); color: var(--accent-texte); font-weight: 600;
}
.onglet .icone { flex-shrink: 0; }
.body { padding: var(--e-5); overflow-y: auto; min-width: 0; }

/* Groupes de réglages : une carte légère par thème. */
.groupe {
  background: var(--surface);
  border: 1px solid var(--bordure);
  border-radius: var(--r-3);
  padding: var(--e-4) var(--e-5);
  margin: 0 0 var(--e-4);
  min-width: 0;
}
.groupe-danger { border-color: var(--danger); }
.groupe h3, .groupe legend {
  display: flex; align-items: center; gap: var(--e-2);
  font-size: var(--t-m); font-weight: 600; margin: 0 0 var(--e-3);
}
.groupe h3 .icone { color: var(--accent-texte); }
/* Un fieldset garde son propre cadre de légende : on le remet à plat. */
fieldset.groupe { margin-inline: 0; }
fieldset.groupe legend { padding: 0; float: left; width: 100%; }
fieldset.groupe legend + * { clear: both; }

.field { margin-bottom: var(--e-4); }
.field:last-child { margin-bottom: 0; }
.field > label:not(.checkbox) {
  display: flex; align-items: center; gap: var(--e-2);
  font-size: var(--t-s); font-weight: 500; color: var(--texte); margin-bottom: 4px;
}
.field textarea, .field input:not([type="checkbox"]), .field select { width: 100%; }
.curseur { padding: 0; border: none; background: transparent; accent-color: var(--accent); }
.row { display: flex; gap: var(--e-2); align-items: stretch; flex-wrap: wrap; }
.row input { flex: 1; min-width: 160px; }
.row button { white-space: nowrap; }
.checkbox {
  display: flex; gap: var(--e-2); align-items: center; margin: var(--e-2) 0;
  font-size: var(--t-s); font-weight: 500;
}
.checkbox input[type="checkbox"] { width: auto; margin: 0; accent-color: var(--accent); }

.hint { font-size: var(--t-xs); color: var(--discret); line-height: 1.5; margin: 6px 0 0; }
.hint.intro { margin: 0 0 var(--e-4); }
.hint code, .warn code, .etat code {
  background: var(--surface-3); padding: 1px 5px; border-radius: var(--r-1);
  font-family: monospace;
}
.warn {
  display: flex; gap: var(--e-2); align-items: flex-start;
  font-size: var(--t-s); line-height: 1.5; color: var(--texte);
  padding: var(--e-3); margin: var(--e-2) 0; border-radius: var(--r-2);
  background: color-mix(in srgb, var(--avert) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--avert) 45%, transparent);
}
.warn .icone { color: var(--avert); flex-shrink: 0; margin-top: 2px; }
.groupe-danger .warn {
  background: color-mix(in srgb, var(--danger) 10%, transparent);
  border-color: color-mix(in srgb, var(--danger) 45%, transparent);
}
.groupe-danger .warn .icone { color: var(--danger); }
/* État d'un moteur ou d'un index : coche si tout va bien, alerte sinon. */
.etat {
  display: flex; gap: var(--e-2); align-items: flex-start;
  font-size: var(--t-s); line-height: 1.5; color: var(--texte);
  margin: var(--e-3) 0;
}
.etat .icone { flex-shrink: 0; margin-top: 2px; color: var(--accent-texte); }
.etat.ok .icone { color: var(--ok); }
.etat.avert .icone { color: var(--avert); }


/* Apparence : cartes radio, le bouton radio natif reste dans le DOM (sr-only). */
.themes { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--e-3); }
.theme {
  position: relative;
  display: flex; align-items: flex-start; gap: var(--e-3);
  padding: var(--e-3);
  border-radius: var(--r-2);
  border: 1px solid var(--bordure);
  background: var(--surface);
  cursor: pointer;
  transition: background-color var(--transition), border-color var(--transition);
}
.theme:hover { background: var(--surface-2); }
.theme.actif { background: var(--accent-doux); border-color: var(--accent); }
.theme:has(input:focus-visible) { outline: 2px solid var(--accent); outline-offset: 2px; }
.theme-icone {
  display: inline-flex; align-items: center; justify-content: center;
  width: 36px; height: 36px; flex-shrink: 0;
  border-radius: var(--r-1); background: var(--surface-2); color: var(--discret);
}
.theme.actif .theme-icone { background: var(--surface); color: var(--accent-texte); }
.theme-texte { display: flex; flex-direction: column; gap: 2px; flex: 1; min-width: 0; }
.theme-nom { font-size: var(--t-m); font-weight: 600; }
.theme.actif .theme-nom { color: var(--accent-texte); }
.theme-aide { font-size: var(--t-xs); color: var(--discret); line-height: 1.4; }
.theme-coche { color: var(--accent-texte); flex-shrink: 0; }

.search-test { margin-top: var(--e-3); }
.result { padding: var(--e-2); border-bottom: 1px solid var(--bordure); }
.result a { color: var(--accent-texte); text-decoration: none; font-size: var(--t-s); }
.result .snippet { font-size: var(--t-xs); color: var(--discret); margin-top: 4px; line-height: 1.4; }

footer {
  padding: var(--e-3) var(--e-5); border-top: 1px solid var(--bordure);
  display: flex; justify-content: space-between; align-items: center; gap: var(--e-3);
  flex-wrap: wrap;
}
.footer-actions { display: flex; gap: var(--e-3); }

/* Écran étroit : la navigation passe en rangée horizontale défilante. */
@media (max-width: 760px) {
  .centre { grid-template-columns: 1fr; grid-template-rows: auto 1fr; }
  .tabs {
    flex-direction: row; overflow-x: auto; overflow-y: hidden;
    border-right: none; border-bottom: 1px solid var(--bordure);
  }
  .onglet { width: auto; flex-shrink: 0; white-space: nowrap; }
  .themes { grid-template-columns: 1fr; }
  .body { padding: var(--e-4); }
}
</style>
