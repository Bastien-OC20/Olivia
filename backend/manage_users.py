"""
Provisionnement en ligne de commande des organisations et des comptes.

Il n'y a volontairement pas d'interface graphique d'administration : comme les
connecteurs OAuth, ces réglages se préparent une fois par le service
informatique, pas par l'utilisatrice finale.

Trois façons de lancer ces commandes, qui écrivent toutes au bon endroit :
  - application installée ou disque portable (aucun Python requis) :
        ai-webapp.exe init                 (assistant guidé, voir `_cmd_init`)
        double-clic sur Creer-un-compte.bat (disque portable)
  - dépôt source, via le lanceur :
        python launch.py init
  - dépôt source, directement (depuis la RACINE du dépôt) :
        python backend/manage_users.py init
        python backend/manage_users.py create-profile "Mairie de Test"
        python backend/manage_users.py create-user marie <profile_id> [--role membre]
        python backend/manage_users.py list-profiles

Gestion des comptes existants (lot 4c), mêmes trois façons de lancer :
        list-users [--profil <profile_id>]   comptes, rôles, blocages
        change-password <identifiant>        ancien puis nouveau mot de passe
        reset-password <identifiant>         nouveau mot de passe sans l'ancien
        delete-user <identifiant>            suppression (confirmation demandée)
        unlock <identifiant>                 efface les échecs de connexion
        set-role <identifiant> responsable|membre

La ligne de commande est l'outil du SERVICE INFORMATIQUE, sur le poste et sous
le compte Windows qui détient les données : elle n'exige pas le mot de passe
d'un responsable (sauf `change-password`, qui demande l'ancien mot de passe du
compte, et `init`, accessible depuis le menu de l'application). Les garde-fous
restent ceux de l'interface : une organisation garde toujours un responsable.

Le mot de passe est DEMANDÉ au clavier, masqué, et jamais passé en argument :
un argument de ligne de commande reste dans l'historique du terminal et se lit
dans la liste des processus. L'ancienne forme `create-user <nom> <mot-de-passe>
<profil>` reste acceptée pour les scripts existants, avec un avertissement.
"""
import time
import argparse
import getpass
import sys
from pathlib import Path

# Lancé en script (et non en module), ce fichier n'a pas de paquet parent : les
# imports relatifs de profiles.py/users.py échoueraient. On rend donc la racine
# du dépôt importable pour retrouver `backend` comme paquet.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import profiles, sessions, tentatives, users  # noqa: E402

# Nombre d'essais laissés pour saisir deux fois le même mot de passe.
ESSAIS_MOT_DE_PASSE = 3
# Essais laissés pour confirmer par un compte existant (ajout à une organisation).
ESSAIS_CONFIRMATION = 3


class Abandon(Exception):
    """Saisie interrompue (Ctrl+C, fin d'entrée) ou essais épuisés."""


def _saisir(invite: str) -> str:
    """Ligne saisie au clavier, sans espaces de bord. Abandon sur Ctrl+C / EOF."""
    try:
        return input(invite).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise Abandon("saisie interrompue")


def _demander_mot_de_passe() -> str:
    """Mot de passe saisi deux fois, masqué. Lève Abandon après trop d'échecs.

    La politique de mot de passe (users.probleme_mot_de_passe) est vérifiée ici,
    avant la confirmation, pour ne pas faire retaper deux fois un mot de passe
    que `users.create_user` refuserait.
    """
    print(f"Mot de passe : au moins {users.PASSWORD_MIN_LEN} caractères, mêlant 3 types "
          "parmi minuscules, majuscules, chiffres et caractères spéciaux.")
    for _ in range(ESSAIS_MOT_DE_PASSE):
        try:
            mdp = getpass.getpass("Mot de passe (la saisie ne s'affiche pas) : ")
            probleme = users.probleme_mot_de_passe(mdp)
            if probleme:
                print(f"  {probleme}")
                continue
            if getpass.getpass("Retapez le mot de passe : ") != mdp:
                print("  Les deux saisies diffèrent, recommencez.")
                continue
        except (EOFError, KeyboardInterrupt):
            print()
            raise Abandon("saisie interrompue")
        return mdp
    raise Abandon("mot de passe non confirmé")


def _cmd_create_profile(args) -> int:
    profil = profiles.create_profile(args.name)
    print(f"Profil créé : {profil['name']}")
    print(f"  id : {profil['id']}")
    print("Créez maintenant un compte rattaché à ce profil :")
    print(f"  {args.prog} create-user <identifiant> {profil['id']}")
    return 0


def _cmd_create_user(args) -> int:
    # Deux formes acceptées :
    #   create-user <identifiant> <profile_id>                (mot de passe demandé)
    #   create-user <identifiant> <mot-de-passe> <profile_id> (ancienne forme)
    if args.troisieme is None:
        profile_id, mot_de_passe = args.deuxieme, None
    else:
        mot_de_passe, profile_id = args.deuxieme, args.troisieme
        print("Avertissement : un mot de passe passé en argument reste dans "
              "l'historique du terminal. Préférez :", file=sys.stderr)
        print(f"  {args.prog} create-user {args.username} {profile_id}", file=sys.stderr)
    # Profil vérifié AVANT la saisie : inutile de taper deux fois un mot de passe
    # pour un compte que create_user refusera.
    if profiles.get_profile(profile_id) is None:
        raise ValueError(f"Profil inconnu : {profile_id} (voir list-profiles)")
    if mot_de_passe is None:
        mot_de_passe = _demander_mot_de_passe()
    # --role absent : responsable si c'est le premier compte de l'organisation,
    # membre sinon (voir users.create_user).
    user = users.create_user(args.username, mot_de_passe, profile_id, role=args.role)
    profil = profiles.get_profile(user["profile_id"])
    print(f"Compte créé : {user['username']}")
    print(f"  id      : {user['id']}")
    print(f"  profil  : {profil['name'] if profil else user['profile_id']}")
    print(f"  rôle    : {user['role']}")
    return 0


def _cmd_list_profiles(args) -> int:
    tous = profiles.list_profiles()
    if not tous:
        print("Aucun profil. Créez-en un avec : create-profile \"Nom de l'organisation\"")
        return 0
    for p in tous:
        print(f"{p['id']}  {p.get('name', '')}")
    return 0


def _choisir_organisation() -> tuple[dict | None, str]:
    """(organisation existante, "") ou (None, nom de la nouvelle organisation).

    Une nouvelle organisation n'est PAS créée ici : elle ne l'est qu'une fois le
    compte entièrement saisi (voir `_cmd_init`). Abandonner en cours de route ne
    laisse donc aucune organisation vide derrière soi.
    """
    existantes = profiles.list_profiles()
    if existantes:
        print("Organisations déjà présentes sur ce poste :")
        for i, p in enumerate(existantes, start=1):
            print(f"  {i}. {p.get('name', '')}")
        print("  N. Nouvelle organisation")
        while True:
            choix = _saisir("Votre choix (numéro ou N) : ").lower()
            if choix == "n":
                break
            if choix.isdigit() and 1 <= int(choix) <= len(existantes):
                return existantes[int(choix) - 1], ""
            print("  Choix invalide.")
    while True:
        nom = _saisir("Nom de l'organisation (ex. Lycée de l'Olivier) : ")
        if not nom:
            print("  Le nom de l'organisation est obligatoire.")
        elif len(nom) > profiles.NAME_MAX_LEN:
            print(f"  Au plus {profiles.NAME_MAX_LEN} caractères.")
        else:
            return None, nom


def _organisation_a_des_comptes(profile_id: str) -> bool:
    return bool(users.lister_comptes(profile_id))


def _confirmer_par_un_compte_existant(profil: dict) -> None:
    """Exige les identifiants d'un compte RESPONSABLE de CETTE organisation.
    Lève Abandon sinon.

    Sans cela, n'importe qui devant le poste pouvait choisir une organisation
    existante, s'y créer un compte et lire toutes ses conversations (l'assistant
    est accessible depuis le menu de l'application et le menu Démarrer).
    Même temporisation que la connexion (tentatives.py), pour qu'on ne puisse
    pas deviner un mot de passe ici faute de pouvoir le faire à l'écran.

    Seul un responsable confirme, quel que soit le rôle du compte créé : ajouter
    quelqu'un à l'organisation relève de la gestion des comptes, réservée au
    responsable dans l'interface. Laisser un membre confirmer lui permettrait de
    créer un responsable (et donc de s'attribuer ses droits), ou de faire entrer
    une personne que le responsable n'a pas choisie.
    """
    print()
    print(f"Pour ajouter un compte à « {profil.get('name', '')} », un responsable de "
          "cette organisation doit le confirmer.")
    print("Saisissez son identifiant et son mot de passe.")
    for _ in range(ESSAIS_CONFIRMATION):
        identifiant = _saisir("Identifiant d'un compte existant : ")
        attente = tentatives.attente_restante(identifiant)
        if attente > 0:
            raise Abandon("trop de tentatives pour cet identifiant, réessayez dans "
                          f"{tentatives.formater_attente(attente)}")
        try:
            mot_de_passe = getpass.getpass("Son mot de passe (la saisie ne s'affiche pas) : ")
        except (EOFError, KeyboardInterrupt):
            print()
            raise Abandon("saisie interrompue")
        user = users.verify_credentials(identifiant, mot_de_passe)
        if user is None or user.get("profile_id") != profil["id"]:
            # Même message dans les deux cas : ne révèle pas qu'un identifiant
            # existe dans une autre organisation.
            tentatives.noter_echec(identifiant)
            print("  Identifiant ou mot de passe incorrect pour cette organisation.")
            continue
        tentatives.noter_succes(identifiant)
        if users.role_de(user) != users.ROLE_RESPONSABLE:
            # Identifiants exacts : on peut dire pourquoi, sans rien révéler.
            print("  Ce compte est « membre » : seul un responsable de l'organisation "
                  "peut confirmer l'ajout d'un compte.")
            continue
        return
    raise Abandon("confirmation par un responsable de l'organisation non obtenue")


def _choisir_role() -> str:
    """Rôle d'un compte ajouté à une organisation qui en a déjà : membre par défaut."""
    print()
    print("Rôle du nouveau compte :")
    print("  1. Membre (par défaut) : utilise Oliv'IA, ses conversations restent privées")
    print("  2. Responsable : règle les dossiers, les connexions et gère les comptes")
    while True:
        choix = _saisir("Votre choix (1 ou 2, Entrée = membre) : ")
        if choix in ("", "1"):
            return users.ROLE_MEMBRE
        if choix == "2":
            return users.ROLE_RESPONSABLE
        print("  Choix invalide.")


def _cmd_init(args) -> int:
    """Assistant guidé : organisation (existante ou nouvelle) puis compte.

    Pensé pour le premier démarrage d'une installation neuve, où l'écran de
    connexion ne mène nulle part tant qu'aucun compte n'existe ; il sert aussi,
    plus tard, à ajouter un compte. Aucun identifiant à recopier : l'organisation
    se choisit par son nom.
    """
    print("=" * 60)
    print("Oliv'IA - création d'un compte")
    print("=" * 60)
    profil, nouveau_nom = _choisir_organisation()
    # Organisation sans aucun compte (premier compte d'une installation neuve) :
    # rien à confirmer, personne ne pourrait le faire ; ce premier compte en
    # devient le responsable.
    role = users.ROLE_RESPONSABLE
    if profil is not None and _organisation_a_des_comptes(profil["id"]):
        _confirmer_par_un_compte_existant(profil)
        role = _choisir_role()
    while True:
        identifiant = _saisir("Identifiant de connexion (ex. marie) : ")
        if not identifiant:
            print("  L'identifiant est obligatoire.")
            continue
        if len(identifiant) > users.USERNAME_MAX_LEN:
            print(f"  Au plus {users.USERNAME_MAX_LEN} caractères.")
            continue
        if users.get_user_by_username(identifiant) is not None:
            print(f"  L'identifiant « {identifiant} » est déjà pris.")
            continue
        break
    mot_de_passe = _demander_mot_de_passe()
    if profil is None:
        profil = profiles.create_profile(nouveau_nom)
    user = users.create_user(identifiant, mot_de_passe, profil["id"], role=role)
    print()
    print(f"Compte « {user['username']} » créé pour « {profil['name']} » "
          f"(rôle : {user['role']}).")
    print("Lancez Oliv'IA et connectez-vous avec cet identifiant et ce mot de passe.")
    return 0


# ---------- Gestion des comptes existants (lot 4c) ----------
def _compte(identifiant: str) -> dict:
    """Compte désigné par son identifiant de connexion (casse ignorée), ou ValueError."""
    user = users.get_user_by_username(identifiant)
    if user is None:
        raise ValueError(f"Aucun compte ne porte l'identifiant « {identifiant} » "
                         "(voir list-users).")
    return user


def _nom_organisation(profile_id: str) -> str:
    profil = profiles.get_profile(profile_id)
    return profil.get("name", "") if profil else profile_id


def _cmd_list_users(args) -> int:
    if args.profil:
        if profiles.get_profile(args.profil) is None:
            raise ValueError(f"Profil inconnu : {args.profil} (voir list-profiles)")
        organisations = [profiles.get_profile(args.profil)]
    else:
        organisations = profiles.list_profiles()
    trouve = False
    for org in organisations:
        comptes = users.lister_comptes(org["id"])
        if not comptes:
            continue
        trouve = True
        print(f"{org.get('name', '')}  ({org['id']})")
        for u in comptes:
            cree = time.strftime("%d/%m/%Y", time.localtime(u.get("created_at", 0)))
            bloque = "  BLOQUÉ (voir unlock)" if tentatives.est_bloque(u["username"]) else ""
            print(f"  {u['username']:<24} {u['role']:<12} créé le {cree}{bloque}")
    if not trouve:
        print("Aucun compte. Créez-en un avec : init")
    return 0


def _cmd_change_password(args) -> int:
    """Le compte change son mot de passe : l'ancien est exigé, temporisé comme
    à la connexion (même compteur)."""
    user = _compte(args.identifiant)
    for _ in range(ESSAIS_CONFIRMATION):
        attente = tentatives.attente_restante(user["username"])
        if attente > 0:
            raise Abandon("trop de tentatives pour cet identifiant, réessayez dans "
                          f"{tentatives.formater_attente(attente)}")
        try:
            ancien = getpass.getpass("Mot de passe actuel (la saisie ne s'affiche pas) : ")
        except (EOFError, KeyboardInterrupt):
            print()
            raise Abandon("saisie interrompue")
        verifie = users.verify_credentials(user["username"], ancien)
        if verifie is None or verifie["id"] != user["id"]:
            tentatives.noter_echec(user["username"])
            print("  Mot de passe actuel incorrect.")
            continue
        tentatives.noter_succes(user["username"])
        nouveau = _demander_mot_de_passe()
        if not users.changer_mot_de_passe(user["id"], ancien, nouveau):
            raise ValueError("Mot de passe actuel incorrect.")
        fermees = sessions.supprimer_sessions_du_compte(user["id"])
        print(f"Mot de passe de « {user['username']} » changé.")
        if fermees:
            print(f"  {fermees} session(s) ouverte(s) fermée(s) : reconnectez-vous.")
        return 0
    raise Abandon("mot de passe actuel non confirmé")


def _cmd_reset_password(args) -> int:
    user = _compte(args.identifiant)
    print(f"Nouveau mot de passe pour « {user['username']} » "
          f"({_nom_organisation(user['profile_id'])}).")
    nouveau = _demander_mot_de_passe()
    if not users.reinitialiser_mot_de_passe(user["id"], nouveau):
        raise ValueError(f"Le compte « {user['username']} » n'existe plus.")
    sessions.supprimer_sessions_du_compte(user["id"])
    tentatives.debloquer(user["username"])
    print(f"Mot de passe de « {user['username']} » réinitialisé ; ses sessions sont fermées.")
    return 0


def _cmd_delete_user(args) -> int:
    user = _compte(args.identifiant)
    print(f"Supprimer le compte « {user['username']} » ({user['role']}, "
          f"{_nom_organisation(user['profile_id'])}) ?")
    print("Ses conversations privées restent sur le poste, invisibles, jusqu'à "
          "l'effacement des données de l'organisation.")
    if _saisir("Tapez oui pour confirmer : ").lower() != "oui":
        raise Abandon("suppression non confirmée")
    if users.supprimer_compte(user["id"]) is None:
        raise ValueError(f"Le compte « {user['username']} » n'existe plus.")
    sessions.supprimer_sessions_du_compte(user["id"])
    print(f"Compte « {user['username']} » supprimé.")
    return 0


def _cmd_unlock(args) -> int:
    user = _compte(args.identifiant)
    if tentatives.debloquer(user["username"]):
        print(f"Compte « {user['username']} » débloqué : il peut se reconnecter tout de suite.")
    else:
        print(f"Aucun échec de connexion enregistré pour « {user['username']} ».")
    return 0


def _cmd_set_role(args) -> int:
    user = _compte(args.identifiant)
    modifie = users.changer_role(user["id"], args.role)
    if modifie is None:
        raise ValueError(f"Le compte « {user['username']} » n'existe plus.")
    print(f"« {modifie['username']} » est désormais {modifie['role']}.")
    return 0


def construire_parser(prog: str = "manage_users.py") -> argparse.ArgumentParser:
    """Analyseur de la ligne de commande, séparé de `main` pour que les tests
    puissent lister les sous-commandes (voir tests/test_lanceur.py : chacune
    doit être relayée par launch.py)."""
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Crée les organisations (profils) et les comptes utilisateurs d'Oliv'IA.",
    )
    parser.set_defaults(prog=prog)
    sous = parser.add_subparsers(dest="commande", required=True)

    p_init = sous.add_parser(
        "init", help="Assistant guidé : crée une organisation et un compte (recommandé)")
    p_init.set_defaults(func=_cmd_init)

    p_profil = sous.add_parser("create-profile", help="Crée une organisation")
    p_profil.add_argument("name", help="Nom de l'organisation, ex. \"Mairie de Test\"")
    p_profil.set_defaults(func=_cmd_create_profile)

    p_user = sous.add_parser(
        "create-user", help="Crée un compte rattaché à une organisation (mot de passe demandé)")
    p_user.add_argument("username", help="Identifiant de connexion")
    p_user.add_argument("deuxieme", metavar="profile_id",
                        help="id du profil, voir list-profiles")
    p_user.add_argument("troisieme", nargs="?", default=None, help=argparse.SUPPRESS)
    p_user.add_argument("--role", choices=users.ROLES, default=None,
                        help="responsable ou membre (par défaut : responsable pour le "
                             "premier compte de l'organisation, membre ensuite)")
    p_user.set_defaults(func=_cmd_create_user)

    p_liste = sous.add_parser("list-profiles", help="Liste les organisations existantes")
    p_liste.set_defaults(func=_cmd_list_profiles)

    p_comptes = sous.add_parser("list-users", help="Liste les comptes, leur rôle et leur blocage")
    p_comptes.add_argument("--profil", default=None, metavar="profile_id",
                           help="seulement cette organisation (voir list-profiles)")
    p_comptes.set_defaults(func=_cmd_list_users)

    for nom, aide, fonction in (
        ("change-password", "Change le mot de passe d'un compte (l'ancien est demandé)",
         _cmd_change_password),
        ("reset-password", "Fixe un nouveau mot de passe sans l'ancien (oubli)",
         _cmd_reset_password),
        ("delete-user", "Supprime un compte (confirmation demandée)", _cmd_delete_user),
        ("unlock", "Débloque un compte après trop d'échecs de connexion", _cmd_unlock),
    ):
        p = sous.add_parser(nom, help=aide)
        p.add_argument("identifiant", help="Identifiant de connexion du compte")
        p.set_defaults(func=fonction, creation=False)

    p_role = sous.add_parser("set-role", help="Nomme un compte responsable ou membre")
    p_role.add_argument("identifiant", help="Identifiant de connexion du compte")
    p_role.add_argument("role", choices=users.ROLES)
    p_role.set_defaults(func=_cmd_set_role, creation=False)
    return parser


def sous_commandes() -> set[str]:
    """Noms des sous-commandes (init, create-user…)."""
    for action in construire_parser()._actions:
        if isinstance(action, argparse._SubParsersAction):
            return set(action.choices)
    return set()


def main(argv: list[str] | None = None, prog: str = "manage_users.py") -> int:
    args = construire_parser(prog).parse_args(argv)
    try:
        return args.func(args)
    except Abandon as exc:
        suite = ("Aucun compte n'a été créé." if getattr(args, "creation", True)
                 else "Rien n'a été modifié.")
        print(f"Abandon : {exc}. {suite}", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        # Erreur métier attendue (nom déjà pris, profil inconnu, fichier
        # corrompu, dossier non inscriptible) : message lisible plutôt qu'une
        # trace Python.
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
