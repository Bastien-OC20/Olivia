"""
Provisionnement en ligne de commande des organisations et des comptes.

Il n'y a volontairement pas d'interface graphique d'administration : comme les
connecteurs OAuth, ces réglages se préparent une fois par le service
informatique, pas par l'utilisatrice finale.

À lancer depuis la RACINE du dépôt :
    python backend/manage_users.py create-profile "Mairie de Test"
    python backend/manage_users.py create-user marie motdepasse <profile_id>
    python backend/manage_users.py list-profiles
"""
import argparse
import sys
from pathlib import Path

# Lancé en script (et non en module), ce fichier n'a pas de paquet parent : les
# imports relatifs de profiles.py/users.py échoueraient. On rend donc la racine
# du dépôt importable pour retrouver `backend` comme paquet.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import profiles, users  # noqa: E402


def _cmd_create_profile(args) -> int:
    profil = profiles.create_profile(args.name)
    print(f"Profil créé : {profil['name']}")
    print(f"  id : {profil['id']}")
    print("Créez maintenant un compte rattaché à ce profil :")
    print(f"  python backend/manage_users.py create-user <username> <password> {profil['id']}")
    return 0


def _cmd_create_user(args) -> int:
    user = users.create_user(args.username, args.password, args.profile_id)
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="manage_users.py",
        description="Crée les organisations (profils) et les comptes utilisateurs d'Olivia.",
    )
    sous = parser.add_subparsers(dest="commande", required=True)

    p_profil = sous.add_parser("create-profile", help="Crée une organisation")
    p_profil.add_argument("name", help="Nom de l'organisation, ex. \"Mairie de Test\"")
    p_profil.set_defaults(func=_cmd_create_profile)

    p_user = sous.add_parser("create-user", help="Crée un compte rattaché à une organisation")
    p_user.add_argument("username", help="Identifiant de connexion")
    p_user.add_argument("password", help="Mot de passe (jamais stocké en clair)")
    p_user.add_argument("profile_id", help="id du profil, voir list-profiles")
    p_user.set_defaults(func=_cmd_create_user)

    p_liste = sous.add_parser("list-profiles", help="Liste les organisations existantes")
    p_liste.set_defaults(func=_cmd_list_profiles)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError) as exc:
        # Erreur métier attendue (nom déjà pris, profil inconnu, fichier
        # corrompu) : message lisible plutôt qu'une trace Python.
        print(f"Erreur : {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
