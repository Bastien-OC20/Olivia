<p align="center">
  <img src="visuel/logo-transparent.png" alt="Logo d'Oliv'IA : tuile bleue avec un O traversé d'un rameau d'olivier" width="180">
</p>

#  Oliv'IA — assistante locale pour le secrétariat

**Oliv'IA** est une assistante IA **100 % locale**, pensée d'abord pour une **assistante de
direction en lycée**, et utilisable par toute petite structure (mairie, association, PME,
établissement). Objectif : une utilisation **la plus simple possible**, sans donnée envoyée à
l'extérieur — le modèle d'IA tourne sur le poste (Ollama), les documents restent sur le
disque.

> **Nom** : l'application s'affiche sous le nom **Oliv'IA**. Les noms techniques gardent
> « Olivia » : dossiers des données (`C:\ProgramData\Olivia`…), fichiers (`olivia.ini`,
> `Lancer-Olivia.bat`, `ai-webapp.exe`), variables `OLIVIA_*`, nom interne de l'application de
> bureau (`Olivia.app`, `Olivia Setup <version>.exe`) et dossier d'installation. Les renommer
> ferait perdre, à la mise à jour, les comptes et conversations déjà enregistrés, et casserait
> les mises à jour automatiques.

Elle s'utilise de quatre façons, avec le même code :

| Forme | Pour qui | Section |
|---|---|---|
| **Application de bureau** macOS / Windows (Electron) | poste de travail, usage quotidien | [🖥️ Application de bureau](#️-application-de-bureau-macos-windows) |
| **Installeur Windows** (Inno Setup, tout embarqué) | poste Windows sans connexion, installation classique | [💾 Installeur Windows](#-installeur-windows-inno-setup) |
| **Disque portable** (clé USB / disque externe) | rien à installer sur l'ordinateur hôte | [🔌 Version portable](#-version-portable-clé-usb--disque-externe) |
| **Depuis les sources** (navigateur) | développement | [🚀 Démarrage depuis les sources](#-démarrage-depuis-les-sources-développement) |

---

## Sommaire

1. [Fonctionnalités](#-fonctionnalités)
2. [Versions](#️-versions)
3. [Prérequis](#-prérequis)
4. [Démarrage depuis les sources](#-démarrage-depuis-les-sources-développement)
5. [Application de bureau (macOS, Windows)](#️-application-de-bureau-macos-windows)
6. [Exécutable Windows (PyInstaller)](#-exécutable-windows-pyinstaller)
7. [Installeur Windows (Inno Setup)](#-installeur-windows-inno-setup)
8. [Version portable](#-version-portable-clé-usb--disque-externe)
9. [Emplacement des données](#-emplacement-des-données)
10. [Comptes et organisations](#-comptes-et-organisations)
11. [Configuration](#️-configuration)
12. [Utilisation](#-utilisation)
13. [Recherche web](#-recherche-web)
14. [Outils connectés](#-outils-connectés)
15. [RGPD](#-rgpd--vos-données)
16. [Accessibilité (RGAA / WCAG AA)](#-accessibilité-rgaa--wcag-aa)
17. [Sécurité](#️-sécurité)
18. [API HTTP](#-api-http)
19. [Tests et intégration continue](#-tests-et-intégration-continue)
20. [Dépannage](#-dépannage)
21. [Limites connues et points non vérifiés](#️-limites-connues-et-points-non-vérifiés)
22. [Logo et icônes](#-logo-et-icônes)
23. [Arborescence](#-arborescence)
24. [Historique](#-historique)

---

## ✨ Fonctionnalités

**Conversation**
- Discussion avec le modèle local en **streaming** (mot à mot), bouton **⏸ Stop**.
- Réponses en **Markdown** (titres, listes, tableaux, code), liens cliquables, HTML assaini
  (DOMPurify).
- **Historique des conversations** : enregistrement automatique, rouvrir, renommer, supprimer.
- **Style** (Concis / Équilibré / Détaillé / Créatif / Analytique), **ton** (Neutre / Amical /
  Formel / Pédagogue), **température**, prompt système libre.
- Garde-fou contre les **sources inventées** : le modèle reçoit la consigne de ne jamais
  fabriquer de référence, de texte de loi ou de date.
- Erreurs du moteur (Ollama éteint, modèle absent, réponse coupée) **affichées dans la
  conversation**, en clair, au lieu d'une bulle vide.
- Panneau **« Oliv'IA n'est pas encore prête »** : si Ollama ne répond pas ou si un modèle
  manque, Oliv'IA explique quoi installer ou démarrer (commandes `ollama pull` à copier) et le
  panneau disparaît de lui-même une fois le problème réglé.

**Documents**
- Explorateur de fichiers limité aux **dossiers de travail** choisis, choix des dossiers **à
  la souris** (parcours des lecteurs).
- **Aperçu** : texte, code, CSV, Excel (`.xlsx`), Word (`.docx`), images, PDF.
- **Import** (25 Mo max, jamais d'écrasement d'un fichier existant) et **téléchargement**.
- **Ajout de documents à la conversation** (plusieurs à la fois), avec signalement de toute
  coupe (« ⚠️ tronqué »).
- **Recherche par mots-clés** à l'intérieur des fichiers (Word, Excel, PDF, CSV, texte),
  insensible à la casse et aux accents.
- **Recherche par le sens** (embeddings `bge-m3` + index FAISS local) : retrouve un document
  d'après l'idée, même sans mot commun.
- **OCR** (Tesseract, en français) des PDF scannés et des images.

**Production de documents Word**
- Bouton **📄 Créer un document Word** sous chaque réponse : **circulaire**, **courrier aux
  familles**, **convocation**, **compte rendu**.
- **Rédaction dirigée** : la réponse est d'abord réduite à son corps (sans objet, appel,
  formule de politesse ni signature, que le document pose lui-même).
- **Modèle de l'établissement** : logo, en-tête, pied de page, polices et marges repris d'un
  document Word existant.
- **Formules** d'usage (appel, politesse, ville, signature) réglables sans toucher au code.

**Comptes**
- **Connexion obligatoire**, comptes rattachés à une **organisation** ; conversations,
  réglages, index et modèle Word **cloisonnés** par organisation.
- Création des comptes réservée au **service informatique** (assistant `init`), pas
  d'inscription en libre-service.

**Outils**
- **Recherche web** à la demande (bouton 🌐), avec citation des sources : SearXNG, Brave
  Search ou DuckDuckGo, repli automatique entre moteurs, mode **« sources officielles »**.
- **Boîte mail professionnelle (IMAP)** avec nombre de non-lus, **calendrier `.ics`**.

**Matériel et distribution**
- Bascule **GPU ↔ CPU**, **détectée automatiquement** au premier lancement (VRAM NVIDIA).
- **Mode simple** par défaut (réglages techniques masqués).
- **Application de bureau** macOS et Windows : fenêtre native, icône dans la barre des menus /
  zone de notification, raccourci global, instance unique, mises à jour automatiques
  (Windows).
- Exécutable Windows autonome, installeur Inno Setup, disque portable.

**Conformité**
- Mesures techniques **RGPD** (export, effacement, consentement, secrets masqués) et
  **RGAA / WCAG AA** (ARIA, clavier, contrastes).

---

## 🏷️ Versions

Les numéros de version ne sont **pas alignés** entre les composants : chacun est déclaré à
un endroit différent et a évolué séparément.

| Composant | Version | Déclarée dans |
|---|---|---|
| Backend (API) | **3.0.0** | `backend/main.py` (`FastAPI(version=…)`), renvoyée par `GET /api/health` |
| Interface (Vue) | 2.0.0 | `frontend/package.json` |
| Application de bureau | 1.0.0 | `desktop/package.json` (nom des installeurs et des releases) |
| Installeur Inno Setup | 1.0.0 | `installer Olivia/olivia.iss` (`#define AppVersion`) |

Les **mises à jour automatiques** de l'application de bureau comparent la version de
`desktop/package.json` à celle de la dernière release GitHub : c'est ce numéro qu'il faut
augmenter avant de publier une nouvelle version (voir
[Intégration continue](#-tests-et-intégration-continue)).

**Principales dépendances** (minimums déclarés ; la version réellement installée est celle
du fichier de verrouillage ou du dernier `pip install`) :

| Côté | Dépendance | Version |
|---|---|---|
| Backend | FastAPI / Uvicorn / Pydantic | ≥ 0.115 / ≥ 0.30 / ≥ 2.9 |
| | httpx, python-dotenv, python-multipart | ≥ 0.27, ≥ 1.0, ≥ 0.0.12 |
| | python-docx, openpyxl, pypdf, pypdfium2 | ≥ 1.1, ≥ 3.1, ≥ 4.0, ≥ 4.30 |
| | faiss-cpu, numpy | ≥ 1.8, ≥ 1.26 et < 3 |
| | ics | ≥ 0.7.2 |
| Interface | Vue, Pinia, Vite | ^3.5.13, ^2.2.6, ^6.0.5 |
| | marked, DOMPurify | ^18.0.7, ^3.4.12 |
| Bureau | Electron, electron-builder, electron-updater | ^44.5.1, ^26.15.3, ^6.8.9 |

**Modèles d'IA** (Ollama) — un seul modèle par périphérique, choisi après comparaison sur
un même prompt de référence (le détail des modèles écartés et pourquoi est en commentaire
dans `backend/settings.py`, `DEVICE_MODELS`) :

| Usage | Modèle | Taille |
|---|---|---|
| Conversation, GPU (cible : RTX 5060 8 Go) | `mistral-nemo:12b-instruct-2407-q4_K_M` | ~7,5 Go |
| Conversation, CPU / bureautique | `gemma2:2b` | ~1,6 Go |
| Recherche par le sens (embeddings) | `bge-m3` | — |

---

## 📋 Prérequis

| Outil | Rôle | Remarque |
|---|---|---|
| **Ollama** (https://ollama.com) | moteur d'IA local | installé sur le poste (port 11434) ou en portable dans `./ollama` |
| Modèles Ollama | voir [Versions](#️-versions) | `ollama pull mistral-nemo:12b-instruct-2407-q4_K_M`, `ollama pull gemma2:2b`, `ollama pull bge-m3` |
| **Python** 3.10 ou plus | backend (sources, construction) | `requirements.txt` vise 3.10 → 3.14 ; **testé en 3.11** ; la CI est configurée en 3.12 |
| **Node.js** | interface, application de bureau | **testé avec Node 22** (aussi celui de la CI) |
| **Tesseract** (facultatif) | OCR des documents scannés | voir [OCR](#-documents-scannés--ocr) |
| **Docker** (facultatif) | SearXNG | voir [Recherche web](#-recherche-web) |

Pour un **utilisateur final**, rien de tout cela n'est nécessaire avec l'installeur Inno
Setup ou le disque portable (tout est embarqué). L'application de bureau demande seulement
Ollama et ses modèles sur le poste (voir plus bas).

---

## 🚀 Démarrage depuis les sources (développement)

### En une commande

```bash
python launch.py
```

Le lanceur :
1. démarre **Ollama** s'il est installé en portable dans `./ollama` (modèles dans
   `./ollama/models`), sauf s'il tourne déjà ;
2. crée le venv `backend/.venv` s'il n'existe pas et installe les dépendances ;
3. affiche l'emplacement des données et vérifie qu'il est modifiable ;
4. démarre FastAPI (`backend.main:app`, port 8000) depuis la racine ;
5. lance Vite en parallèle si `frontend/node_modules` existe (mode dev) ;
6. attend que les serveurs répondent, puis ouvre le navigateur.

| Option | Effet |
|---|---|
| `--no-dev` | backend seul, interface buildée servie sur `/ui` |
| `--no-browser` | ne pas ouvrir le navigateur |
| `--no-ollama` | ne pas démarrer le moteur |
| `--host 127.0.0.1` | adresse d'écoute (défaut `127.0.0.1`) |
| `--port 8000` | port du backend (défaut 8000) |
| `--max-wait 30` | attente maximale des serveurs, en secondes |
| `--parent-stdin` | s'arrêter quand l'entrée standard se ferme (utilisé par l'application de bureau) |
| `init`, `create-profile`, `create-user`, `list-profiles` | gestion des comptes (voir [Comptes](#-comptes-et-organisations)) |

`start-ollama.ps1` lance Ollama seul dans sa propre fenêtre (Windows).

### Manuellement

**Backend** — depuis la **racine du projet** (le backend est un package aux imports
relatifs : `uvicorn main:app` depuis `backend/` ne fonctionne pas) :

```bash
python -m venv backend/.venv
source backend/.venv/bin/activate          # Windows : backend\.venv\Scripts\activate
pip install -r backend/requirements.txt
cp backend/.env.example backend/.env       # puis adapter (voir Configuration)
uvicorn backend.main:app --reload --port 8000
```

**Interface**

```bash
cd frontend
npm install
npm run dev        # développement → http://localhost:5173
npm run build      # production → frontend/dist, servi par FastAPI sur /ui
npm run lint       # ESLint
```

Créer ensuite un premier compte : `python launch.py init`.

---

## 🖥️ Application de bureau (macOS, Windows)

L'application de bureau (`desktop/`, Electron) **enveloppe** l'application existante sans la
réécrire : elle lance le backend compilé (PyInstaller), attend qu'il réponde, puis affiche son
interface dans une vraie fenêtre. Tout reste local : la fenêtre ne charge que
`http://127.0.0.1`, et **aucune messagerie externe** (WhatsApp, Telegram…) n'est branchée —
choix assumé, cohérent avec le RGPD.

### Ce qu'elle apporte

- **fenêtre native**, icône Oliv'IA dans le Dock / la barre des tâches ;
- **icône dans la barre des menus** (macOS) ou la **zone de notification** (Windows) : fermer
  la fenêtre laisse Oliv'IA disponible en arrière-plan ; menu : *Ouvrir*, *Créer un compte…*,
  *Redémarrer*, *Quitter* ;
- **raccourci global** `Ctrl+Alt+O` (Windows) / `Cmd+Option+O` (macOS) pour afficher ou
  masquer Oliv'IA ;
- **une seule instance** : relancer Oliv'IA ramène la fenêtre existante ;
- **menus en français** ;
- **installeurs** `.dmg` / `.zip` (macOS) et `.exe` (Windows, NSIS, installation pour tous les
  utilisateurs du poste) ;
- **mises à jour automatiques** depuis les releases GitHub du dépôt (electron-updater) : actives
  sur Windows ; sur macOS seulement une fois l'application signée (macOS refuse sinon
  d'installer la mise à jour) — activer alors `olivia.majAutoMac` dans `desktop/package.json`.
  Une release ne sert de mise à jour qu'une fois **publiée** (le workflow crée un brouillon),
  et seulement si le dépôt est accessible aux postes ;
- **création de compte** : sur un poste sans compte, l'écran de connexion propose « Ouvrir
  l'assistant de création de compte » ; ensuite, menu *Créer un compte…*. L'assistant `init`
  s'ouvre dans une fenêtre de terminal.

### Installer sur un poste

1. Installer **Ollama** (https://ollama.com) et tirer les trois modèles :
   ```bash
   ollama pull mistral-nemo:12b-instruct-2407-q4_K_M
   ollama pull gemma2:2b
   ollama pull bge-m3
   ```
2. Installer Oliv'IA : `.dmg` (glisser dans *Applications*) ou `Olivia Setup <version>.exe`.
3. Au premier lancement, créer le premier compte avec le bouton de l'écran de connexion.
   Si Ollama ou un modèle manque, un panneau en haut de la fenêtre l'indique après la
   connexion, avec les commandes à taper.
4. Facultatif : Tesseract pour l'OCR (voir [OCR](#-documents-scannés--ocr)).

Les installeurs n'étant **pas signés** : Windows affiche SmartScreen (*Informations
complémentaires → Exécuter quand même*) ; macOS bloque l'ouverture (autoriser dans *Réglages
Système → Confidentialité et sécurité*, ou `xattr -dr com.apple.quarantine
/Applications/Olivia.app` par le service informatique).

**Données** : `C:\ProgramData\Olivia` sous Windows (commun au poste ; l'installeur NSIS y donne
le droit de modification au groupe Utilisateurs, repli sur le dossier de l'utilisateur si ce
dossier n'est pas modifiable), `~/Library/Application Support/Olivia` sous macOS. Transmis au
backend par `OLIVIA_DATA_DIR`. **Journal** : `olivia.log`, dans le dossier des journaux
d'Electron (`app.getPath('logs')`).

**Sécurité de la fenêtre** : `contextIsolation`, `sandbox`, aucun accès Node pour la page ;
la fenêtre ne navigue que vers l'interface d'Oliv'IA ; les liens s'ouvrent dans le navigateur
du système (http/https seulement) ; toutes les permissions (caméra, micro…) sont refusées.
Seule action exposée à la page (`desktop/preload.js`, objet `window.oliviaBureau`) : ouvrir
l'assistant de création de compte.

**Arrêt** : le backend est lancé avec `--parent-stdin` et s'arrête dès que l'application ferme
son entrée standard — y compris si elle plante (le système ferme alors le tube) : aucun
processus Oliv'IA ne survit à la fenêtre.

### Construire les installeurs

Chaque installeur se construit **sur son propre système** (pas de compilation croisée) :

```bash
cd frontend && npm ci && npm run build && cd ..
pip install -r backend/requirements.txt pyinstaller
pyinstaller build.spec --clean --noconfirm        # → dist/ai-webapp
cd desktop && npm ci
npm run dist:mac        # sur un Mac      → desktop/dist/Olivia-<version>.dmg (+ .zip)
npm run dist:win        # sur un Windows  → desktop/dist/Olivia Setup <version>.exe
npm run dist:dir        # dossier non empaqueté, pour tester
```

`desktop/scripts/preparer.mjs` copie `dist/ai-webapp` dans `desktop/build/ressources/backend`,
et y ajoute `ollama/`, `tesseract/` et `modeles/` s'ils sont présents à la racine du dépôt
**et** compilés pour le système de la machine. Sinon, l'application utilise l'Ollama installé
sur le poste.

Sans Mac ni Windows sous la main : le workflow GitHub Actions **« Application de bureau »**
construit les deux installeurs (voir [Intégration continue](#-tests-et-intégration-continue)).

**Développement** : `cd desktop && npm ci && npm start` (backend lancé depuis le dépôt avec
uvicorn ; interpréteur : `OLIVIA_PYTHON`, sinon `backend/.venv`, sinon `python3`/`python`).
**Tests** : `npm test`.

### Signer (non configuré pour l'instant)

Il faut un compte **Apple Developer** (signature + notarisation) et un **certificat de
signature de code Windows**, fournis à electron-builder par ses variables `CSC_LINK` /
`CSC_KEY_PASSWORD` (et `APPLE_ID`… pour la notarisation), puis retirer
`CSC_IDENTITY_AUTO_DISCOVERY=false` du workflow.

---

## 🪟 Exécutable Windows (PyInstaller)

Le `.exe` embarque le backend **et** l'interface, et démarre FastAPI **en interne** (aucun
venv ni pip au lancement). Il est compilé **sur une machine Windows** :

```powershell
cd frontend; npm install; npm run build; cd ..
backend\.venv\Scripts\python.exe -m pip install pyinstaller
backend\.venv\Scripts\pyinstaller.exe build.spec --clean --noconfirm
# → dist\ai-webapp\ai-webapp.exe
# Double-clic → FastAPI démarre + navigateur ouvert sur http://127.0.0.1:8000/ui/
```

- PyInstaller doit être lancé **depuis la racine** : `build.spec` désigne ses sources en
  relatif (`backend`, `frontend/dist`).
- Pour que l'`.exe` démarre aussi le moteur d'IA, copier `ollama/` (binaire + `models/`)
  **à côté de `ai-webapp.exe`** ; sinon il réutilise un Ollama déjà lancé sur le port 11434.
- Le binaire **n'embarque ni comptes, ni réglages, ni conversations** (`build.spec` les retire) :
  une installation neuve démarre vide et ne transporte aucun secret.
- Icône : `ai-webapp.ico` (racine du dépôt), générée depuis `visuel/logo.png` (voir
  [Logo et icônes](#-logo-et-icônes)).
- Le même exécutable sert à créer les comptes : `ai-webapp.exe init`.

---

## 💾 Installeur Windows (Inno Setup)

`installer Olivia/olivia.iss` produit un installeur classique (Program Files, menu Démarrer,
désinstalleur), **tout embarqué** : application, Ollama portable, les trois modèles,
Tesseract et le modèle Word commun. Installeur volumineux (~10-11 Go, d'après l'estimation
notée dans le script).

**Avant compilation** :
1. `cd frontend && npm run build`
2. `backend\.venv\Scripts\python -m PyInstaller build.spec --clean --noconfirm` (depuis la racine)
3. vérifier `ollama\`, `tesseract\` et `modeles\` à la racine du dépôt ;
4. compiler `installer Olivia\olivia.iss` avec Inno Setup → `Installer-Olivia-<version>.exe`.

L'installeur :
- place les **données** dans `C:\ProgramData\Olivia`, rendu modifiable par les utilisateurs du
  poste, et écrit `ai-webapp\olivia.ini` pour le désigner ;
- propose de **créer le premier compte** en fin d'installation (case cochée seulement s'il n'en
  existe aucun) et ajoute un raccourci **« Créer un compte Oliv'IA »** au menu Démarrer ;
- ne supprime **jamais** le dossier des données à la désinstallation.

---

## 🔌 Version portable (clé USB / disque externe)

Oliv'IA tourne entièrement depuis un disque amovible : application, moteur, modèles, comptes
et conversations restent dessus, rien n'est installé sur l'ordinateur hôte.

```powershell
.\deploy-portable.ps1                                  # interactif : choix du disque, puis du mode
.\deploy-portable.ps1 -Destination G:\Olivia -Update   # mise à jour silencieuse
.\deploy-portable.ps1 -Destination E:\Olivia -Replace  # réinstallation complète
.\deploy-portable.ps1 -SkipFrontend -SkipExe           # resynchroniser sans reconstruire
```

Le script enchaîne build Vite → build PyInstaller → copie des moteurs si nécessaire →
synchronisation, puis vérifie que l'installation est complète (interface bien embarquée,
lanceurs présents).

**Choix du disque** — sans `-Destination`, le script liste les lecteurs et propose celui qui
contient déjà Oliv'IA, sinon le disque non système le plus libre (un disque USB externe est
souvent vu comme « fixe » par Windows : le tri se fait sur l'espace libre).

| Mode | Effet |
|---|---|
| `-Update` (défaut) | Remplace l'application. **Conserve** moteurs, modèles, comptes, conversations et réglages. |
| `-Replace` | Efface tout et repart à neuf. **Destructif** : comptes, conversations et réglages perdus, modèles recopiés. |

En mode `-Update`, la synchronisation est un miroir, sauf ces éléments préservés :

| Préservé | Pourquoi |
|---|---|
| `ai-webapp\ollama\` | moteur + modèles (~9 Go) |
| `ai-webapp\tesseract\` | moteur OCR (~190 Mo) |
| `ai-webapp\_internal\backend\profiles\` | comptes, organisations, sessions, et pour chaque organisation réglages, conversations, index et modèle Word |
| `ai-webapp\_internal\backend\settings.json` | réglages de l'ancien mode mono-organisation (plus lus, conservés par prudence) |
| `ai-webapp\_internal\backend\.env` | configuration propre au disque (`OLLAMA_URL`, `FS_ROOT`…), jamais embarquée dans le build |
| `ai-webapp\_internal\backend\ocr_cache\` | cache OCR, reconstructible mais coûteux |

Garde-fous : lecteur absent refusé ; dossier non vide qui ne ressemble pas à une installation
Oliv'IA refusé (sauf `-Force`) ; sans console, valeurs par défaut et **jamais** de mode
destructif sans `-Replace` explicite.

```
G:\Olivia\
├── Lancer-Olivia.bat      ← double-clic (source : portable/)
├── Creer-un-compte.bat    ← assistant de création de compte (service informatique)
├── LISEZ-MOI.txt          ← notice non technique
└── ai-webapp\
    ├── ai-webapp.exe
    ├── _internal\         ← dont backend\profiles\ (données), créé à l'usage
    ├── ollama\            ← moteur + models\ (doit être DANS ai-webapp\)
    └── tesseract\
```

---

## 📍 Emplacement des données

Comptes, sessions, réglages, conversations, index de recherche par le sens et cache OCR vivent
dans un même dossier, choisi par `backend/emplacements.py`, par ordre de priorité :

1. variable d'environnement **`OLIVIA_DATA_DIR`** (utilisée par l'application de bureau) ;
2. fichier **`olivia.ini`** à côté de l'application (`[donnees]` `dossier=…`, écrit par
   l'installeur Inno Setup) ;
3. sinon le dossier **`backend/`** (développement, disque portable : les données voyagent avec
   la clé).

| Installation | Dossier des données |
|---|---|
| Sources / développement | `backend/` (`backend/profiles/`, ignoré par Git) |
| Disque portable | `ai-webapp\_internal\backend\` |
| Installeur Inno Setup | `C:\ProgramData\Olivia` |
| Application de bureau Windows | `C:\ProgramData\Olivia` (repli : dossier de l'utilisateur) |
| Application de bureau macOS | `~/Library/Application Support/Olivia` |

Une installation antérieure qui écrivait dans Program Files est **recopiée** au premier
démarrage (l'ancien dossier reste en sauvegarde). Le lanceur affiche l'emplacement retenu et
signale clairement un dossier non modifiable.

> Un dossier **commun au poste** (`ProgramData`) est lisible par tous les utilisateurs Windows
> du poste, comme un disque portable. C'est voulu (les comptes créés par le service
> informatique servent à toutes les sessions), mais à connaître.

---

## 🔐 Comptes et organisations

Se connecter est **obligatoire**. Chaque compte appartient à exactement une **organisation** ;
conversations, réglages, index et modèle Word sont rangés dans
`profiles/<profile_id>/` du dossier des données — un identifiant deviné d'une autre
organisation ne donne accès à rien.

Une installation neuve démarre **sans aucun compte**. L'écran de connexion le détecte
(`GET /api/auth/etat`) et explique comment créer le premier. La création est volontairement
réservée au **service informatique**, en ligne de commande, sans formulaire d'inscription :

| Où | Commande |
|---|---|
| Application de bureau | bouton de l'écran de connexion, ou menu *Créer un compte…* |
| Installeur Inno Setup | case en fin d'installation, ou menu Démarrer → *Créer un compte Oliv'IA* |
| Disque portable | double-clic sur `Creer-un-compte.bat` |
| Exécutable | `ai-webapp.exe init` |
| Sources | `python launch.py init` ou `python backend/manage_users.py init` |

Commandes détaillées (mêmes noms avec `ai-webapp.exe`, `python launch.py` ou
`python backend/manage_users.py`) :

```bash
init                                   # assistant : organisation + compte
create-profile "Nom de l'organisation" # crée une organisation, affiche son identifiant
create-user <identifiant> <id-du-profil>
list-profiles
```

- Le mot de passe est **demandé au clavier, masqué et confirmé** (passé en argument, il
  resterait dans l'historique du terminal). L'ancienne forme
  `create-user <identifiant> <mot-de-passe> <id-du-profil>` reste acceptée, avec un
  avertissement.
- **Politique** : 8 caractères minimum et 3 types parmi minuscules, majuscules, chiffres,
  caractères spéciaux.
- **Session** : cookie `olivia_session` (`HttpOnly`, `SameSite=Lax`), valable **8 h**.
- **Suppression** : aucune commande à ce jour ; retirer l'entrée de `profiles/registry.json` /
  `profiles/users.json` et le dossier `profiles/<profile_id>/`. Les sessions d'un compte
  supprimé sont refusées dès la requête suivante.

---

## ⚙️ Configuration

### Variables d'environnement

Lues au démarrage depuis `backend/.env` (modèle : `backend/.env.example`) ; une variable déjà
définie dans l'environnement reste prioritaire.

| Variable | Défaut | Rôle |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | adresse d'Ollama |
| `FS_ROOT` | `~/Documents` | dossier de travail par défaut, tant qu'aucun n'est choisi dans l'interface |
| `FRONTEND_DIST` | `frontend/dist` | interface buildée servie sur `/ui` |
| `OLIVIA_DATA_DIR` | — | dossier des données (voir [Emplacement des données](#-emplacement-des-données)) |
| `BRAVE_API_KEY` | — | clé Brave Search, si elle n'est pas saisie dans les Paramètres |
| `OLIVIA_PAUSE_FIN` | — | garde la fenêtre de l'assistant de compte ouverte à la fin (positionnée par l'application de bureau) |
| `OLIVIA_PYTHON` | — | application de bureau en développement : interpréteur Python à utiliser |

### Paramètres dans l'interface (⚙️)

Réglages **propres à chaque organisation** (`profiles/<profile_id>/settings.json`), modifiables
sans redémarrage. En **mode simple** (défaut), les onglets *Recherche web* et *Connexions*, le
choix du périphérique et le prompt système sont masqués ; **🔧 Réglages avancés** les affiche,
**← Revenir au mode simple** les masque (choix mémorisé).

| Onglet | Réglages |
|---|---|
| **Préférences** | style de raisonnement, ton, température (0 à 2) ; *avancé* : périphérique GPU/CPU, prompt système |
| **Documents** | dossiers de travail (un par ligne, `chemin \| libellé`), OCR (activation, état, chemin de Tesseract), recherche par le sens (état, construire / annuler l'index), modèle Word de l'établissement |
| **Formules** | appel, formule de politesse, ville (« Fait à … »), signature par défaut des documents Word |
| **Recherche web** *(avancé)* | moteur (SearXNG / Brave / DuckDuckGo), URL SearXNG, clé Brave, sources officielles, test |
| **Connexions** *(avancé)* | IMAP, calendrier `.ics`, Obsidian, Notion |
| **Confidentialité** | consentement, export, effacement |

**Valeurs par défaut** (`backend/settings.py`, `DEFAULTS`) : température 0,7, style
« équilibré », ton « neutre », mode simple activé, moteur de recherche DuckDuckGo, URL SearXNG
`http://localhost:8888`, sources officielles désactivées, OCR activé, tous les connecteurs
désactivés. Le périphérique (GPU/CPU) est **détecté** au premier lancement de chaque
organisation (voir ci-dessous).

Chaque valeur enregistrée est **validée** (type, choix fermés, bornes, longueur) : une valeur
invalide est refusée (HTTP 400, message nommant le champ) ; une clé inconnue héritée d'une
ancienne version est ignorée.

### GPU / CPU

Sélecteur **⚡ Rapide (GPU) / 🧩 Standard (CPU)** dans la barre du haut (et dans les
Paramètres en mode avancé). En CPU, le backend force `num_gpu=0` à chaque requête.

**Détection automatique** (`backend/hardware.py`) : une organisation **jamais configurée**
interroge `nvidia-smi` et retient `gpu` si une carte NVIDIA d'au moins ~8 Go de VRAM est
détectée, `cpu` sinon (y compris sans `nvidia-smi`, donc sur Mac et sur les postes sans carte
NVIDIA). Raison : sur un poste sans carte dédiée, une réponse de `mistral-nemo` a pu prendre
**45 minutes** en conditions réelles. Un choix enregistré n'est **jamais** re-détecté
automatiquement ; l'effacement RGPD des données relance la détection.

Chaque réponse est plafonnée à **4 096 jetons** (`num_predict`) ; une réponse coupée par ce
plafond est signalée. Les modèles restent chargés en mémoire (`keep_alive=-1`) pour éviter un
rechargement après inactivité.

---

## 🧭 Utilisation

### Mode simple

Oliv'IA démarre en **mode simple** : la **conversation**, les **documents**, la **barre des
outils connectés** et le bouton **🌐 Recherche web**. Le service informatique passe une fois en
mode avancé pour tout configurer, puis laisse Oliv'IA en mode simple.

### Conversations

La barre latérale a deux onglets : **💬 Conversations** et **📁 Documents**. Chaque
conversation est enregistrée **à la fin de chaque réponse** (y compris après « ⏸ Stop ») dans
`profiles/<profile_id>/conversations/<id>.json`, écriture atomique. « ＋ Nouvelle
conversation » ne crée d'entrée qu'une fois un échange fait.

Le HTML des réponses est assaini (DOMPurify) : une réponse nourrie par le web n'est pas du
contenu de confiance ; les balises qui déclencheraient une requête réseau (`img`, `iframe`,
`video`…) sont retirées.

### Dossiers de travail

Onglet **📁 Documents** : une liste déroulante bascule entre les dossiers ; **📂 Parcourir…**
part des lecteurs de la machine et permet d'**ajouter** ou de **retirer** un dossier, en mode
simple. Google Drive et OneDrive se synchronisent dans un dossier local : il suffit de désigner
ce dossier.

### Fichiers

- **Importer** : « ⬆ Importer un fichier » (texte/code, `.csv`, `.xlsx`, `.docx`, `.pdf`,
  images ; 25 Mo max ; nom assaini). Un fichier du même nom n'est **jamais remplacé** : l'import
  est renommé (`nom (2).ext`) et l'interface le signale.
- **Prévisualiser** : tableau pour CSV/Excel, texte pour Word, image, PDF dans un cadre.
- **Télécharger** : « ⬇ Télécharger » dans l'aperçu.
- **Ajouter à la conversation** : le contenu est transmis au modèle comme contexte.

### Retrouver une information dans ses documents

Champ de recherche de l'onglet Documents, deux modes :

- **🔤 Mots-clés** : on écrit simplement les mots (« eleve » trouve « élève »). Lit **à
  l'intérieur** des fichiers : Word (tableaux compris), Excel (toutes les feuilles), PDF, CSV,
  texte. Résultats groupés par document, avec extraits ; un dossier volumineux est exploré dans
  des limites de temps et de nombre de fichiers, signalées quand elles se déclenchent.
- **🧠 Par le sens** : « lettre aux parents pour la sortie scolaire » retrouve une
  « autorisation de sortie pédagogique ». Documents découpés en extraits d'environ 1 200
  caractères, vectorisés par `bge-m3` via Ollama, rangés dans un index FAISS par organisation
  (`profiles/<profile_id>/docindex/`, métadonnées en JSON). L'index se met à jour **tout seul**
  au démarrage et après chaque import ; *Paramètres → Documents* permet de forcer une mise à
  jour. Sans `bge-m3`, sans Ollama ou sans FAISS, le mode est indiqué indisponible, sans erreur.

Chaque résultat peut être **ajouté à la conversation** (plusieurs à la fois) ; Oliv'IA précise de
quel document vient chaque information. Le contexte transmis est borné (**8 000 caractères**
par document, **24 000** au total) et **toute coupe est signalée** (« ⚠️ tronqué »).

### 🔍 Documents scannés — OCR

Un PDF scanné est fait d'images : sans OCR, il resterait introuvable. Oliv'IA les fait lire par
**Tesseract**, en local, en français.

- Concerne les PDF **sans couche texte** et les images (`.png`, `.jpg`, `.tif`…) ; un PDF qui
  contient du texte n'est jamais envoyé à l'OCR.
- Traitement local en sous-processus ; résultat **mis en cache** (chemin, date, taille).
- Bornes : **8 pages** par document, **20 s** par document, **2** reconnaissances simultanées ;
  une coupe est signalée.
- Les résultats issus de l'OCR sont **marqués** : une transcription automatique n'est jamais
  fiable à 100 % (manuscrit, page inclinée, mauvaise photocopie).

**Installer le moteur** (il n'est pas fourni par `pip`) :

- **Windows** : build de référence https://github.com/UB-Mannheim/tesseract ; copier le binaire,
  ses DLL et `tessdata\` dans `tesseract\` à la racine du projet (ou à côté de
  `ai-webapp.exe`), avec `tessdata\fra.traineddata` (dépôt officiel `tesseract-ocr/tessdata` :
  l'installation par défaut ne pose que l'anglais).
- **macOS** : par exemple `brew install tesseract tesseract-lang` (non testé dans ce projet).
  Une application lancée depuis le Finder ne voit pas toujours le `PATH` du terminal : si
  l'état du moteur indique qu'il est introuvable, renseigner son chemin dans *Paramètres →
  Documents* (par exemple `/opt/homebrew/bin/tesseract`).

Oliv'IA cherche le moteur livré dans `tesseract/`, puis celui du `PATH`, puis le chemin réglé.
Ce chemin étant **exécuté**, il doit désigner un programme nommé `tesseract` (ou son dossier) :
tout autre programme est refusé. **Sans moteur, rien ne casse** : les documents scannés restent
consultables, ils ne sortent simplement pas dans les recherches.

### 📄 Créer un document Word

Sous chaque réponse terminée, **📄 Créer un document Word** :

1. choisir le type et compléter les champs proposés :

   | Type | Composition |
   |---|---|
   | **Circulaire** | titre, sous-titres en bandeau |
   | **Courrier aux familles** | destinataire, lieu et date, objet, appel, formule de politesse |
   | **Convocation** | destinataire, lieu et date, objet, appel, formule de politesse |
   | **Compte rendu** | lieu et date, participants, sous-titres en bandeau |

2. **rédaction dirigée** : la réponse est d'abord réécrite par le modèle en **corps seul**
   (sans titre, objet, appel, politesse ni signature, que le document ajoute lui-même) ; si
   cette étape échoue, le texte d'origine est utilisé et un nettoyage côté serveur sert de filet ;
3. le document est créé **dans le dossier de travail**, sans jamais écraser un fichier existant,
   puis proposé en aperçu.

**Modèle de l'établissement** (*Paramètres → Documents*) : indiquer un document Word de
l'établissement (chemin affiché dans 📁 Documents, ex. `r0/documents/Circulaire.docx`) ;
Oliv'IA en retire tout le texte et garde l'identité (logo, en-tête, pied de page, polices,
marges). Modèle rangé dans `profiles/<profile_id>/modele-etablissement.docx`, avec repli sur un
modèle commun `modeles/modele-etablissement.docx` déposé par le service informatique.

**Formules** (*Paramètres → Formules*) : appel (« Madame, Monsieur, » par défaut), formule de
politesse, ville, signature. Laissées vides, les valeurs par défaut de `backend/docgen.py`
(`TEXTES`) s'appliquent — dont la ville **« Marseille »**, à corriger pour un autre
établissement.

---

## 🌐 Recherche web

### Dans la conversation (bouton 🌐)

Le bouton **🌐 Recherche web**, sous la zone de saisie, est un interrupteur. Activé, Oliv'IA
interroge le moteur **avant** de répondre, transmet les 5 premiers résultats au modèle et
**cite ses sources** (`[1]`, `[2]`…), listées sous la réponse (« 🌐 N sources web »). Visible
en mode simple : c'est la **seule action qui fait sortir une donnée de la machine** (la requête
part vers le moteur), et elle reste un choix explicite. Si le moteur ne répond pas, Oliv'IA
répond quand même et le dit.

| Moteur | Prérequis | Fiabilité |
|---|---|---|
| **SearXNG** | Docker (ci-dessous) | élevée, 100 % auto-hébergé |
| **Brave Search** | clé d'API (*Paramètres → Recherche web*) | élevée, sans Docker |
| **DuckDuckGo** (défaut) | aucun | moyenne (lecture de la page HTML, bloquée après des requêtes rapprochées) |

**Repli automatique** : le moteur choisi est essayé en premier, puis les autres. Le moteur qui a
**réellement** répondu est indiqué (`provider` dans `POST /api/search`) — un repli envoie la
requête à un autre moteur que celui configuré. Une requête sans résultat n'est pas traitée
comme une panne.

**Clé Brave** : stockée dans les réglages de l'organisation, **jamais renvoyée en clair** à
l'interface ; `BRAVE_API_KEY` reste accepté en repli. Les conditions du palier gratuit sont
fixées par Brave (`brave.com/search/api`) et peuvent changer.

### Mode « sources officielles »

*Paramètres → Recherche web → Privilégier les sites officiels* (désactivé par défaut) restreint
aux domaines `education.gouv.fr`, `eduscol.education.fr`, `legifrance.gouv.fr`,
`service-public.fr`, `gouv.fr`, `onisep.fr`. Deux barrières : restriction `site:` dans la
requête, puis **refiltrage par domaine** des résultats (qui écarte aussi les sosies du type
`education.gouv.fr.exemple.com`). **Aucun repli silencieux** : sans source officielle, la liste
est vide et Oliv'IA le dit.

### Installer SearXNG

```powershell
docker run -d --name olivia-searxng --restart unless-stopped `
  -p 8888:8080 -v "D:\Olivia\searxng:/etc/searxng" `
  -e "SEARXNG_BASE_URL=http://localhost:8888/" searxng/searxng:latest
```

> ⚠️ La configuration par défaut de SearXNG **n'autorise pas le format JSON** (HTTP 403 sur
> `/search?format=json`). Ajouter dans `searxng/settings.yml` :
> ```yaml
> search:
>   formats: [html, json]
>   default_lang: "fr-FR"
> ```
> puis `docker restart olivia-searxng`. Le dossier `searxng/` est ignoré par Git (il contient
> une `secret_key` propre à la machine).

**Qwant** n'est pas disponible : son accès automatisé est protégé par un captcha (constaté en
appel direct comme via le connecteur de SearXNG, qui signale `qwant: CAPTCHA`).

---

## 🔌 Outils connectés

Sous la barre de titre, chaque connecteur **activé** s'affiche avec un point d'état (vert =
connecté, orange = à configurer, gris = inactif) **et** un libellé (l'information n'est pas
portée par la seule couleur). La boîte mail affiche un badge 🔔 des **non-lus**, rafraîchi
toutes les 60 s.

| Service | État | Configuration |
|---|---|---|
| **IMAP** (boîte pro) | ✅ fonctionnel, non-lus | serveur, adresse, mot de passe d'application, dossier |
| **Calendrier `.ics`** | ✅ fonctionnel | chemin d'un fichier `.ics` exporté |
| **Obsidian / Notion** | 🟡 squelette | chemin du coffre / jeton |

**Pas de connecteur Google Drive / OneDrive / Gmail / Outlook** : Drive et OneDrive se
synchronisent déjà dans un dossier local ; côté courrier, les API Google et Microsoft imposent
une vérification d'application ou le consentement d'un administrateur du tenant (souvent
l'académie). IMAP couvre le besoin. Les anciens squelettes OAuth Gmail/Outlook, École Directe
et Service-Public/FranceConnect ont été **retirés** : ils laissaient croire à des fonctions
inexistantes. Leurs clés restées dans un `settings.json` sont ignorées.

---

## 🔒 RGPD — vos données

Tout reste **local**, sauf la recherche web quand elle est activée. *Paramètres →
Confidentialité* :

- **Export** (`GET /api/privacy/export`) : toutes les données de l'organisation connectée en
  JSON (réglages, conversations…). Les **secrets** (mot de passe IMAP, clé Brave, jeton Notion)
  y sont **masqués**, listés dans `secrets_masques` — un fichier téléchargé circule.
- **Effacement** (`POST /api/privacy/delete`), pour l'organisation connectée seulement :
  réinitialise les réglages (GPU/CPU re-détecté), supprime conversations et index de recherche
  par le sens, vide le dossier `_uploads` des dossiers de travail et retire du cache OCR le
  texte de ses documents. Les autres documents ne sont pas touchés. L'effacement de l'index ne
  peut pas être annulé par une construction en cours.
- **Consentement** : bandeau informatif au premier lancement.
- `GET` / `PUT /api/settings` ne renvoient jamais les secrets en clair.

> Ce sont des **mesures techniques**. La conformité formelle (registre, information, analyse
> d'impact le cas échéant) reste à mener par la structure qui déploie Oliv'IA.

---

## ♿ Accessibilité (RGAA / WCAG AA)

- Structure sémantique et repères ARIA (`header`, `main`, `dialog`, `aria-label`, `aria-live`).
- Lien d'évitement « Aller au contenu principal ».
- Navigation clavier complète, focus visible (`:focus-visible`), modales fermables par `Échap`.
- États non portés par la seule couleur.
- Contrastes relevés, respect de `prefers-reduced-motion`.

> Mesures techniques, sans audit RGAA formel à ce jour.

---

## 🛡️ Sécurité

**Périmètre des fichiers**
- Routes `/api/fs/*` limitées aux **dossiers de travail** de l'organisation (`safe_path()`) :
  sortie du périmètre → HTTP 403, y compris par lien symbolique.
- `GET /api/fs/drives` et `/api/fs/browse` sortent volontairement du périmètre pour choisir un
  dossier, mais ne renvoient **que des noms de dossiers**, sans récursion.
- **Dossiers réservés** (`backend/zones.py`) : le paquet `backend/`, le dossier des données,
  `profiles/`, le cache OCR, `modeles/`, `tesseract/`, `ollama/` et, dans l'exécutable,
  `_internal/`. Ils ne peuvent pas devenir un dossier de travail (HTTP 400) et restent
  invisibles et refusés sous un dossier plus large (HTTP 403) — lecture, import, recherche,
  index. Sans cela, une organisation pouvait lire les jetons de session des autres.
- Import : liste d'extensions autorisées, nom assaini, 25 Mo max, jamais d'écrasement.
- Chemin de l'OCR limité à un exécutable nommé `tesseract`.
- Modèle Word par organisation ; l'ancien réglage `docgen_template_path` (emplacement libre) est
  supprimé et ignoré.

**Connexion**
- Mots de passe **jamais stockés en clair** : PBKDF2-HMAC-SHA256 salé, **600 000 itérations**
  (valeur recommandée par l'OWASP Password Storage Cheat Sheet pour PBKDF2-HMAC-SHA256) ; un
  compte à l'ancien format (200 000) est remis à niveau à sa connexion suivante.
- **Temporisation des échecs** (`backend/tentatives.py`) : à partir du 3ᵉ échec consécutif sur
  un identifiant, attente qui double (20 s, 40 s, 80 s…, 1 h au plus) ; 25 échecs au plus sur
  24 h glissantes ; pendant l'attente, même le bon mot de passe est refusé (HTTP 429). Règles
  calquées sur le cas « mot de passe + restriction d'accès » de la recommandation CNIL relative
  aux mots de passe (délibération n° 2022-100 du 21 juillet 2022).
- Un identifiant inconnu est traité **comme un vrai**, dans le même temps : ni la réponse ni le
  chronomètre ne révèlent quels comptes existent.
- Sessions par jeton opaque (32 octets), 8 h ; compte supprimé → session refusée et supprimée.

**HTTP**
- Écoute sur `127.0.0.1` par défaut ; **CORS** limité au poste local.
- En-têtes sur toutes les réponses : `Content-Security-Policy`, `X-Content-Type-Options`,
  `X-Frame-Options: SAMEORIGIN`, `Referrer-Policy`, `Permissions-Policy`.
- Téléchargements en pièce jointe ; seul l'aperçu PDF est servi « inline ».
- Réglages validés à l'enregistrement ; secrets masqués dans l'API et l'export.

---

## 🔗 API HTTP

Toutes les routes exigent une session, sauf `POST /api/auth/login`, `GET /api/auth/etat` et
`GET /api/health`. La documentation interactive générée par FastAPI est servie sur `/docs`.

| Domaine | Routes |
|---|---|
| Authentification | `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`, `GET /api/auth/etat` (y a-t-il au moins un compte ?) |
| Modèles et chat | `GET /api/models`, `GET /api/moteur/etat` (Ollama joignable ? modèles nécessaires installés ?), `POST /api/chat/stream` (SSE), `POST /api/chat` |
| Fichiers | `GET /api/fs/list`, `GET /api/fs/read`, `GET /api/fs/preview`, `GET /api/fs/text`, `GET /api/fs/download`, `POST /api/fs/upload` |
| Choix des dossiers | `GET /api/fs/drives`, `GET /api/fs/browse` |
| Recherche documentaire | `GET /api/fs/search` (mots-clés), `GET /api/fs/search/semantic` (par le sens) |
| Index par le sens | `GET /api/docindex/status`, `POST /api/docindex/build`, `POST /api/docindex/cancel` |
| Réglages | `GET /api/settings`, `PUT /api/settings` |
| OCR | `GET /api/ocr/status` |
| Documents Word | `GET /api/documents/status`, `POST /api/documents/modele`, `POST /api/documents/generate` |
| Recherche web | `POST /api/search` (`{query, limit}`) |
| Conversations | `GET /api/conversations`, `GET`/`PUT`/`DELETE /api/conversations/{id}`, `POST /api/conversations` |
| Connecteurs | `GET /api/connectors/status`, `GET /api/connectors/mail/unread`, `GET /api/connectors/imap/preview`, `GET /api/connectors/calendar/preview` |
| RGPD | `GET /api/privacy/export`, `POST /api/privacy/delete` |
| Service | `GET /api/health` (état, version, adresse d'Ollama), `GET /` (redirige vers `/ui/`, ou `/docs` sans interface buildée) |

---

## 🧪 Tests et intégration continue

**Backend** (pytest, depuis la racine) :

```bash
pip install pytest
python -m pytest tests
```

118 tests, tous au vert en Python 3.11 au moment de cette mise à jour. Ils couvrent le
cloisonnement entre organisations, l'état du moteur d'IA, les comptes et la connexion (temporisation, temps constant,
remise à niveau du hachage), l'emplacement des données, l'import sans écrasement, la purge de
l'index, les erreurs du moteur dans le chat, l'export RGPD, la validation des réglages et le
lanceur (`--parent-stdin`).

**Application de bureau** (Node, fonctions pures de `desktop/lib/outils.js`) :

```bash
cd desktop && npm test        # 10 tests
```

**Interface** : `cd frontend && npm run lint`.

**CI — workflow « Tests »** (`.github/workflows/tests.yml`), sur chaque pull request et
chaque push sur `main` :
- **backend** : flake8 + pytest, sous Linux en Python 3.10, 3.11, 3.12, 3.13 et 3.14, et
  sous Windows et macOS en Python 3.12 (la version des installeurs) ;
- **interface** : ESLint + build Vite ;
- **application de bureau** : tests Node (sans télécharger Electron).

**CI — workflow « Application de bureau »** (`.github/workflows/bureau.yml`) :
- déclenchement manuel (*Actions → Application de bureau → Run workflow*) ou étiquette `v*` ;
- sur `macos-latest` (Apple Silicon) et `windows-latest` : tests du backend, build de
  l'interface, PyInstaller, tests et build Electron **non signé** ;
- installeurs déposés dans les **artefacts** du run ;
- avec la case **« publier »** cochée (ou une étiquette `v*`), joints en plus à une **release
  GitHub brouillon** `v<version>`, créée une seule fois avant les deux constructions. Une fois
  publiée, elle sert de source aux mises à jour automatiques.

Publier une version :
1. augmenter `version` dans `desktop/package.json` et fusionner sur `main` ;
2. *Actions → Application de bureau → Run workflow*, branche `main`, cocher **publier** ;
3. vérifier la release brouillon (*Releases*), puis **Publish release**. GitHub crée alors
   l'étiquette `v<version>`.

Pousser une étiquette (`git tag v1.1.0 && git push origin v1.1.0`) donne le même résultat.

---

## 🩺 Dépannage

| Symptôme | Piste |
|---|---|
| « Le moteur d'IA (Ollama) ne répond pas » dans le chat | suivre le panneau affiché en haut de la fenêtre : installer ou démarrer Ollama ; vérifier aussi `OLLAMA_URL` |
| Panneau « Oliv'IA n'est pas encore prête » | taper les commandes `ollama pull` proposées ; le panneau disparaît seul une fois le modèle installé |
| « Oliv'IA ne répond plus » (application de bureau) | icône Oliv'IA → *Redémarrer Oliv'IA* ; sinon consulter `olivia.log` |
| « Oliv'IA ne répond pas » (navigateur) | la fenêtre noire du lanceur a été fermée : relancer Oliv'IA |
| Réponses extrêmement lentes | le mode GPU est choisi sur un poste sans carte adaptée : passer en 🧩 CPU |
| L'écran de connexion dit qu'il n'y a aucun compte | créer le premier compte ([Comptes](#-comptes-et-organisations)) |
| « Trop de tentatives » (HTTP 429) | attendre le délai affiché ; il double à chaque nouvel échec |
| Échec de connexion juste après l'installation | dossier des données non modifiable : le lanceur l'affiche au démarrage ([Emplacement](#-emplacement-des-données)) |
| Recherche par le sens indisponible | `ollama pull bge-m3`, puis *Paramètres → Documents → Construire l'index* |
| PDF scanné introuvable | Tesseract absent ou non trouvé : voir l'état dans *Paramètres → Documents* |
| SearXNG renvoie HTTP 403 | activer le format JSON dans `searxng/settings.yml` |
| Application de bureau : fenêtre d'erreur au démarrage | consulter `olivia.log` (dossier des journaux d'Electron) |
| macOS refuse d'ouvrir Oliv'IA | application non signée : voir [Application de bureau](#️-application-de-bureau-macos-windows) |
| Exécutable sans interface | PyInstaller lancé ailleurs qu'à la racine ; reconstruire depuis la racine |

---

## ⚠️ Limites connues et points non vérifiés

- **Installeurs `.dmg` et `.exe` de l'application de bureau** : chaîne complète construite et
  testée **sous Linux** (même code que macOS : backend embarqué, connexion, arrêt du backend en
  moins d'une seconde à la fermeture comme après un plantage, navigation externe bloquée). Pas
  encore vérifiés sur de vrais postes : installeurs, premier lancement non signé sur macOS,
  droits de `C:\ProgramData\Olivia`, icônes, raccourci global, mise à jour automatique. Le
  workflow « Application de bureau » n'a pas encore été exécuté.
- **Panneau « Oliv'IA n'est pas encore prête »** : vérifié dans Chromium avec un Ollama simulé ;
  les consignes d'installation (application Ollama, commande `ollama` dans le Terminal ou
  l'Invite de commandes) restent à confirmer sur de vrais postes Mac et Windows.
- **Mac Intel** : non couvert par la CI (`macos-latest` construit pour Apple Silicon).
- **Installeur Inno Setup** et **ACL NSIS** : non recompilés ni testés après les dernières
  modifications.
- **Fenêtre de contexte** : `num_ctx` n'est pas fixé, Ollama applique sa valeur par défaut ;
  de longs documents ajoutés à la conversation peuvent donc être tronqués par le moteur
  lui-même, au-delà des bornes signalées par Oliv'IA.
- **Versions non alignées** entre composants (voir [Versions](#️-versions)).
- **Pas de suppression de compte** en ligne de commande.
- **Connecteurs Obsidian et Notion** : squelettes.
- **Python 3.10, 3.12 à 3.14** : déclarés compatibles par `requirements.txt` ; testés par le
  workflow « Tests » à partir de son premier passage.

---

## 🎨 Logo et icônes

Toutes les icônes viennent d'**un seul fichier**, `visuel/logo.png` : tuile bleue aux coins
arrondis, « O » au rameau d'olivier et mot « Oliv'IA ». Pour changer de logo, remplacer ce
fichier puis :

```bash
pip install pillow numpy
python visuel/generer_icones.py      # depuis la racine du dépôt
```

Le script en tire deux variantes (coins rendus transparents) :
- **logo complet** (O + « Oliv'IA ») pour les grandes tailles, où le mot reste lisible ;
- **marque** (la même tuile avec le seul « O » au rameau, agrandi) pour les petites tailles et
  l'interface, où le mot deviendrait illisible et où « Oliv'IA » est déjà écrit à côté.

| Fichier | Variante | Usage |
|---|---|---|
| `frontend/src/assets/logo-mark.png` | marque, 512 px | barre du haut, connexion, accueil |
| `frontend/public/favicon.ico` | marque, 16-48 px | onglet du navigateur |
| `ai-webapp.ico` | marque 16-48 px, logo 64-256 px | exécutable Windows, installeur Inno Setup |
| `desktop/build/icon.ico` | idem | application de bureau et installeur Windows |
| `desktop/build/icon.png` | logo, 1024 px avec marge transparente | application macOS |
| `desktop/icons/fenetre.png` | marque, 256 px | fenêtre, écran de démarrage |
| `desktop/icons/tray.png`, `tray@2x.png` | marque, 32 et 64 px | barre des menus / zone de notification |
| `visuel/logo-transparent.png` | logo, 512 px | en-tête de ce README |

Le script fixe deux réglages :
- **marge macOS** : la tuile occupe 824 px d'une toile de 1024. C'est la convention de la
  grille d'icônes macOS, non revérifiée sur la documentation d'Apple ;
- **format du `.ico`** : bitmap classique jusqu'à 128 px, PNG à 256 px.

Le logo complet affiche le mot « Olivia » tel qu'il figure sur l'image fournie. Pour qu'il
affiche « Oliv'IA », remplacer `visuel/logo.png` par une version modifiée et relancer le script.

## 📁 Arborescence

```
Olivia/
├── README.md
├── launch.py              ← lanceur multi-OS (dev) + point d'entrée de l'exécutable + commandes de comptes
├── build.spec             ← PyInstaller (embarque backend + frontend/dist, jamais les données)
├── deploy-portable.ps1    ← build + synchro vers un disque portable
├── start-ollama.ps1       ← lance Ollama seul (Windows)
├── ai-webapp.ico          ← icône de l'exécutable Windows
├── visuel/logo.png        ← logo source (toutes les icônes en sont tirées)
├── visuel/logo-transparent.png ← logo à coins transparents (en-tête du README)
├── visuel/generer_icones.py ← régénère toutes les icônes
├── .github/workflows/tests.yml    ← CI : tests sur chaque PR
├── .github/workflows/bureau.yml   ← CI : installeurs macOS et Windows
├── installer Olivia/olivia.iss    ← installeur Inno Setup
├── portable/              ← Lancer-Olivia.bat, Creer-un-compte.bat, LISEZ-MOI.txt
├── tests/                 ← tests pytest du backend
├── desktop/               ← application de bureau Electron
│   ├── package.json       ← version, scripts, configuration electron-builder
│   ├── main.js            ← processus principal : backend, fenêtre, icône, raccourci, mises à jour
│   ├── preload.js         ← pont minimal vers la page (window.oliviaBureau)
│   ├── chargement.html    ← écran d'attente du démarrage
│   ├── lib/outils.js      ← fonctions pures testées (port, données, commande, liens)
│   ├── scripts/preparer.mjs ← copie du backend compilé avant empaquetage
│   ├── build/             ← icon.png (macOS), icon.ico (Windows), installer.nsh (droits sur ProgramData\Olivia)
│   ├── icons/             ← icônes de fenêtre et de barre des menus
│   └── test/outils.test.js
├── backend/
│   ├── main.py            ← FastAPI : auth, chat, fichiers, recherche, documents, réglages, connecteurs, RGPD
│   ├── __init__.py        ← chargement de backend/.env
│   ├── settings.py        ← réglages par organisation, validation, modèle par périphérique
│   ├── hardware.py        ← détection VRAM (nvidia-smi)
│   ├── profiles.py        ← registre des organisations
│   ├── emplacements.py    ← emplacement des données (OLIVIA_DATA_DIR, olivia.ini, backend/)
│   ├── zones.py           ← dossiers réservés
│   ├── users.py           ← comptes, politique et hachage des mots de passe
│   ├── tentatives.py      ← temporisation des échecs de connexion
│   ├── sessions.py        ← sessions par cookie (8 h)
│   ├── manage_users.py    ← commandes init / create-profile / create-user / list-profiles
│   ├── conversations.py   ← historique par organisation
│   ├── search.py          ← recherche web, repli entre moteurs, sources officielles
│   ├── documents.py       ← aperçu et extraction de texte
│   ├── docsearch.py       ← recherche par mots-clés
│   ├── docindex.py        ← recherche par le sens (bge-m3 + FAISS)
│   ├── ocr.py             ← OCR Tesseract
│   ├── docgen.py          ← production des documents Word (types, formules)
│   ├── docmodele.py       ← modèle Word de l'établissement
│   ├── moteur.py          ← état du moteur d'IA (Ollama joignable, modèles installés)
│   ├── connectors/        ← imap_client.py, oauth_providers.py (calendrier .ics)
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json, vite.config.js, index.html
    └── src/
        ├── main.js, App.vue, style.css
        ├── stores/          ← chat.js, settings.js, auth.js, moteur.js
        └── components/
            ├── LoginView.vue         ← connexion (sans inscription)
            ├── ChatPanel.vue         ← conversation, recherche web, création de documents Word
            ├── MessageBubble.vue     ← Markdown assaini
            ├── ConversationList.vue  ← historique
            ├── FileExplorer.vue      ← dossiers, import, recherche mots-clés / par le sens
            ├── FolderPickerModal.vue ← parcours des lecteurs
            ├── FilePreview.vue       ← aperçu multi-format
            ├── ModelPicker.vue       ← GPU / CPU
            ├── ConnectedTools.vue    ← barre des outils connectés
            ├── ConsentBanner.vue     ← bandeau RGPD
            ├── MoteurAssistant.vue   ← panneau « Oliv'IA n'est pas encore prête »
            └── SettingsMenu.vue      ← 6 onglets de Paramètres
```

Ignorés par Git : `backend/profiles/`, `backend/.env`, `olivia.ini`, `ollama/`, `tesseract/`,
`modeles/`, `searxng/`, les dossiers de build.

---

## 📜 Historique

| Date | Étape |
|---|---|
| 29/07/2026 | Un modèle par périphérique après tests comparatifs ; onglet *Formules* ; installeur Inno Setup ; plafond de génération |
| 02/08/2026 | Écran de connexion ; détection matérielle GPU/CPU ; garde-fou contre les citations inventées ; `keep_alive=-1` |
| 04/10/2026 — PR #1 | Cloisonnement entre organisations (dossiers réservés, modèle Word par organisation, chemin OCR) ; premier compte sur installation neuve (`init`) ; données hors de Program Files |
| 04/10/2026 — PR #2 | Import sans écrasement ; purge RGPD de l'index non annulable |
| 04/10/2026 — PR #3 | Erreurs du moteur affichées dans le chat ; secrets masqués dans l'export RGPD |
| 04/10/2026 — PR #4 | Connexion robuste (temporisation, temps constant, 600 000 itérations, sessions révoquées) ; validation des réglages ; dépendances npm à jour |
| 04/10/2026 — PR #5 | Application renommée « Oliv'IA » (nom affiché) ; nouveau logo (tuile bleue) et icônes générées par script ; points mineurs (aperçu PDF, GPU/CPU après effacement, `.env`, API dépréciées) ; **application de bureau macOS et Windows** ; README complet ; panneau « Oliv'IA n'est pas encore prête » ; messages d'erreur adaptés à l'application de bureau ; workflow de tests sur les PR |

Détail : `git log`.
