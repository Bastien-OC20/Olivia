"""
Temporisation des échecs de connexion.

Sans elle, rien n'empêchait d'essayer des milliers de mots de passe à la suite
sur un identifiant. Règles retenues, d'après le cas « mot de passe + restriction
d'accès » de la recommandation CNIL n° 2022-100 du 21 juillet 2022 (associé à la
politique de mot de passe de users.py) :
  - à partir du 3e échec consécutif, attente qui DOUBLE à chaque nouvel échec :
    20 s, 40 s, 80 s (plus d'une minute au 5e échec), 160 s… plafonnée à 1 h ;
  - au plus 25 échecs sur 24 heures glissantes ; au-delà, l'identifiant reste
    bloqué jusqu'à ce que les plus anciens sortent de la fenêtre ;
  - pendant une attente, même le BON mot de passe est refusé — sinon
    l'attente ne protégerait rien ;
  - une connexion réussie remet le compteur d'échecs consécutifs à zéro.

Le compteur porte sur l'IDENTIFIANT tapé, qu'il existe ou non : un identifiant
inconnu se bloque exactement comme un vrai, la temporisation ne révèle donc pas
quels comptes existent. Pas de compteur par adresse IP : Olivia n'écoute que sur
127.0.0.1, tous les postes clients auraient la même.

Persisté sur disque (profiles/tentatives.json, à côté des sessions) : un
redémarrage du service ne remet pas les compteurs à zéro. L'identifiant y est
stocké HACHÉ — une utilisatrice qui tape par erreur son mot de passe dans le
champ identifiant ne doit pas le retrouver écrit en clair dans un fichier.
"""
import hashlib
import time

from . import profiles

SEUIL_TEMPORISATION = 3          # échecs consécutifs avant la première attente
ATTENTE_INITIALE = 20            # secondes, au 3e échec
ATTENTE_MAX = 3600               # plafond de l'attente exponentielle
FENETRE = 24 * 3600              # fenêtre glissante du plafond quotidien
MAX_ECHECS_FENETRE = 25


def _chemin():
    # Calculé à chaque appel (et non au chargement) : suit PROFILES_DIR, y
    # compris quand les tests le redirigent vers un dossier temporaire.
    return profiles.PROFILES_DIR / "tentatives.json"


def _cle(username: str) -> str:
    return hashlib.sha256((username or "").strip().casefold().encode("utf-8")).hexdigest()


def _lire() -> dict:
    try:
        return profiles.read_store(_chemin(), "tentatives", vide={})
    except RuntimeError:
        # Fichier abîmé : on repart de zéro plutôt que d'empêcher toute connexion.
        return {"tentatives": {}}


def _attente_apres(consecutifs: int) -> float:
    if consecutifs < SEUIL_TEMPORISATION:
        return 0.0
    return float(min(ATTENTE_MAX, ATTENTE_INITIALE * 2 ** (consecutifs - SEUIL_TEMPORISATION)))


def attente_restante(username: str, maintenant: float | None = None) -> float:
    """Secondes à attendre avant de pouvoir retenter cet identifiant (0 = libre)."""
    maintenant = time.time() if maintenant is None else maintenant
    with profiles.store_lock:
        etat = _lire()["tentatives"].get(_cle(username))
    if not isinstance(etat, dict):
        return 0.0
    echecs = [t for t in etat.get("echecs", []) if maintenant - t < FENETRE]
    if not echecs:
        return 0.0
    restants = []
    if len(echecs) >= MAX_ECHECS_FENETRE:
        restants.append(min(echecs) + FENETRE - maintenant)
    attente = _attente_apres(int(etat.get("consecutifs", 0)))
    if attente:
        restants.append(max(echecs) + attente - maintenant)
    return max([0.0, *restants])


def noter_echec(username: str, maintenant: float | None = None) -> None:
    maintenant = time.time() if maintenant is None else maintenant
    with profiles.store_lock:
        data = _lire()
        table = data["tentatives"]
        # Ménage : identifiants dont aucun échec n'est plus dans la fenêtre.
        for cle in [c for c, e in table.items()
                    if not isinstance(e, dict)
                    or all(maintenant - t >= FENETRE for t in e.get("echecs", []))]:
            del table[cle]
        etat = table.setdefault(_cle(username), {"echecs": [], "consecutifs": 0})
        etat["echecs"] = [t for t in etat["echecs"] if maintenant - t < FENETRE]
        etat["echecs"].append(maintenant)
        etat["consecutifs"] = int(etat.get("consecutifs", 0)) + 1
        profiles.write_store(_chemin(), data)


def noter_succes(username: str) -> None:
    """Connexion réussie : fin de la série d'échecs consécutifs.

    Les échecs restent comptés dans le plafond des 24 heures : réussir une fois
    ne doit pas ouvrir droit à 25 nouveaux essais aussitôt.
    """
    with profiles.store_lock:
        data = _lire()
        etat = data["tentatives"].get(_cle(username))
        if isinstance(etat, dict) and etat.get("consecutifs"):
            etat["consecutifs"] = 0
            profiles.write_store(_chemin(), data)


def formater_attente(secondes: float) -> str:
    """« 40 secondes », « 3 minutes », « 2 heures » — pour le message d'erreur."""
    s = max(1, int(secondes + 0.999))
    if s < 60:
        return f"{s} seconde{'s' if s > 1 else ''}"
    m = (s + 59) // 60
    if m < 60:
        return f"{m} minute{'s' if m > 1 else ''}"
    h = (m + 59) // 60
    return f"{h} heure{'s' if h > 1 else ''}"
