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
        python backend/manage_users.py create-user marie <profile_id>
        python backend/manage_users.py list-profiles

Le mot de passe est DEMANDÉ au clavier, masqué, et jamais passé en argument :
un argument de ligne de commande reste dans l'historique du terminal et se lit
dans la liste des processus. L'ancienne forme `create-user <nom> <mot-de-passe>
<profil>` reste acceptée pour les scripts existants, avec un avertissement.
"""
import argparse
import getpass
import sys
from pathlib import Path

# Lancé en script (et non en module), ce fichier n'a pas de paquet parent : les
# imports relatifs de profiles.py/users.py échoueraient. On rend donc la racine
# du dépôt importable pour retrouver `backend` comme paquet.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import profiles, users  # noqa: E402

# Nombre d'essais laissés pour saisir deux fois le même mot de passe.
ESSAIS_MOT_DE_PASSE = 3


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
    user = users.create_user(args.username, mot_de_passe, profile_id)
    profil = profiles.get_profile(user["profile_id"])
    print(f"Compte créé : {user['username']}")
    print(f"  id      : {user['id']}")
    print(f"  profil  : {profil['name'] if profil else user['profile_id']}")
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


def _cmd_init(args) -> int:
    """Assistant guidé : organisation (existante ou nouvelle) puis compte.

    Pensé pour le premier démarrage d'une installation neuve, où l'écran de
    connexion ne mène nulle part tant qu'aucun compte n'existe ; il sert aussi,
    plus tard, à ajouter un compte. Aucun identifiant à recopier : l'organisation
    se choisit par son nom.
    """
    print("=" * 60)
    print("Olivia - création d'un compte")
    print("=" * 60)
    profil, nouveau_nom = _choisir_organisation()
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
    user = users.create_user(identifiant, mot_de_passe, profil["id"])
    print()
    print(f"Compte « {user['username']} » créé pour « {profil['name']} ».")
    print("Lancez Olivia et connectez-vous avec cet identifiant et ce mot de passe.")
    return 0


def main(argv: list[str] | None = None, prog: str = "manage_users.py") -> int:
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Crée les organisations (profils) et les comptes utilisateurs d'Olivia.",
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
    p_user.set_defaults(func=_cmd_create_user)

    p_liste = sous.add_parser("list-profiles", help="Liste les organisations existantes")
    p_liste.set_defaults(func=_cmd_list_profiles)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Abandon as exc:
        print(f"Abandon : {exc}. Aucun compte n'a été créé.", file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, OSError) as exc:
        # Erreur métier attendue (nom déjà pris, profil inconnu, fichier
        # corrompu, dossier non inscriptible) : message lisible plutôt qu'une
        # trace Python.
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
