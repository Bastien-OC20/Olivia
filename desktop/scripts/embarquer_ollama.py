"""
Télécharge le moteur Ollama officiel et le place dans ollama/ (racine du
dépôt), d'où desktop/scripts/preparer.mjs l'embarque dans l'application de
bureau. Lancé par .github/workflows/bureau.yml avant la construction ; aussi
utilisable à la main, depuis la racine du dépôt :

    python desktop/scripts/embarquer_ollama.py

La version est FIGÉE et chaque archive vérifiée par son empreinte SHA-256 :
un installeur ne doit pas changer de moteur au gré des publications d'Ollama,
ni embarquer un fichier altéré. Pour changer de version : mettre à jour
VERSION et les empreintes (sha256sum sur les archives de la release), tester,
puis publier.

Seul le moteur est embarqué, pas les modèles (plusieurs Go, au-delà des 2 Gio
qu'accepte un fichier de release GitHub) : Oliv'IA les fait télécharger au
premier lancement (backend/moteur.py), dans le dossier des données (launch.py,
dossier_modeles_ollama).

Licence : Ollama est sous licence MIT (desktop/licences/OLLAMA-LICENSE.txt,
copiée à côté du moteur) ; les licences de ses composants (llama.cpp…) sont
livrées dans ses archives.
"""
import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

VERSION = "0.35.1"
ARCHIVES = {
    # plateforme: (nom de l'archive, SHA-256)
    "darwin": ("ollama-darwin.tgz",
               "3137dbf28948ee844e0fb3e584d9b5de6879d73d9f0cb7eff3ad64930601d307"),
    "win32": ("ollama-windows-amd64.zip",
              "dc50b9ca7f9023c86525012632cd1615b093d0407987444a7f62ecab617e8e93"),
}
URL = "https://github.com/ollama/ollama/releases/download/v{version}/{archive}"

RACINE = Path(__file__).resolve().parents[2]
LICENCE = RACINE / "desktop" / "licences" / "OLLAMA-LICENSE.txt"


def empreinte(chemin: Path) -> str:
    h = hashlib.sha256()
    with chemin.open("rb") as f:
        for bloc in iter(lambda: f.read(1 << 20), b""):
            h.update(bloc)
    return h.hexdigest()


def telecharger(url: str, destination: Path) -> None:
    print(f"→ Téléchargement : {url}")
    with urllib.request.urlopen(url, timeout=60) as r, destination.open("wb") as f:
        shutil.copyfileobj(r, f, 1 << 20)


def extraire(archive: Path, dossier: Path) -> None:
    dossier.mkdir(parents=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(dossier)
    else:
        # tar du système : sous macOS, il conserve liens symboliques, droits
        # d'exécution et attributs étendus des bibliothèques.
        subprocess.run(["tar", "-xzf", str(archive), "-C", str(dossier)], check=True)


def main(argv=None) -> int:
    # La console d'un runner Windows est en cp1252 : sans cela, le premier
    # « → » ou « ✓ » affiché arrête le script (UnicodeEncodeError).
    for flux in (sys.stdout, sys.stderr):
        if hasattr(flux, "reconfigure"):
            flux.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Embarque le moteur Ollama officiel.")
    parser.add_argument("--plateforme", default=sys.platform, choices=sorted(ARCHIVES),
                        help="par défaut, celle de cette machine")
    parser.add_argument("--archive", type=Path,
                        help="archive déjà téléchargée (vérifiée de la même façon)")
    parser.add_argument("--destination", type=Path, default=RACINE / "ollama")
    args = parser.parse_args(argv)

    nom, attendu = ARCHIVES[args.plateforme]
    dest = args.destination
    if dest.exists():
        # Un ollama/ existant peut contenir des modèles (disque portable,
        # installeur Inno Setup) : jamais écrasé sans qu'on l'ait retiré soi-même.
        print(f"❌ {dest} existe déjà : retirez-le d'abord (il peut contenir des modèles).")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        archive = args.archive or Path(tmp) / nom
        if not args.archive:
            telecharger(URL.format(version=VERSION, archive=nom), archive)
        obtenu = empreinte(archive)
        if obtenu != attendu:
            print(f"❌ Empreinte inattendue pour {nom} :")
            print(f"   attendue {attendu}\n   obtenue  {obtenu}")
            return 1
        print(f"✓ Empreinte SHA-256 vérifiée ({nom}, Ollama {VERSION})")
        extraire(archive, dest)

    exe = dest / ("ollama.exe" if args.plateforme == "win32" else "ollama")
    if not exe.is_file():
        print(f"❌ {exe.name} absent de l'archive : structure inattendue.")
        return 1
    shutil.copyfile(LICENCE, dest / "LICENSE-OLLAMA.txt")
    print(f"✓ Ollama {VERSION} embarqué dans {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
