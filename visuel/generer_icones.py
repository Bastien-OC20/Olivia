"""
Génère toutes les icônes d'Olivia à partir d'un seul fichier :
visuel/logos_olivia/oliv-ia.png.

    pip install pillow numpy
    python visuel/generer_icones.py            # depuis la racine du dépôt

Le logo source est une tuile bleue aux coins arrondis, avec le « O » au rameau
d'olivier et le mot « Oliv'ia ». Ses coins sont soit transparents (PNG avec canal
alpha, export du .psd), soit posés sur un fond blanc carré. Deux variantes en
sont tirées :

  - le LOGO COMPLET, coins rendus transparents : grandes icônes (application
    macOS, tailles ≥ 64 px de l'icône Windows), où le mot « Oliv'ia » reste
    lisible ;
  - la MARQUE : même tuile, avec le seul « O » au rameau, agrandi et centré.
    Pour les petites tailles (16 à 48 px, favicon, barre des menus, barre du
    haut de l'interface) où le mot deviendrait une tache illisible — et où
    « Olivia » est de toute façon écrit juste à côté.

Fichiers produits (tous versionnés) :
  frontend/src/assets/logo-mark.png   marque, 512 px   (interface)
  frontend/public/favicon.ico         marque, 16-48 px (onglet du navigateur)
  ai-webapp.ico                       16-48 marque, 64-256 logo (exe Windows, Inno Setup)
  desktop/build/icon.png              logo, 1024 px, marge macOS (application macOS)
  desktop/build/icon.ico              comme ai-webapp.ico (application et installeur Windows)
  desktop/icons/fenetre.png           marque, 256 px   (fenêtre, écran de démarrage)
  desktop/icons/tray.png, tray@2x.png marque, 32 et 64 px (barre des menus / notification)
  visuel/logo-transparent.png         logo, 512 px     (en-tête du README)
"""
import io
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

RACINE = Path(__file__).resolve().parent.parent
SOURCE = RACINE / "visuel" / "logos_olivia" / "oliv-ia.png"

# Lignes du logo source (1254 px) occupées par le « O » au rameau ; le mot
# « Oliv'ia » commence en dessous (mesuré : O de 122 à 852, texte dès 885).
O_HAUT, O_BAS = 100, 868

# Grille des icônes macOS : la tuile occupe 824 px d'une toile de 1024, le reste
# est une marge transparente. Sans elle, l'icône paraît plus grosse que les
# autres dans le Dock.
MAC_TOILE, MAC_TUILE = 1024, 824

TAILLES_MARQUE = (16, 24, 32, 48)
TAILLES_LOGO = (64, 128, 256)


def _depuis_coins(passable: np.ndarray) -> np.ndarray:
    """Zone atteinte par remplissage depuis les quatre coins, à travers les
    pixels « passables »."""
    h, w = passable.shape
    atteint = np.zeros((h, w), bool)
    pile = [(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)]
    while pile:
        y, x = pile.pop()
        if atteint[y, x] or not passable[y, x]:
            continue
        atteint[y, x] = True
        if y > 0:
            pile.append((y - 1, x))
        if y < h - 1:
            pile.append((y + 1, x))
        if x > 0:
            pile.append((y, x - 1))
        if x < w - 1:
            pile.append((y, x + 1))
    return atteint


def preparer(source: Image.Image) -> tuple[np.ndarray, np.ndarray]:
    """Couleurs et opacité de la tuile.

    Source avec canal alpha : seuls les coins, reliés au bord, restent
    transparents. L'export du .psd laisse aussi le blanc du « O » transparent :
    ces trous intérieurs sont rebouchés en blanc, sans quoi le « O » prendrait
    la couleur du fond (noir sur le thème sombre de GitHub).
    Source sans canal alpha : l'opacité se déduit du fond blanc des coins.
    """
    rgb = np.asarray(source.convert("RGB")).astype(np.float64)
    if "A" not in source.getbands():
        return rgb, masque_tuile(rgb)
    alpha = np.asarray(source.getchannel("A")).astype(np.float64) / 255.0
    exterieur = _depuis_coins(alpha < 1.0)
    trou = ~exterieur & (alpha < 1.0)
    a = alpha[trou][:, None]
    rgb[trou] = rgb[trou] * a + 255.0 * (1.0 - a)
    alpha[trou] = 1.0
    return rgb, alpha


def masque_tuile(rgb: np.ndarray) -> np.ndarray:
    """Opacité de la tuile : 0 sur le fond blanc des coins, 1 dans la tuile.

    Le fond blanc est atteint par remplissage depuis les quatre coins (le blanc
    du « O » et du texte, entouré de bleu, n'est jamais touché). Le bord, lissé
    par le dessinateur, est un mélange de blanc et de bleu : son opacité se
    déduit de la distance au blanc.
    """
    h, w, _ = rgb.shape
    exterieur = _depuis_coins(rgb.min(axis=2) > 235)
    alpha = np.ones((h, w))
    alpha[exterieur] = 0.0
    # Liseré : pixels voisins du fond, ni tout blancs ni tout bleus.
    voisin = np.asarray(Image.fromarray((exterieur * 255).astype(np.uint8))
                        .filter(ImageFilter.MaxFilter(5))) > 0
    bord = voisin & ~exterieur
    bleu_ref = np.array([70.0, 155.0, 230.0])
    part = (255.0 - rgb[..., 0]) / (255.0 - bleu_ref[0])
    alpha[bord] = np.clip(part[bord], 0.0, 1.0)
    return alpha


def degrade_fond(rgb: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """Fond bleu reconstruit : polynôme de degré 2 ajusté sur les pixels bleus."""
    h, w, _ = rgb.shape
    r, b = rgb[..., 0], rgb[..., 2]
    bleu = (b - r > 60) & (b > 150) & (alpha > 0.99)
    ys, xs = np.nonzero(bleu)
    pas = max(1, ys.size // 60000)
    ys, xs = ys[::pas], xs[::pas]

    def termes(y, x):
        y, x = y / h, x / w
        return np.stack([np.ones_like(x), x, y, x * x, x * y, y * y], axis=-1)
    coeffs = np.linalg.lstsq(termes(ys, xs), rgb[ys, xs], rcond=None)[0]
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
    return np.clip(termes(yy, xx) @ coeffs, 0, 255)


def rgba(rgb: np.ndarray, alpha: np.ndarray) -> Image.Image:
    a = (np.clip(alpha, 0, 1) * 255).round().astype(np.uint8)
    return Image.fromarray(np.dstack([rgb.round().astype(np.uint8), a]), "RGBA")


def logo_complet(source: Image.Image) -> Image.Image:
    rgb, alpha = preparer(source)
    # Sous le liseré, la couleur garde un reste de blanc : on la ramène au bleu.
    fond = degrade_fond(rgb, alpha)
    bord = (alpha > 0) & (alpha < 1)
    rgb[bord] = fond[bord]
    return rgba(rgb, alpha)


def marque(source: Image.Image) -> Image.Image:
    """Tuile bleue et « O » au rameau seul, agrandi et centré."""
    rgb, alpha = preparer(source)
    h, w, _ = rgb.shape
    fond = degrade_fond(rgb, alpha)

    # Premier plan du « O » : ce qui s'écarte du fond bleu (blanc, vert).
    zone = rgb[O_HAUT:O_BAS]
    ecart = np.linalg.norm(zone - fond[O_HAUT:O_BAS], axis=2)
    opacite = np.clip((ecart - 12.0) / 48.0, 0.0, 1.0)
    # Seulement à l'intérieur de la tuile : le blanc des coins, au bord de ces
    # lignes, n'appartient pas au dessin.
    # Le bord de l'image compte aussi comme extérieur : la tuile peut le toucher.
    hors_tuile = alpha < 1
    hors_tuile[:, :8] = hors_tuile[:, -8:] = True
    interieur = np.asarray(Image.fromarray((hors_tuile * 255).astype(np.uint8))
                           .filter(ImageFilter.MaxFilter(15)))[O_HAUT:O_BAS] == 0
    opacite *= interieur
    colonnes = np.nonzero(opacite.max(axis=0) > 0.5)[0]
    lignes = np.nonzero(opacite.max(axis=1) > 0.5)[0]
    x0, x1 = colonnes.min(), colonnes.max() + 1
    y0, y1 = lignes.min(), lignes.max() + 1
    dessin = rgba(zone[y0:y1, x0:x1], opacite[y0:y1, x0:x1])

    # 80 % de la largeur de la tuile au plus, 72 % de sa hauteur au plus.
    echelle = min(0.80 * w / dessin.width, 0.72 * h / dessin.height)
    dessin = dessin.resize((round(dessin.width * echelle), round(dessin.height * echelle)),
                           Image.LANCZOS)
    tuile = rgba(fond, alpha)
    tuile.alpha_composite(dessin, ((w - dessin.width) // 2, (h - dessin.height) // 2))
    # La tuile garde ses coins arrondis : le dessin ne déborde pas du masque.
    a = np.minimum(np.asarray(tuile)[..., 3], (alpha * 255).astype(np.uint8))
    tuile.putalpha(Image.fromarray(a))
    return tuile


def reduire(img: Image.Image, cote: int) -> Image.Image:
    return img.resize((cote, cote), Image.LANCZOS)


def _dib(img: Image.Image) -> bytes:
    """Entrée d'icône au format bitmap classique (BGRA 32 bits + masque ET)."""
    cote = img.width
    pixels = np.asarray(img.convert("RGBA"))[::-1]          # lignes de bas en haut
    bgra = pixels[..., [2, 1, 0, 3]].tobytes()
    ligne_masque = ((cote + 31) // 32) * 4                  # alignement sur 32 bits
    masque = bytes(ligne_masque * cote)                     # opacité portée par l'alpha
    entete = struct.pack("<IiiHHIIiiII", 40, cote, 2 * cote, 1, 32, 0,
                         len(bgra) + len(masque), 0, 0, 0, 0)
    return entete + bgra + masque


def ecrire_ico(chemin: Path, images: list[Image.Image]) -> None:
    """ICO multi-tailles, une image dessinée par taille (Pillow réduirait sinon
    la même image à toutes les tailles, texte compris). Usage Windows : bitmap
    classique jusqu'à 128 px, PNG pour 256 px — le format le mieux accepté par
    PyInstaller, Inno Setup et NSIS."""
    donnees = []
    for img in images:
        if img.width >= 256:
            tampon = io.BytesIO()
            img.save(tampon, "PNG", optimize=True)
            donnees.append(tampon.getvalue())
        else:
            donnees.append(_dib(img))
    entete = struct.pack("<HHH", 0, 1, len(images))
    decalage = 6 + 16 * len(images)
    repertoire = b""
    for img, octets in zip(images, donnees):
        cote = img.width if img.width < 256 else 0      # 0 signifie 256
        repertoire += struct.pack("<BBBBHHII", cote, cote, 0, 0, 1, 32,
                                  len(octets), decalage)
        decalage += len(octets)
    chemin.write_bytes(entete + repertoire + b"".join(donnees))


def main() -> None:
    source = Image.open(SOURCE)
    logo = logo_complet(source)
    mq = marque(source)

    reduire(mq, 512).save(RACINE / "frontend/src/assets/logo-mark.png", optimize=True)
    ecrire_ico(RACINE / "frontend/public/favicon.ico", [reduire(mq, t) for t in TAILLES_MARQUE])

    ico = [reduire(mq, t) for t in TAILLES_MARQUE] + [reduire(logo, t) for t in TAILLES_LOGO]
    ecrire_ico(RACINE / "ai-webapp.ico", ico)
    ecrire_ico(RACINE / "desktop/build/icon.ico", ico)

    mac = Image.new("RGBA", (MAC_TOILE, MAC_TOILE), (0, 0, 0, 0))
    marge = (MAC_TOILE - MAC_TUILE) // 2
    mac.alpha_composite(reduire(logo, MAC_TUILE), (marge, marge))
    mac.save(RACINE / "desktop/build/icon.png", optimize=True)

    reduire(mq, 256).save(RACINE / "desktop/icons/fenetre.png", optimize=True)
    reduire(mq, 32).save(RACINE / "desktop/icons/tray.png", optimize=True)
    reduire(mq, 64).save(RACINE / "desktop/icons/tray@2x.png", optimize=True)
    # Coins transparents : des coins blancs seraient visibles sur le thème
    # sombre de GitHub.
    reduire(logo, 512).save(RACINE / "visuel/logo-transparent.png", optimize=True)
    print("Icônes générées depuis", SOURCE.relative_to(RACINE))


if __name__ == "__main__":
    main()
