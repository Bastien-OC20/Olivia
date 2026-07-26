"""
Connecteurs « outils métier » — scaffold honnête.

⚠️ Réalité technique :
  - École Directe n'expose PAS d'API publique officielle. Les intégrations
    existantes reposent sur une API interne non documentée et non garantie.
    Ce connecteur est donc un squelette : il valide la configuration et renvoie
    un statut clair, sans prétendre à une connexion fonctionnelle.
  - Service-Public / gouv.fr via FranceConnect nécessite un enregistrement
    partenaire officiel (habilitation, client_id/secret délivrés par l'État).
    Idem : squelette prêt à brancher, pas d'appel réel.

Aucun secret n'est codé en dur ; la configuration vient de l'UI Paramètres.
"""


def ecole_directe_status(cfg: dict) -> dict:
    if not cfg.get("enabled"):
        return {"id": "ecole_directe", "label": "École Directe",
                "enabled": False, "status": "idle"}
    ready = bool(cfg.get("username") and cfg.get("password"))
    return {
        "id": "ecole_directe",
        "label": "École Directe",
        "enabled": True,
        "status": "scaffold" if ready else "misconfigured",
        "detail": ("Identifiants saisis. Intégration à brancher : l'API École Directe "
                   "est non officielle et doit être implémentée côté utilisateur."
                   if ready else "Renseignez identifiant et mot de passe."),
    }


def service_public_status(cfg: dict) -> dict:
    if not cfg.get("enabled"):
        return {"id": "service_public", "label": cfg.get("label", "Service-Public / gouv.fr"),
                "enabled": False, "status": "idle"}
    return {
        "id": "service_public",
        "label": cfg.get("label", "Service-Public / gouv.fr"),
        "enabled": True,
        "status": "scaffold",
        "detail": ("FranceConnect requiert un enregistrement partenaire officiel "
                   "(client_id/secret délivrés par l'État). Squelette prêt à brancher."),
    }
