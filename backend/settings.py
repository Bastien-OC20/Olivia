"""
Persistance des paramètres, UNE INSTANCE PAR ORGANISATION.

Chaque profil (organisation) a son propre fichier
backend/profiles/<profile_id>/settings.json, créé automatiquement au premier
enregistrement avec les valeurs par défaut. Toutes les écritures sont mutexées et
atomic-write sur disque.

Le cloisonnement passe par le DOSSIER et non par un champ `profile_id` mêlé à des
réglages communs : `fs_roots`, les identifiants de connecteurs (IMAP…) et la clé
d'API du moteur de recherche vivent dans ce fichier, et une fuite d'une
organisation vers une autre devient structurellement impossible plutôt que
simplement filtrée.

On n'accède donc plus à un singleton mais au registre (`reglages(profile_id)`),
alimenté par `main.get_current_profile()` — jamais par un identifiant fourni par
le client.
"""
import json
from pathlib import Path
from threading import RLock

from . import hardware, profiles

# Modèles recommandés selon le périphérique de calcul.
#   gpu : cible RTX 5060 8 Go (voir README) — modèle quantifié Q4_K_M
#   cpu : petit modèle qui reste fluide sans carte graphique
#
# UN SEUL modèle par périphérique, décision du 29/07/2026 : Olivia vise des
# collectivités, associations et PME qui n'ont pas de compétence technique en
# interne — une liste de choix, aussi « recommandée » soit-elle, est un risque
# (un mauvais choix silencieux) et une charge de test qui grandit avec chaque
# modèle ajouté. Mieux vaut UN modèle par profil, éprouvé sur le cas d'usage
# réel, que plusieurs options non toutes vérifiées avec la même rigueur.
#
# Choix arbitrés sur mesure, pas sur réputation — consigne : « rédige le corps
# d'une convocation au conseil de classe », prompt système d'Olivia inchangé
# (dont `reasoning_style="detailed"` + `tone="teacher"`, le réglage le plus
# exigeant testé, qui a justement révélé la plupart des échecs ci-dessous).
#
# GPU : Mistral Nemo (12B, Mistral AI + NVIDIA, Apache 2.0, conçu multilingue).
#   Français administratif juste (« Madame, Monsieur, … Nous vous prions de bien
#   vouloir »), sortie en PROSE PURE (pas de Markdown parasite), réponse
#   correcte et complète en 12 s même avec le réglage « détaillé ». Alternatives
#   écartées : `qwen3:8b` ajoute un méta-titre et des `**gras**` Markdown qui
#   atterrissent tels quels dans le document Word produit ; `mistral:7b`
#   (instruct) bascule en anglais en cours de document, ou part carrément hors
#   sujet (voir CPU ci-dessous, même modèle) — un courrier bilingue ou erroné
#   partirait aux familles sans que personne ne le remarque.
#
# CPU : `gemma2:2b` (Google, Apache 2.0). Un 12B y serait inutilisable
#   (plusieurs minutes par réponse). Seul candidat, sur SIX testés le
#   29/07/2026 sur le même prompt en CPU forcé, à produire une vraie réponse
#   correcte : le plus rapide (≈ 15 tokens/s) ET le seul dont le fond soit
#   juste. Recalé :
#   - `qwen3:4b` / `qwen3:1.7b` : boucle de méta-réflexion SANS FIN, EN
#     ANGLAIS (« Okay, the user wants me to draft... »), reproduit avec et
#     sans `think:false` — jamais de réponse produite. Cause probable d'un
#     plantage machine constaté en test (15+ min à pleine charge CPU).
#   - `phi4-mini:3.8b` et `gemma2:9b` : répondent en français mais hors sujet
#     — rédigent un TUTORIEL (« voici comment structurer... ») au lieu de la
#     convocation elle-même. `gemma2:9b` est en plus 3× plus lent que `2b`.
#   - `mistral:7b-instruct` : confond totalement le sujet (rédige un compte
#     rendu de cours d'histoire-géo au lieu d'une convocation aux parents),
#     et le plus lent de tous les candidats testés (≈ 6 tokens/s).
#   - `llama3.2:3b` : répond sur le bon sujet mais s'adresse aux « élèves »
#     au lieu des parents, avec une faute de code-switching anglais
#     (« Je vous addressed »).
#   Retester si un meilleur candidat apparaît — même protocole obligatoire :
#   `num_gpu: 0`, `num_predict` plafonné, même prompt de référence.
DEVICE_MODELS = {
    "gpu": ["mistral-nemo:12b-instruct-2407-q4_K_M"],
    "cpu": ["gemma2:2b"],
}

DEFAULTS = {
    "system_prompt": "Tu es un assistant IA local. Réponds en français, clair et structuré.",
    "temperature": 0.7,
    "reasoning_style": "balanced",
    "tone": "neutral",
    "compute_device": "gpu",          # "gpu" | "cpu"
    "device_models": DEVICE_MODELS,
    "simple_mode": True,              # UI épurée par défaut (utilisatrice non technique)
    "search_provider": "duckduckgo",
    "searxng_url": "http://localhost:8888",
    # Restreint la recherche web aux domaines officiels français (voir
    # OFFICIAL_DOMAINS dans search.py). Désactivé par défaut : c'est un mode
    # volontairement plus restrictif, pas le comportement standard.
    "search_official_only": False,
    # Vide = repli sur la variable d'env BRAVE_API_KEY (compatibilité).
    "search_brave_api_key": "",
    # Reconnaissance de caractères (OCR) sur les documents scannés et les images.
    # Activée par défaut : désactivée, la fonction serait invisible pour une
    # utilisatrice non technique, qui n'irait jamais la chercher dans les
    # réglages — et un PDF scanné resterait introuvable sans qu'elle sache
    # pourquoi. Le coût est borné (8 pages par document, 20 s, 2 traitements
    # simultanés au plus), il n'est payé QUE sur les documents sans couche
    # texte, le résultat est mis en cache sur disque, et si le moteur n'est pas
    # installé tout se comporte exactement comme avant.
    "ocr_enabled": True,
    # Chemin d'un Tesseract installé ailleurs. Vide = moteur portable livré dans
    # le dossier tesseract/ de l'application, sinon celui trouvé dans le PATH.
    "ocr_tesseract_path": "",
    # Modèle Word portant l'identité de l'établissement (logo, en-tête, styles),
    # utilisé pour produire circulaires, courriers, convocations et comptes rendus.
    # Vide = modeles/modele-etablissement.docx, à côté de l'application. Ce modèle
    # se fabrique depuis un vrai document (voir backend/docmodele.py) : il n'est ni
    # versionné ni embarqué dans l'.exe, le logo appartenant au lycée. S'il manque,
    # les documents sont tout de même produits, sans l'en-tête, avec un avertissement.
    "docgen_template_path": "",
    # Formules d'usage des documents produits (appel, politesse, lieu, signature).
    # Vide = repli sur les valeurs par défaut de backend/docgen.py (TEXTES) : un
    # établissement scolaire générique, mais pas forcément celui du lycée de
    # l'utilisatrice. Exposées ici précisément pour qu'elle les corrige sans
    # toucher au code — c'est la raison d'être de ces réglages.
    "docgen_appel": "",
    "docgen_formule_politesse": "",
    "docgen_lieu": "",
    "docgen_signature": "",
    # Liste vide = utiliser le défaut (variable d'env FS_ROOT, sinon ~/Documents).
    # Ne pas pré-remplir : une liste non vide prendrait le pas sur l'env.
    "fs_roots": [],
    "privacy_consent": False,          # RGPD : consentement au stockage local
    "connectors": {
        # Uniquement des connecteurs qui fonctionnent réellement. Les squelettes
        # (OAuth Gmail/Outlook, École Directe, Service-Public) ont été retirés.
        # Les clés correspondantes qui traîneraient dans un settings.json existant
        # sont simplement conservées et ignorées : _merge n'efface rien.
        "imap": {"enabled": False, "label": "Boîte pro", "host": "", "user": "",
                 "password": "", "folder": "INBOX"},
        "calendar_ics": {"enabled": False, "path": ""},
        "obsidian": {"enabled": False, "vault_path": ""},
        "notion": {"enabled": False, "api_token": ""},
    },
}


def _deep_default() -> dict:
    return json.loads(json.dumps(DEFAULTS))


def _merge(base: dict, patch: dict) -> dict:
    """Fusion récursive : les dicts imbriqués sont fusionnés clé à clé."""
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _merge(base[k], v)
        else:
            base[k] = v
    return base


class Settings:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self._data = self._load()

    def _load(self) -> dict:
        merged = _deep_default()
        if not self.path.exists():
            # Tout premier lancement de cette organisation (jamais configurée) :
            # on choisit un "compute_device" adapté au poste plutôt que le "gpu"
            # codé en dur ci-dessus, qui a rendu Olivia inutilisable (45 min de
            # réponse) sur un poste sans carte graphique dédiée. Ne s'applique
            # qu'ici : un réglage déjà enregistré, même s'il vaut "gpu" à tort,
            # a pu être choisi consciemment depuis (bouton ⚡/🧩 de la topbar) et
            # ne doit jamais être corrigé sous le pied de l'utilisatrice.
            merged["compute_device"] = hardware.detect_default_device()
            return merged
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
        except Exception:
            return merged
        result = _merge(merged, saved)
        result["device_models"] = _deep_default()["device_models"]
        return result

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2, ensure_ascii=False)
        tmp.replace(self.path)

    def get(self) -> dict:
        with self._lock:
            return json.loads(json.dumps(self._data))  # deep copy

    def update(self, patch: dict) -> dict:
        with self._lock:
            # device_models est calculé par le code (DEVICE_MODELS ci-dessus), pas
            # un choix utilisateur. Le front-end le renvoie pourtant tel quel à
            # chaque "Enregistrer" (il fait partie de son état local) : sans ce
            # filtre, la liste se fige à la version du bundle chargé au moment de
            # la sauvegarde, et un changement de modèle recommandé (ex. Mistral
            # Nemo) ne prend alors plus jamais effet sur une installation existante.
            patch.pop("device_models", None)
            _merge(self._data, patch)
            self._data["device_models"] = _deep_default()["device_models"]
            self._save()
            return self.get()

    def reset(self) -> dict:
        """RGPD : réinitialise tous les paramètres aux valeurs par défaut."""
        with self._lock:
            self._data = _deep_default()
            self._save()
            return self.get()


NOM_FICHIER = "settings.json"

# Fichier du temps où Olivia était mono-organisation (backend/settings.json).
# Il n'est plus ni lu ni écrit : la constante ne subsiste que pour documenter
# l'emplacement des réglages hérités. Leur migration vers un profil est une
# décision d'exploitation (quelle organisation en hérite ?), pas un effet de bord
# du démarrage — voir le rapport de la Phase 1.
SETTINGS_PATH_HERITE = Path(__file__).parent / NOM_FICHIER


class SettingsRegistry:
    """Une instance `Settings` par organisation, mise en cache.

    Pourquoi un cache : `Settings` lit son fichier une fois et garde l'état en
    mémoire ; en recréer une par requête relirait le disque à chaque `get()`,
    plusieurs fois par affichage de l'interface.

    Pourquoi ce cache reste cohérent : il n'existe qu'UNE instance par profil dans
    tout le process, donc deux requêtes concurrentes d'une même organisation
    passent par le même RLock interne à `Settings` — leurs écritures se
    sérialisent au lieu de s'écraser. C'est précisément ce qu'un cache par requête
    (ou pas de cache du tout) ne garantirait pas.
    """

    def __init__(self):
        # Protège uniquement le dictionnaire d'instances ; l'état de chaque
        # profil est protégé par le verrou de son propre objet `Settings`.
        self._lock = RLock()
        self._instances: dict[str, Settings] = {}

    def for_profile(self, profile_id: str) -> Settings:
        """Réglages d'une organisation. Lève ValueError si l'identifiant est invalide."""
        chemin = profiles.profile_dir(profile_id) / NOM_FICHIER   # valide l'identifiant
        with self._lock:
            instance = self._instances.get(profile_id)
            if instance is None:
                instance = Settings(chemin)
                self._instances[profile_id] = instance
            return instance


registry = SettingsRegistry()


def reglages(profile_id: str) -> Settings:
    """Réglages d'une organisation (raccourci sur le registre)."""
    return registry.for_profile(profile_id)


def reglages_lus(profile_id: str) -> dict:
    """Réglages en LECTURE de l'organisation, avec repli sur les valeurs par défaut
    quand aucun profil n'est fourni.

    Sert aux appels faits hors d'une requête HTTP (ligne de commande de
    backend/docmodele.py) : un identifiant vide ou invalide y rend les défauts au
    lieu de lever — mais jamais, en aucun cas, les réglages d'une autre
    organisation.
    """
    if not profiles.is_valid_id(profile_id or ""):
        return _deep_default()
    return registry.for_profile(profile_id).get()


def style_directives(style: str, tone: str) -> str:
    """Produit la portion dynamique du prompt système selon les choix UI."""
    fragments = []
    if style == "concise":
        fragments.append("Sois concis : réponses courtes, va à l'essentiel.")
    elif style == "detailed":
        # « mentionne tes sources de raisonnement » a été retiré le 02/08/2026 :
        # sans document ni résultat de recherche fourni, le modèle obéissait à la
        # lettre et fabriquait des références plausibles (textes officiels et
        # sigles inexistants) en fin de document. On garde le bénéfice — le pas à
        # pas — en demandant le cheminement du raisonnement, pas ses « sources ».
        fragments.append("Sois détaillé : explique pas à pas, "
                         "justifie chaque point par le raisonnement qui y mène.")
    elif style == "creative":
        fragments.append("Sois créatif : propose des idées originales, varie ton vocabulaire.")
    elif style == "analytical":
        fragments.append("Raisonne de façon analytique : POURQUOI → ÉTAPES → CONSÉQUENCES.")
    else:
        fragments.append("Sois équilibré : ni trop bref ni trop long.")

    if tone == "friendly":
        fragments.append("Ton chaleureux, vouvoiement léger, tutoie si pertinent.")
    elif tone == "formal":
        fragments.append("Ton formel et professionnel, vouvoiement strict.")
    elif tone == "teacher":
        fragments.append("Ton pédagogue : vulgarise, donne des analogies, pars du connu.")
    else:
        fragments.append("Ton neutre, factuel.")

    return " ".join(fragments)
