# 🌷 Olivia — assistante locale pour le secrétariat de direction

**Olivia** est une assistante IA **100 % locale** conçue pour une **assistante de direction en lycée**.
Objectif : une utilisation **la plus simple possible**, sans donnée envoyée à l'extérieur.

Techniquement, c'est une application web (Vue.js + FastAPI + Ollama) qui :
- Discute avec Ollama (streaming token par token)
- Parcourt un dossier local **sandboxé** (path-traversal protégé)
- **Prévisualise** fichiers texte, code, CSV, Excel (.xlsx), Word (.docx), images et PDF
- **Importe (upload) et télécharge (download)** des fichiers dans le périmètre sandboxé
- Injecte le contenu d'un fichier dans le contexte du LLM (mini-RAG, tous formats prévisualisables)
- Effectue des recherches web à la demande (bouton 🌐 du chat) et cite ses sources
  (DuckDuckGo / SearXNG / Brave)
- Bascule le calcul **GPU ↔ CPU** et adapte les modèles recommandés
- Affiche une barre stylisée des **outils connectés** (boîte mail pro avec notification des non-lus, calendrier, outils métier)
- Respecte les mesures techniques **RGPD** (export / suppression des données, consentement) et **RGAA/WCAG AA** (ARIA, clavier, contrastes)
- Lanceur automatique (`.py` multi-OS + `.exe` Windows autonome via PyInstaller)

## 🧭 Mode simple (par défaut)

Olivia démarre en **mode simple** pour ne montrer à l'utilisatrice que l'essentiel :
la **conversation**, les **documents** (import / aperçu) et la **barre des outils connectés**
(dont les e-mails non lus), plus le bouton **🌐 Recherche web** du chat. Les réglages
techniques (puissance GPU/CPU, choix du modèle, *choix du moteur* de recherche web,
connexions, prompt système) sont **masqués**.

Pour les afficher : **⚙️ Paramètres → 🔧 Réglages avancés**. Un clic sur
**« ← Revenir au mode simple »** rétablit l'affichage épuré. Le choix est mémorisé.
Idéal : le service informatique passe une fois en mode avancé pour tout configurer,
puis laisse Olivia en mode simple pour l'assistante de direction.

## 🚀 Démarrage rapide

### Pré-requis
- Python 3.10 → 3.14
- Node.js 20+
- Ollama (https://ollama.com) — installé en portable dans `./ollama` (démarré
  automatiquement par `launch.py`) ou déjà lancé sur `http://localhost:11434`

### Lancement en une commande (dev)

```bash
python launch.py
```

Le script :
1. **Démarre Ollama automatiquement** s'il est installé en portable dans `./ollama`
   (avec les modèles du projet `./ollama/models`), sauf s'il tourne déjà
2. Crée le venv backend s'il n'existe pas et installe les dépendances
3. Démarre FastAPI (`backend.main:app`, port 8000) depuis la racine
4. Lance Vite en parallèle si `frontend/node_modules` existe (mode dev)
5. Attend que les serveurs répondent (health-check par port)
6. Ouvre le navigateur sur l'URL correcte

> `--no-ollama` pour ne pas démarrer le moteur ; `start-ollama.ps1` reste disponible
> pour lancer Ollama seul dans sa propre fenêtre.

Options :
```bash
python launch.py --no-dev        # backend seul, UI buildée servie sur /ui
python launch.py --no-browser    # sans ouverture auto du navigateur
python launch.py --port 9000     # changer le port backend
```

### Lancement manuel (alternative)

**Backend** — depuis la **racine du projet** (imports en package) :
```bash
python -m venv backend/.venv
backend/.venv/Scripts/activate        # Linux/macOS : source backend/.venv/bin/activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env  # éditer FS_ROOT
uvicorn backend.main:app --reload --port 8000
```
> ⚠️ Lancez bien `uvicorn backend.main:app` **depuis la racine**, pas `main:app` depuis `backend/`
> (le backend est un package qui utilise des imports relatifs).

**Frontend**
```bash
cd frontend
npm install
npm run dev        # dev → http://localhost:5173
# ou
npm run build      # prod → frontend/dist, servi par FastAPI sur /ui
```

## 🪟 Construire le `.exe` Windows (PyInstaller)

Le `.exe` est compilé **sur votre machine Windows**. Il embarque le backend ET l'UI, et
démarre FastAPI **en interne** (aucun venv/pip requis au lancement).

```powershell
# 1) Builder l'UI pour qu'elle soit embarquée dans le binaire
cd frontend
npm install
npm run build
cd ..

# 2) Compiler l'exécutable autonome (PyInstaller installé DANS le venv du projet)
backend\.venv\Scripts\python.exe -m pip install pyinstaller
backend\.venv\Scripts\pyinstaller.exe build.spec --clean --noconfirm

# → dist\ai-webapp\ai-webapp.exe
# Double-clic → FastAPI démarre + navigateur ouvert sur http://127.0.0.1:8000/ui/
```

> **Déploiement avec Ollama portable** : pour que l'.exe démarre aussi le moteur d'IA,
> copiez le dossier `ollama/` (binaire + `models/`) **à côté de `ai-webapp.exe`**
> (le lanceur cherche `./ollama` relatif à l'exécutable). Sinon, l'.exe réutilise
> un Ollama déjà lancé sur :11434.

Icône personnalisée : placez `ai-webapp.ico` à la racine et décommentez la ligne
`# icon='ai-webapp.ico'` dans `build.spec`.

## 🎮 CPU / GPU et modèles

Un sélecteur **GPU / CPU** est présent dans la barre du haut (et dans Paramètres) :
- **GPU** : Ollama utilise la carte automatiquement.
- **CPU** : le backend force `num_gpu=0` à chaque requête.

Le choix filtre les **modèles recommandés** dans le sélecteur de modèle et bascule
automatiquement vers un modèle adapté si le modèle courant ne l'est pas. Listes par défaut
(modifiables) :

| Périphérique | Modèles recommandés |
|---|---|
| GPU (ex. RTX 5060 8 Go) | `qwen3:8b`, `qwen2.5-coder:7b`, `llama3.3:8b`, `qwen2.5-vl:7b`, `phi4-mini:3.8b` |
| CPU / bureautique | `qwen3:4b` (~2,5 Go), `qwen3:1.7b` (~1,4 Go, très léger), `phi4-mini:3.8b`, `gemma2:2b` |

Les modèles recommandés non installés apparaissent grisés avec la commande `ollama pull`.

## 📎 Fichiers : import, téléchargement, prévisualisation

- **Importer** : bouton « ⬆ Importer un fichier » dans l'explorateur (déposé sous `_uploads/`
  ou dans le dossier courant). Types autorisés : texte/code, `.csv`, `.xlsx`, `.docx`, `.pdf`, images.
  Taille max 25 Mo, nom assaini, périmètre sandboxé.
- **Prévisualiser** : clic sur un fichier → aperçu simplifié selon le type
  (tableau pour CSV/Excel, texte formaté pour Word, `<img>` pour images, `<iframe>` pour PDF).
- **Télécharger** : bouton « ⬇ Télécharger » dans l'aperçu.
- **Injecter dans le chat** : texte/CSV/Excel/Word peuvent être injectés comme contexte RAG.

## 🔌 Outils connectés (barre stylisée)

Sous la barre de titre, une barre affiche chaque connecteur **activé** avec un point d'état
(vert = connecté, orange = à configurer/à brancher, gris = inactif) et une info textuelle
(non codée uniquement par la couleur → RGAA). La **boîte mail pro** affiche un badge 🔔 avec
le nombre d'e-mails **non lus** (rafraîchi toutes les 60 s).

| Service | Statut | Configuration |
|---|---|---|
| **IMAP (boîte pro)** | ✅ Fonctionnel + notifications non-lus | Serveur + email + mot de passe d'application |
| **Calendrier .ics** | ✅ Fonctionnel | Chemin d'un fichier .ics exporté |
| **OAuth Gmail / Outlook** | 🟡 Squelette | client_id / client_secret / tenant_id |
| **Obsidian / Notion** | 🟡 Squelette | Chemin du coffre / token |
| **École Directe** (outil métier) | 🟡 Squelette | Identifiant/mot de passe — ⚠️ pas d'API publique officielle |
| **Service-Public / gouv.fr** (outil métier) | 🟡 Squelette | ⚠️ FranceConnect exige une habilitation partenaire officielle |

> **Honnêteté technique** : École Directe et FranceConnect n'ont pas d'intégration « clé en
> main ». Ces connecteurs valident la configuration et exposent un statut clair, mais l'appel
> réel doit être branché par vos soins (voir `backend/connectors/business_tools.py`).

## 🔒 RGPD — vos données

Tout reste **local** (aucun envoi externe). Onglet **Paramètres → Confidentialité (RGPD)** :
- **Export** (`GET /api/privacy/export`) : télécharge toutes vos données/paramètres en JSON.
- **Suppression** (`POST /api/privacy/delete`) : réinitialise les paramètres et purge le dossier
  `_uploads` (vos autres documents ne sont pas touchés).
- **Consentement** : bandeau informatif au premier lancement.
- Les secrets ne sont **jamais renvoyés en clair** par l'API (`GET /api/settings` les masque).

## ♿ RGAA / WCAG AA

- Structure sémantique + repères ARIA (`header`, `main`, `dialog`, `aria-label`, `aria-live`).
- Lien d'évitement « Aller au contenu principal ».
- Navigation clavier complète, focus visible (`:focus-visible`), modale focusable + `Échap`.
- États non véhiculés uniquement par la couleur (libellés textuels sur les points d'état).
- Contrastes relevés, respect de `prefers-reduced-motion`.

> Ce sont les **mesures techniques** de conformité. La conformité formelle RGPD/RGAA reste
> un processus (déclaration, audit, mentions légales) à mener selon votre contexte.

## 🛡️ Sécurité

- Routes `/api/fs/*` **sandboxées** sous les dossiers accessibles configurés — un ou plusieurs,
  un par ligne, avec un libellé optionnel après une barre verticale
  (`chemin | libellé`, path-traversal → **HTTP 403**). Ces dossiers se changent dans
  *Paramètres → Réglages avancés → Préférences*, sans redémarrage ; la variable d'environnement
  `FS_ROOT` reste la valeur par défaut si aucun dossier n'est configuré.
- En-têtes de sécurité sur toutes les réponses : `Content-Security-Policy`, `X-Content-Type-Options`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`.
- **CORS restreint** au poste local (plus de wildcard).
- Écoute sur `127.0.0.1` par défaut.
- Upload : allowlist d'extensions, nom assaini, taille max, sandbox.
- **Jeton API optionnel** : définissez `API_TOKEN` dans l'environnement pour exiger l'en-tête
  `X-API-Token` sur `/api/*`.
- Extensions lisibles : `.txt .md .py .js .ts .vue .json .yaml .yml .csv .html .css .log .sh`.

## 🔍 Recherche web

### Dans la conversation (bouton 🌐)

Sous la zone de saisie, le bouton **« 🌐 Recherche web »** est un interrupteur. Activé
(il devient coloré), Olivia interroge le moteur **avant** de répondre, injecte les
5 premiers résultats dans la demande et **cite ses sources** par numéro (`[1]`, `[2]`…).
Les liens correspondants s'affichent sous sa réponse, dans un bloc dépliable
« 🌐 N sources web ». L'état reste actif jusqu'à ce qu'on le désactive.

Le bouton est visible **y compris en mode simple** : c'est un choix explicite de
l'utilisatrice, seule action qui fait sortir une donnée de la machine (la requête
part vers le moteur configuré). Si le moteur est injoignable ou ne renvoie rien,
Olivia répond quand même et l'annonce clairement au lieu d'échouer.

### API

`POST /api/search` accepte `{query, limit}` et renvoie jusqu'à 5 résultats. Testable en direct
depuis **Paramètres → Recherche web** (champ + bouton « 🔍 Tester »).

| Provider | Pré-requis | Fiabilité |
|---|---|---|
| **SearXNG** (recommandé) | Docker — voir ci-dessous | Élevée |
| **DuckDuckGo** | Aucun | Moyenne (scraping HTML, bloqué après quelques requêtes rapprochées) |
| **Brave Search** | `BRAVE_API_KEY` dans l'environnement | Élevée |

### Installer SearXNG (métamoteur auto-hébergé)

SearXNG interroge plusieurs moteurs à la fois (Google, DuckDuckGo, Wikipédia…) depuis
**votre machine** : aucun compte, aucune clé API, et aucun profilage publicitaire.

```powershell
docker run -d --name olivia-searxng --restart unless-stopped `
  -p 8888:8080 -v "D:\Olivia\searxng:/etc/searxng" `
  -e "SEARXNG_BASE_URL=http://localhost:8888/" searxng/searxng:latest
```

> ⚠️ **Indispensable** : la configuration par défaut de SearXNG **n'autorise pas le
> format JSON** dont Olivia a besoin (`/search?format=json` → HTTP 403). Après le
> premier démarrage, ajoutez dans `searxng/settings.yml` :
> ```yaml
> search:
>   formats: [html, json]
>   default_lang: "fr-FR"
> ```
> puis `docker restart olivia-searxng`. Le dossier `searxng/` est ignoré par Git
> (il contient une `secret_key` propre à la machine).

### À propos de Qwant

Qwant (moteur français) **n'est pas disponible** dans Olivia : son accès automatisé est
protégé par un captcha anti-robot (DataDome), en appel direct comme via le connecteur
officiel de SearXNG, qui le signale `qwant: CAPTCHA`. Seul un contrat d'API commercial
avec Qwant permettrait l'intégration. SearXNG en local reste l'option la plus proche :
auto-hébergée, sans traçage, avec des résultats en français.

## 🧠 Raisonnement et ton

**Paramètres → Raisonnement & ton** : Style (Concis / Équilibré / Détaillé / Créatif /
Analytique), Ton (Neutre / Amical / Formel / Pédagogue), Température (0–2), Prompt système libre.
Assemblé dynamiquement à chaque requête ; pas besoin de redémarrer Ollama.

## ⚠️ Notes VRAM (cible RTX 5060 8 Go)

`qwen3:8b` (~5,2 Go), `qwen2.5-coder:7b` (~5 Go), `phi4-mini:3.8b` (~2,5 Go),
`llama3.3:8b` (~5,5 Go), `qwen2.5-vl:7b` (~6 Go). Quantification Q4_K_M recommandée.

## 📁 Arborescence

```
ai-webapp/
├── README.md
├── launch.py              ← lanceur multi-OS (dev) + point d'entrée .exe (mode gelé)
├── build.spec             ← config PyInstaller (embarque backend + frontend/dist)
├── .gitignore
├── backend/
│   ├── main.py            ← FastAPI : chat + fs + upload/download/preview + settings + search + connectors + RGPD
│   ├── settings.py        ← persistance JSON + CPU/GPU + modèles par périphérique
│   ├── search.py          ← recherche web pluggable
│   ├── documents.py       ← prévisualisation txt/csv/xlsx/docx/img/pdf
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── imap_client.py      ← IMAP + comptage des non-lus
│   │   ├── oauth_providers.py  ← stubs OAuth Gmail/Outlook + lecteur .ics
│   │   └── business_tools.py   ← stubs École Directe + Service-Public/gouv.fr
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json, vite.config.js, index.html
    └── src/
        ├── main.js, App.vue, style.css
        ├── stores/ (chat.js, settings.js)
        └── components/
            ├── ModelPicker.vue      ← sélecteur device-aware
            ├── FileExplorer.vue     ← arbre + upload + recherche
            ├── FilePreview.vue      ← aperçu multi-format
            ├── ChatPanel.vue
            ├── ConnectedTools.vue   ← barre des outils connectés + notif mail
            ├── ConsentBanner.vue    ← bandeau RGPD
            └── SettingsMenu.vue     ← 4 onglets (Raisonnement / Recherche / Connexions / Confidentialité)
```
