"""
Détection du matériel au premier lancement, pour choisir un périphérique de
calcul (`compute_device`) par défaut raisonnable sans aucune action de
l'utilisatrice.

Contexte : le défaut codé en dur ("gpu") s'appliquait à toute nouvelle
installation, y compris sur un poste sans carte graphique dédiée — un retour de
terrain a montré `mistral-nemo` (le modèle GPU) prendre jusqu'à 45 minutes sur
un portable 4 Go de RAM / i5 sans GPU, un temps de réponse inutilisable. Mieux
vaut détecter et proposer "cpu" par défaut dans ce cas, quitte à ce que
l'utilisatrice bascule elle-même sur ⚡ Rapide (GPU) si le poste le permet.
"""
import subprocess

# Cible du projet : RTX 5060 8 Go (voir README). Une carte "8 Go" annoncée
# rapporte souvent un peu moins que 8192 Mio de VRAM nominale (mémoire réservée
# par le pilote, l'OS, etc.) — seuil fixé à 7000 Mio pour ne pas rejeter une
# carte réellement 8 Go à cause de cet arrondi, tout en excluant les cartes
# d'entrée de gamme (4 Go) manifestement insuffisantes pour mistral-nemo.
SEUIL_VRAM_MIO = 7000

# Le sous-processus interroge le pilote NVIDIA, qui peut être lent à répondre
# (ou ne jamais répondre) sur un poste chargé ou mal configuré — un timeout
# court évite qu'un premier lancement reste bloqué dessus.
TIMEOUT_SECONDES = 3


def detect_default_device() -> str:
    """"gpu" si une carte NVIDIA avec au moins ~8 Go de VRAM est détectée,
    "cpu" sinon.

    Aucune dépendance ajoutée (pas de psutil, pas de GPUtil) : on interroge
    directement `nvidia-smi`, présent avec tout pilote NVIDIA récent, cohérent
    avec la politique de dépendances minimales déjà appliquée ailleurs (voir le
    commentaire sur PBKDF2 vs bcrypt dans backend/users.py).

    Toute erreur (binaire absent, timeout, sortie non parsable, aucune carte)
    renvoie silencieusement "cpu" : c'est le repli sûr — un CPU sous-utilisé
    vaut mieux qu'un GPU absent ou insuffisant qui plante ou traîne."""
    try:
        resultat = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=TIMEOUT_SECONDES, check=True,
        )
        # Plusieurs lignes si plusieurs GPU : on retient le maximum, une seule
        # carte capable suffisant à Ollama pour y charger le modèle GPU.
        vram_mio = max(
            int(ligne.strip())
            for ligne in resultat.stdout.splitlines()
            if ligne.strip()
        )
    except Exception:
        # FileNotFoundError (pas de pilote NVIDIA), TimeoutExpired,
        # CalledProcessError, ValueError (sortie non numérique), ou une sortie
        # vide (max() sur un générateur vide lève ValueError) : dans tous les
        # cas, repli silencieux sur "cpu".
        return "cpu"
    return "gpu" if vram_mio >= SEUIL_VRAM_MIO else "cpu"
