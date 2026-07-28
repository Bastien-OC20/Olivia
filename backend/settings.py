"""
Persistance des paramètres utilisateur dans backend/settings.json.

Le fichier est créé automatiquement au premier accès avec les valeurs par défaut.
Toutes les écritures sont mutexées et atomic-write sur disque.
"""
import json
from pathlib import Path
from threading import RLock

# Modèles recommandés selon le périphérique de calcul.
#   gpu : cible RTX 5060 8 Go (voir README) — modèles quantifiés Q4_K_M
#   cpu : petits modèles qui restent fluides sans carte graphique
#
# Choix arbitrés sur mesure, pas sur réputation — consigne : « rédige le corps
# d'une convocation au conseil de classe », prompt système d'Olivia inchangé.
#
# GPU : Mistral Nemo (12B, Mistral AI + NVIDIA, Apache 2.0, conçu multilingue).
#   Français administratif juste (« Madame, Monsieur, … Nous vous prions de bien
#   vouloir »), et surtout une sortie en PROSE PURE : qwen3:8b, aussi bon en
#   français, ajoute un méta-titre et des `**gras**` Markdown qui atterrissent
#   tels quels dans le document Word produit. 34 s contre 36 s, donc à égalité.
#
# Mistral 7B Instruct a été RETIRÉ des recommandations : même avec une consigne
#   impérative « écris exclusivement en français », il rédige en anglais, ou
#   bascule en anglais en cours de document. Un courrier officiel bilingue
#   partirait aux familles sans que personne ne le remarque. Il reste
#   sélectionnable s'il est installé, mais n'est plus proposé.
#
# CPU : un 12B y serait inutilisable (plusieurs minutes par réponse). qwen3:4b
#   garde la première place : français correct, aucun anglicisme constaté.
DEVICE_MODELS = {
    "gpu": ["mistral-nemo:12b-instruct-2407-q4_K_M", "qwen3:8b", "qwen2.5-coder:7b",
            "llama3.3:8b", "qwen2.5-vl:7b", "phi4-mini:3.8b"],
    "cpu": ["qwen3:4b", "qwen3:1.7b", "phi4-mini:3.8b", "gemma2:2b"],
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


SETTINGS_PATH = Path(__file__).parent / "settings.json"
settings = Settings(SETTINGS_PATH)


def style_directives(style: str, tone: str) -> str:
    """Produit la portion dynamique du prompt système selon les choix UI."""
    fragments = []
    if style == "concise":
        fragments.append("Sois concis : réponses courtes, va à l'essentiel.")
    elif style == "detailed":
        fragments.append("Sois détaillé : explique pas à pas, "
                         "mentionne tes sources de raisonnement.")
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
