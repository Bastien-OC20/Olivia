"""
Coffre des secrets : chiffrement par Windows (DPAPI), sans dépendance.

Pourquoi (audit du 15/11/2026) : le mot de passe IMAP, le jeton Notion et la clé
d'API Brave étaient écrits en clair dans settings.json. Le dossier des données
d'un poste installé est déjà réservé au compte Windows de la personne (voir
backend/emplacements.py), mais une sauvegarde, une copie du dossier ou un
administrateur du poste les lisaient tels quels.

DPAPI, portée UTILISATEUR : la clé de chiffrement est dérivée du mot de passe
de session Windows de la personne et gérée par le système. Aucune clé à ranger
ni à perdre ; seul ce compte Windows, sur ce poste, peut relire la valeur. Une
valeur copiée sur un autre compte ou un autre poste est donc illisible : c'est
voulu, et backend/settings.py la traite comme vide (« à ressaisir »).

QUAND chiffrer (`actif`) : sous Windows ET quand le dossier des données vient de
`olivia.ini` (installeur) ou de OLIVIA_DATA_DIR (application de bureau). Sur la
clé portable, les données voyagent d'un ordinateur à l'autre : chiffrées par le
compte d'un poste, elles deviendraient illisibles sur le suivant. macOS et Linux
n'ont pas de DPAPI. Dans ces cas, les secrets restent en clair, comme avant, et
l'interface le signale à côté des champs concernés.

Format stocké : `dpapi:v1:<base64>`. Le préfixe distingue sans ambiguïté une
valeur chiffrée d'un secret en clair hérité d'une version antérieure, et le
numéro de version laisse la porte ouverte à un autre procédé sans casser la
lecture des valeurs existantes.

Aucune exception `ctypes` ou `OSError` ne sort de ce module : tout échec devient
`SecretIllisible`, que l'appelant traite sans erreur visible.
"""
import base64
import binascii
import sys

from . import emplacements

PREFIXE = "dpapi:v1:"
# Entropie supplémentaire propre à Oliv'IA : un autre programme lancé sous le
# même compte Windows ne peut pas déchiffrer nos valeurs par un simple appel à
# CryptUnprotectData sans la connaître. Ce n'est pas un secret (elle est dans le
# code source) : elle cloisonne les usages, elle ne remplace pas le compte
# Windows. NE JAMAIS LA MODIFIER : toutes les valeurs déjà chiffrées
# deviendraient illisibles (il faudrait alors un nouveau préfixe « dpapi:v2: »).
ENTROPIE = b"Oliv'IA - secrets des reglages - v1"
DESCRIPTION = "Oliv'IA"

# Interdit à Windows d'afficher une boîte de dialogue : Olivia tourne en
# arrière-plan, une fenêtre invisible bloquerait la requête.
_CRYPTPROTECT_UI_FORBIDDEN = 0x1


class SecretIllisible(Exception):
    """Valeur chiffrée impossible à relire (autre compte Windows, autre poste,
    valeur corrompue, ou poste sans DPAPI)."""


_api = None          # (crypt32, kernel32, DATA_BLOB) une fois chargés


def _charger_api():
    """Fonctions Windows, chargées au premier besoin. None hors Windows ou si
    le chargement échoue (DLL introuvable : ne doit jamais arrêter Olivia)."""
    global _api
    if _api is not None:
        return _api
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", wintypes.DWORD),
                        ("pbData", ctypes.POINTER(ctypes.c_char))]

        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        pblob = ctypes.POINTER(DATA_BLOB)
        crypt32.CryptProtectData.argtypes = [
            pblob, wintypes.LPCWSTR, pblob, ctypes.c_void_p, ctypes.c_void_p,
            wintypes.DWORD, pblob]
        crypt32.CryptProtectData.restype = wintypes.BOOL
        crypt32.CryptUnprotectData.argtypes = [
            pblob, ctypes.POINTER(wintypes.LPWSTR), pblob, ctypes.c_void_p,
            ctypes.c_void_p, wintypes.DWORD, pblob]
        crypt32.CryptUnprotectData.restype = wintypes.BOOL
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        _api = (crypt32, kernel32, DATA_BLOB)
    except (OSError, AttributeError, ImportError):
        return None
    return _api


def _appeler(proteger: bool, donnees: bytes) -> bytes:
    """CryptProtectData (proteger=True) ou CryptUnprotectData. Lève
    SecretIllisible en cas d'échec, jamais une exception ctypes."""
    api = _charger_api()
    if api is None:
        raise SecretIllisible("Chiffrement Windows indisponible sur ce poste.")
    import ctypes
    crypt32, kernel32, DATA_BLOB = api
    # Les tampons doivent rester vivants pendant tout l'appel : on garde une
    # référence locale, ctypes ne copie pas les données pointées.
    tampon = ctypes.create_string_buffer(donnees, len(donnees))
    entree = DATA_BLOB(len(donnees), ctypes.cast(tampon, ctypes.POINTER(ctypes.c_char)))
    tampon_entropie = ctypes.create_string_buffer(ENTROPIE, len(ENTROPIE))
    entropie = DATA_BLOB(len(ENTROPIE),
                         ctypes.cast(tampon_entropie, ctypes.POINTER(ctypes.c_char)))
    sortie = DATA_BLOB()
    try:
        if proteger:
            ok = crypt32.CryptProtectData(
                ctypes.byref(entree), DESCRIPTION, ctypes.byref(entropie), None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(sortie))
        else:
            ok = crypt32.CryptUnprotectData(
                ctypes.byref(entree), None, ctypes.byref(entropie), None, None,
                _CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(sortie))
    except (OSError, ctypes.ArgumentError) as e:
        raise SecretIllisible(str(e)) from None
    if not ok:
        raise SecretIllisible(f"Erreur Windows {ctypes.get_last_error()}.")
    try:
        return ctypes.string_at(sortie.pbData, sortie.cbData)
    finally:
        # La mémoire de sortie est allouée par Windows (LocalAlloc) : sans
        # LocalFree, chaque lecture de réglages fuirait un peu de mémoire.
        kernel32.LocalFree(ctypes.cast(sortie.pbData, ctypes.c_void_p))


def _proteger(donnees: bytes) -> bytes:
    return _appeler(True, donnees)


def _deproteger(donnees: bytes) -> bytes:
    return _appeler(False, donnees)


def actif() -> bool:
    """Vrai si les secrets sont chiffrés à l'enregistrement sur ce poste.

    Faux sur la clé portable (dossier des données par défaut), sous macOS et
    Linux, et si DPAPI ne peut pas être chargé : l'interface affiche alors
    « enregistré en clair sur ce poste » à côté des champs secrets.
    """
    if sys.platform != "win32":
        return False
    if emplacements.origine_donnees() not in (emplacements.ORIGINE_ENV,
                                              emplacements.ORIGINE_INI):
        return False
    return _charger_api() is not None


def est_chiffre(valeur) -> bool:
    return isinstance(valeur, str) and valeur.startswith(PREFIXE)


def chiffrer(texte: str) -> str:
    """`dpapi:v1:<base64>` pour `texte`. Lève SecretIllisible si Windows refuse.

    Ne regarde pas `actif()` : c'est à l'appelant de décider s'il chiffre.
    """
    brut = _proteger(texte.encode("utf-8"))
    return PREFIXE + base64.b64encode(brut).decode("ascii")


def dechiffrer(valeur: str) -> str:
    """Texte en clair d'une valeur lue sur disque.

    Une valeur SANS préfixe est renvoyée telle quelle : secret en clair hérité
    d'une version antérieure, ou enregistré sur un poste qui ne chiffre pas.
    Lève SecretIllisible si la valeur est chiffrée mais impossible à relire.
    """
    if not est_chiffre(valeur):
        return valeur
    try:
        brut = base64.b64decode(valeur[len(PREFIXE):], validate=True)
    except (binascii.Error, ValueError):
        raise SecretIllisible("Valeur chiffrée corrompue.") from None
    try:
        return _deproteger(brut).decode("utf-8")
    except UnicodeDecodeError:
        raise SecretIllisible("Valeur chiffrée corrompue.") from None
