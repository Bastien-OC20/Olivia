# 🌷 Olivia — assistante locale pour le secrétariat de direction

**Olivia** est une assistante IA **100 % locale** conçue pour une **assistante de direction en lycée**.
Objectif : une utilisation **la plus simple possible**, sans donnée envoyée à l'extérieur.

Techniquement, c'est une application web (Vue.js + FastAPI + Ollama) qui :
- Discute avec Ollama (streaming token par token)
- Parcourt un dossier local **sandboxé** (path-traversal protégé)
- **Prévisualise** fichiers texte, code, CSV, Excel (.xlsx), Word (.docx), images et PDF
- **Importe (upload) et télécharge (download)** des fichiers dans le périmètre sandboxé
- Injecte le contenu d'un fichier dans le contexte du LLM (mini-RAG, tous formats prévisualisables)
- Garde l'**historique des conversations** (rouvrir, renommer, supprimer) et affiche
  les réponses en **Markdown** avec liens cliquables
- Laisse **choisir son dossier de travail à la souris** (parcours des lecteurs)
- Effectue des recherches web à la demande (bouton 🌐 du chat) et cite ses sources
  (SearXNG / Brave / DuckDuckGo, avec repli automatique entre moteurs)
- Bascule le calcul **GPU ↔ CPU** — **détecté automatiquement** au premier lancement
  (VRAM d'une carte NVIDIA), avec bascule manuelle toujours possible
- **Comptes par organisation** : connexion requise pour utiliser l'interface,
  données cloisonnées par organisation ; création de compte réservée au service
  informatique (`backend/manage_users.py`), pas d'inscription en libre-service
- Affiche une barre stylisée des **outils connectés** (boîte mail pro avec notification des non-lus, calendrier)
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

## 🔐 Comptes et organisations

Se connecter est **obligatoire** pour utiliser l'interface (écran dédié,
`frontend/src/components/LoginView.vue`). Chaque compte appartient à exactement une
**organisation** (mairie, association, PME, établissement) : conversations, réglages et
index documentaire sont cloisonnés dans `backend/profiles/<profile_id>/` — un
identifiant deviné d'une autre organisation ne donne accès à rien.

**Créer une organisation et un compte** — volontairement en ligne de commande et non
dans l'interface (même logique que les connecteurs OAuth : préparé une fois par le
service informatique, pas par l'utilisatrice finale) :

```bash
python backend/manage_users.py create-profile "Nom de l'organisation"
python backend/manage_users.py create-user <identifiant> <mot-de-passe> <id-du-profil>
python backend/manage_users.py list-profiles
```

Aucune commande de suppression n'existe à ce jour : le retrait d'un compte ou d'une
organisation se fait en éditant `backend/profiles/registry.json` / `users.json` et en
supprimant le dossier `backend/profiles/<profile_id>/` correspondant.

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

Le binaire **n'embarque ni les réglages ni les conversations** : `build.spec` les
retire explicitement. Une installation neuve démarre donc sur les valeurs par défaut,
et un `.exe` distribué ne transporte aucun secret (clé d'API, mot de passe IMAP).

## 🔌 Version portable (clé USB / disque externe)

Olivia tourne entièrement depuis un disque amovible : application, moteur, modèles,
réglages et conversations restent dessus, rien n'est installé sur l'ordinateur hôte.

```powershell
.\deploy-portable.ps1                             # interactif : choix du disque, puis du mode
.\deploy-portable.ps1 -Destination G:\Olivia -Update    # mise à jour silencieuse
.\deploy-portable.ps1 -Destination E:\Olivia -Replace   # réinstallation complète
.\deploy-portable.ps1 -SkipFrontend -SkipExe            # resynchroniser sans rebuilder
```

Le script enchaîne build Vite → build PyInstaller → copie du moteur si nécessaire →
synchronisation, puis vérifie que l'installation est complète.

**Choix du disque** — sans `-Destination`, le script liste les lecteurs et propose
celui qui contient déjà Olivia, sinon le disque non système le plus libre. Les
lecteurs de cartes vides sont écartés. Attention : un disque USB externe est souvent
vu comme « fixe » par Windows, le tri se fait donc sur l'espace libre, pas sur le
type de bus.

**Installation déjà présente** — le script demande quoi faire :

| Mode | Effet |
|---|---|
| `-Update` (défaut) | Remplace l'application. **Conserve** moteur, modèles, conversations et réglages. |
| `-Replace` | Efface intégralement le dossier et repart à neuf. **Destructif** : conversations et réglages perdus, modèles recopiés (plusieurs minutes). |

En mode `-Update`, la synchronisation est un miroir — les fichiers des anciennes
versions sont supprimés — avec quatre éléments sanctuarisés, car ils vivent sur le
disque portable et n'existent pas dans le build :

| Préservé | Pourquoi |
|---|---|
| `ai-webapp\ollama\` | moteur + modèles (~9 Go) : les réécraser à chaque déploiement serait absurde |
| `ai-webapp\tesseract\` | moteur OCR (~190 Mo) |
| `..\backend\profiles\` | comptes, organisations, sessions et **conversations** (cloisonnées par organisation) |
| `..\backend\settings.json` | réglages du mode mono-organisation historique |
| `..\backend\ocr_cache\`, `..\backend\docindex\` | caches reconstructibles (OCR, index de recherche par le sens) — non destructeurs à perdre, mais coûteux à refaire |

Les deux moteurs ne sont pas dans le build : ils sont copiés depuis `ollama/` et
`tesseract/` du projet uniquement s'ils manquent à destination — première
installation ou réinstallation.

> PyInstaller est lancé **depuis la racine du projet** par le script : `build.spec`
> désigne ses sources en relatif (`backend`, `frontend/dist`), et ces chemins sont
> résolus par rapport au répertoire courant. Lancé d'ailleurs, il produit un
> exécutable **sans interface** et déverse son build dans le mauvais dossier — panne
> silencieuse constatée en conditions réelles. Le script vérifie désormais que
> l'interface est bien embarquée et échoue sinon.

Deux garde-fous refusent d'écrire au mauvais endroit : lecteur absent (disque non
branché), et dossier non vide qui ne ressemble pas à une installation Olivia —
`-Force` outrepasse le second. Sans console (tâche planifiée), le script retombe
sur les valeurs par défaut plutôt que de bloquer, et ne passe **jamais** en mode
destructif sans `-Replace` explicite.

Structure produite (`ollama\` doit être **dans** `ai-webapp\` : le lanceur le cherche
à côté de l'exécutable, pas du `.bat`) :

```
G:\Olivia\
├── Lancer-Olivia.bat      ← double-clic (source versionnée : portable/)
├── LISEZ-MOI.txt          ← notice non technique
└── ai-webapp\
    ├── ai-webapp.exe
    ├── _internal\         ← dont réglages et conversations, créés à l'usage
    └── ollama\            ← moteur + models\
```

> L'exécutable n'étant pas signé, Windows affiche « Windows a protégé votre
> ordinateur » au premier lancement : *Informations complémentaires* → *Exécuter
> quand même*. C'est expliqué dans le `LISEZ-MOI.txt`.

Icône personnalisée : placez `ai-webapp.ico` à la racine et décommentez la ligne
`# icon='ai-webapp.ico'` dans `build.spec`.

## 🎮 CPU / GPU et modèles

Un sélecteur **⚡ Rapide (GPU) / 🧩 Standard (CPU)** est présent dans la barre du haut
(et dans Paramètres) :
- **GPU** : Ollama utilise la carte automatiquement.
- **CPU** : le backend force `num_gpu=0` à chaque requête.

**Un seul modèle par périphérique** (`backend/settings.py`, `DEVICE_MODELS`), pas une
liste de choix : pour une utilisatrice non technique, une liste — même « recommandée » —
est un risque de mauvaise sélection silencieuse, et une charge de test qui grandit avec
chaque modèle ajouté. Les deux modèles retenus ont été choisis après comparaison sur un
prompt de référence en conditions réelles, pas sur leur réputation :

| Périphérique | Modèle | Taille |
|---|---|---|
| GPU (cible : RTX 5060 8 Go) | `mistral-nemo:12b-instruct-2407-q4_K_M` | ~7,5 Go |
| CPU / bureautique | `gemma2:2b` | ~1,6 Go |

**Détection automatique au premier lancement** (`backend/hardware.py`) : une organisation
**jamais configurée** interroge `nvidia-smi` et retient `gpu` si une carte NVIDIA d'au
moins ~8 Go de VRAM est détectée, `cpu` sinon (y compris si `nvidia-smi` est absent —
c'est le repli sûr). Objectif : éviter qu'un poste sans carte graphique dédiée hérite du
modèle GPU par défaut — vécu en conditions réelles, une réponse de `mistral-nemo` peut y
prendre **45 minutes**. Une organisation déjà configurée n'est **jamais** re-détectée
automatiquement : le réglage enregistré (via ⚡/🧩) prévaut toujours, y compris si la
clé/l'installation change ensuite de machine.

## 💬 Historique des conversations

La barre latérale a deux onglets : **💬 Conversations** et **📁 Documents**.

Chaque conversation est enregistrée automatiquement **à la fin de chaque réponse**
(y compris après un « ⏸ Stop », la réponse partielle est conservée), dans
`backend/profiles/<profile_id>/conversations/<id>.json` — cloisonnée **par
organisation**, un fichier par conversation, écriture atomique. Le dossier
`backend/profiles/` est ignoré par Git. On peut rouvrir, **renommer** et **supprimer** une
conversation depuis la liste ; « ＋ Nouvelle conversation » repart de zéro sans
créer d'entrée tant que rien n'a été échangé.

Ce sont des **données personnelles** : elles sont incluses dans
`GET /api/privacy/export` et effacées par `POST /api/privacy/delete`
(Paramètres → Confidentialité).

> Les réponses sont affichées en **Markdown** (titres, listes, gras, tableaux, code)
> et les liens sont **cliquables**. Le HTML produit est systématiquement assaini
> (DOMPurify) avant affichage : la réponse d'un modèle, surtout nourrie par la
> recherche web, n'est pas du contenu de confiance. Les balises qui déclencheraient
> une requête réseau (`img`, `iframe`, `video`…) sont retirées, en cohérence avec
> la CSP du backend qui n'autorise déjà que les ressources locales.

## 📂 Choisir son dossier de travail

Dans l'onglet **📁 Documents** :
- une **liste déroulante** en haut bascule entre les dossiers configurés ;
- le bouton **« 📂 Parcourir… »** ouvre une fenêtre qui part des lecteurs de la
  machine, descend dans l'arborescence et permet d'**ajouter** le dossier courant
  comme dossier de travail — ou d'en **retirer** un.

Disponible **en mode simple** : plus besoin de taper les chemins à la main dans
les réglages avancés.

> 🔒 Deux routes servent uniquement à ce parcours : `GET /api/fs/drives` et
> `GET /api/fs/browse`. Elles **sortent volontairement du sandbox** — c'est le seul
> moyen de désigner un dossier qui n'est pas encore autorisé — mais elles ne
> renvoient **que des noms de dossiers** : jamais de fichier, jamais de contenu,
> et sans récursion. Tout le reste (`/api/fs/list`, `read`, `preview`, `download`,
> `upload`) reste strictement borné aux dossiers configurés par `safe_path()`.

## 🔎 Retrouver une information dans ses documents

Onglet **📁 Documents**, champ de recherche. On écrit **simplement les mots à
retrouver** — ni regex, ni casse, ni accents à respecter : « eleve » trouve « élève ».

La recherche lit **à l'intérieur** des fichiers : Word (y compris le contenu des
tableaux), Excel (toutes les feuilles), PDF, CSV et texte. Les résultats sont groupés
par document avec des extraits, et chacun peut être **ajouté à la conversation** —
plusieurs à la fois. Olivia s'appuie alors dessus et précise de quel document vient
chaque information.

Le contexte d'un modèle local étant limité, ce qui est transmis est borné (8 000
caractères pour un document seul, 24 000 au total, 10 documents au maximum). **Toute
coupe est signalée** dans le bandeau par une mention « ⚠️ tronqué » : Olivia ne doit
jamais répondre sur un extrait partiel sans que cela se voie.

Un dossier volumineux est exploré dans des limites de temps et de nombre de fichiers ;
quand elles se déclenchent, l'interface indique que le résultat est partiel.

### 🔍 Documents scannés — reconnaissance de caractères (OCR)

Un PDF passé au scanner ou reçu par fax est fait d'**images** : il n'y a aucun texte
à extraire, et sans OCR le document resterait introuvable. Olivia détecte ces
documents et les fait lire par **Tesseract**, en local, en français.

Concerne les PDF sans couche texte et les images (`.png`, `.jpg`, `.tif`…). Un PDF
qui contient déjà du texte n'est **jamais** envoyé à l'OCR : ce serait payer plusieurs
secondes pour rien.

- **Traitement local**, en sous-processus : aucune donnée ne sort de la machine.
- **Résultat mis en cache** sur disque (`(chemin, mtime, taille)`) : compter environ
  1,5 s par page à la première lecture, puis quasi instantané.
- **Bornes** : 8 pages par document, 20 s, 2 reconnaissances simultanées. Un PDF de
  300 pages ne bloquera pas une recherche ; quand une borne coupe, c'est signalé.
- Les résultats issus de l'OCR sont **marqués dans l'interface** — une transcription
  automatique n'est jamais fiable à 100 %, et il faut le savoir avant de recopier une
  date ou un numéro de circulaire dans un courrier officiel.

Réglages dans **Paramètres → Documents** : activation, état du moteur, et chemin
d'un Tesseract installé ailleurs.

**Installation du moteur** — il n'est pas fourni par `pip` :

```powershell
# Build Windows de référence : https://github.com/UB-Mannheim/tesseract
# Installer, puis copier dans le projet le binaire, ses DLL et tessdata\ :
#   D:\Olivia\tesseract\tesseract.exe
#   D:\Olivia\tesseract\tessdata\fra.traineddata
```

Le français (`fra.traineddata`, ~14 Mo) vient du dépôt officiel
`tesseract-ocr/tessdata` : l'installation par défaut ne pose que l'anglais.
Le dossier `tesseract/` (~190 Mo) est **ignoré par Git**, et
`deploy-portable.ps1` le copie sur le disque portable comme il le fait pour Ollama.

> **Sans moteur installé, rien ne casse** : les documents scannés restent
> consultables à l'écran, ils ne sortent simplement pas dans les recherches, et
> Paramètres → Documents l'indique clairement.
>
> ⚠️ **Limites réelles** : un document manuscrit, une page très inclinée ou une
> photocopie de mauvaise qualité donneront un texte partiel ou faux. L'OCR aide à
> *retrouver* un document, il ne remplace pas sa lecture.

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
| **Obsidian / Notion** | 🟡 Squelette | Chemin du coffre / token |

### Google Drive, OneDrive : pas de connecteur, et c'est voulu

Ces deux services **se synchronisent déjà dans un dossier local** du poste. Il suffit
de désigner ce dossier via **Documents → Parcourir** : Olivia y accède comme à
n'importe quel dossier de travail. Aucune autorisation à demander, rien à configurer.

C'est aussi ce qui évite deux impasses réelles :

- **Google** — lire les mails est un *scope restreint*. Hors application vérifiée, les
  jetons expirent **tous les 7 jours** : l'utilisatrice devrait se reconnecter chaque
  semaine. La vérification impose un audit de sécurité payant.
- **Microsoft** — Graph est techniquement plus simple, mais dans un lycée le tenant
  appartient à l'académie : le **consentement d'un administrateur** est requis.

Pour le courrier, **IMAP** est le connecteur réellement opérationnel, et il est accepté
par la plupart des messageries académiques (avec un mot de passe d'application).

### Connecteurs retirés

Les squelettes **OAuth Gmail/Outlook**, **École Directe** et **Service-Public /
FranceConnect** ont été supprimés de l'interface et du code. Visibles dans les
réglages, ils laissaient croire à des fonctionnalités disponibles alors qu'aucun
appel réel n'existait derrière. École Directe n'expose d'ailleurs pas d'API publique
officielle, et FranceConnect exige une habilitation partenaire délivrée par l'État.

Les clés correspondantes qui subsisteraient dans un `settings.json` existant sont
simplement ignorées : la fusion des paramètres n'efface rien.

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
- **Comptes et sessions** — écran de connexion dans l'interface (voir
  [🔐 Comptes et organisations](#-comptes-et-organisations)) : `POST /api/auth/login` ouvre une
  session (cookie `olivia_session`, `HttpOnly`, `SameSite=Lax`, 8 h) ; `POST /api/auth/logout` la
  ferme ; `GET /api/auth/me` renvoie le compte et l'organisation connectés, et sert à l'interface
  à savoir si elle doit afficher l'écran de connexion. Les comptes se créent avec
  `python backend/manage_users.py` (mots de passe dérivés en PBKDF2-HMAC-SHA256 salé, jamais
  stockés en clair). Remplace l'ancien jeton statique partagé `API_TOKEN` / `X-API-Token`, qui
  n'identifiait personne.
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
| **SearXNG** | Docker — voir ci-dessous | Élevée, et 100 % auto-hébergé |
| **Brave Search** | Une clé d'API, collée dans **Paramètres → Recherche web** | Élevée, **sans Docker** |
| **DuckDuckGo** | Aucun | Moyenne (scraping HTML, bloqué après quelques requêtes rapprochées) |

### Mode « sources officielles »

**Paramètres → Recherche web → « Privilégier les sites officiels »** (désactivé par
défaut) restreint la recherche aux domaines de l'administration française :
`education.gouv.fr`, `eduscol.education.fr`, `legifrance.gouv.fr`, `service-public.fr`,
`gouv.fr`, `onisep.fr`.

Utile pour les questions de règle ou de procédure, où une réponse fondée sur un forum
ou un site commercial est pire que pas de réponse.

Le mécanisme repose sur **deux barrières**, et la seconde est la vraie garantie :

1. la requête envoyée au moteur est complétée d'une restriction `site:` ;
2. les résultats reçus sont **refiltrés par domaine** — rien ne garantit qu'un moteur
   honore `site:`, et le filtre rejette aussi les domaines sosies du type
   `education.gouv.fr.exemple.com`.

La demande est volontairement élargie avant filtrage : sans cela, sur 5 résultats
demandés il n'en resterait qu'un ou deux après tri.

**Aucun repli silencieux** : si aucune source officielle ne répond, Olivia renvoie une
liste vide et le dit, plutôt que de proposer un lien non officiel. En contrepartie, une
question hors du champ administratif remonte des liens officiels mais hors sujet — le
modèle est instruit de signaler que les résultats ne permettent pas de répondre.

### Repli automatique entre moteurs

Le moteur choisi est essayé en premier ; s'il est injoignable ou ne renvoie rien,
Olivia **bascule automatiquement** sur les autres moteurs disponibles jusqu'à obtenir
une réponse. C'est ce qui permet à la recherche de fonctionner sur une machine sans
Docker, même si SearXNG est sélectionné.

Le repli reste **visible** : la réponse de `POST /api/search` indique dans `provider`
le moteur qui a *réellement* répondu, pas celui demandé. C'est important côté vie
privée — un repli envoie la requête à un autre moteur que celui configuré.

Une requête qui n'a simplement aucun résultat n'est pas traitée comme une panne :
Olivia répond alors sans le web et le dit, au lieu d'annoncer une erreur.

> **Clé Brave** : le palier gratuit est annoncé autour de 2 000 requêtes/mois et
> demande la création d'un compte sur `brave.com/search/api`. La clé se colle dans
> **Paramètres → Recherche web** ; elle est stockée dans `backend/settings.json`
> (fichier ignoré par Git) et n'est **jamais renvoyée en clair** à l'interface —
> elle s'affiche masquée, comme les mots de passe des connecteurs.
> La variable d'environnement `BRAVE_API_KEY` reste acceptée en repli.

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

`mistral-nemo:12b-instruct-2407-q4_K_M` (~7,5 Go, quantification Q4_K_M) est le seul
modèle GPU retenu (voir [🎮 CPU / GPU et modèles](#-cpu--gpu-et-modèles)). En dessous de
~8 Go de VRAM détectés, `backend/hardware.py` bascule automatiquement sur `gemma2:2b`
(CPU, ~1,6 Go) au premier lancement d'une organisation.

## 📁 Arborescence

```
ai-webapp/
├── README.md
├── launch.py              ← lanceur multi-OS (dev) + point d'entrée .exe (mode gelé)
├── build.spec             ← config PyInstaller (embarque backend + frontend/dist)
├── deploy-portable.ps1    ← build + synchro vers un disque portable (préserve modèles et données)
├── portable/              ← lanceur .bat et notice copiés sur le disque portable
├── .gitignore
├── backend/
│   ├── main.py            ← FastAPI : auth + chat + fs + upload/download/preview + settings + search + connectors + RGPD
│   ├── settings.py        ← persistance JSON par organisation + CPU/GPU + modèle par périphérique
│   ├── hardware.py        ← détection VRAM (nvidia-smi) pour le choix GPU/CPU par défaut
│   ├── profiles.py        ← registre des organisations, cloisonnement par dossier
│   ├── users.py           ← comptes (mots de passe PBKDF2-HMAC-SHA256 salés)
│   ├── sessions.py        ← sessions par cookie (jetons opaques, TTL 8 h)
│   ├── manage_users.py    ← CLI de provisionnement (organisations + comptes)
│   ├── conversations.py   ← historique par organisation : un JSON par conversation, écriture atomique
│   ├── search.py          ← recherche web pluggable + cascade de repli entre moteurs
│   ├── documents.py       ← prévisualisation + extraction de texte (docx/xlsx/pdf/csv)
│   ├── docsearch.py       ← recherche en langage courant dans les documents
│   ├── docindex.py        ← index sémantique FAISS (embeddings bge-m3 via Ollama)
│   ├── ocr.py             ← reconnaissance de caractères (documents scannés)
│   ├── connectors/
│   │   ├── __init__.py
│   │   ├── imap_client.py      ← IMAP + comptage des non-lus
│   │   └── oauth_providers.py  ← lecteur de calendrier .ics
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── package.json, vite.config.js, index.html
    └── src/
        ├── main.js, App.vue, style.css
        ├── stores/ (chat.js, settings.js, auth.js)
        └── components/
            ├── LoginView.vue        ← écran de connexion (pas d'inscription)
            ├── ModelPicker.vue      ← sélecteur device-aware
            ├── FileExplorer.vue     ← arbre + upload + recherche + sélecteur de dossier
            ├── FolderPickerModal.vue ← parcours des lecteurs pour ajouter un dossier
            ├── FilePreview.vue      ← aperçu multi-format
            ├── ChatPanel.vue
            ├── ConversationList.vue ← historique : ouvrir / renommer / supprimer
            ├── MessageBubble.vue    ← rendu Markdown assaini + liens cliquables
            ├── ConnectedTools.vue   ← barre des outils connectés + notif mail
            ├── ConsentBanner.vue    ← bandeau RGPD
            └── SettingsMenu.vue     ← 4 onglets (Raisonnement / Recherche / Connexions / Confidentialité)
```
