"""
Secrets des réglages chiffrés par Windows (DPAPI) — audit du 15/11/2026, lot 4d.

Avant : le mot de passe IMAP, le jeton Notion et la clé Brave étaient écrits en
clair dans settings.json ; une sauvegarde ou une copie du dossier les livrait
tels quels. Désormais, sur un poste installé sous Windows, ils sont chiffrés
pour le compte Windows de la personne ; un secret illisible (autre compte,
autre poste, valeur abîmée) vaut vide, sans jamais faire échouer Olivia.
"""
import json
import sys

import pytest

from backend import coffre, emplacements, settings

MDP = "Mot-De-Passe-IMAP-42"
JETON = "secret_notion_abcdef"
CLE = "BSA-cle-brave-123"
SECRETS_CLAIRS = (MDP, JETON, CLE)

sous_windows = pytest.mark.skipif(sys.platform != "win32", reason="DPAPI : Windows seulement")


@pytest.fixture(autouse=True)
def detection_materielle_neutre(monkeypatch):
    # Le premier chargement d'une organisation détecte la carte graphique :
    # inutile (et lent) ici.
    monkeypatch.setattr(settings.hardware, "detect_default_device", lambda: "cpu")


@pytest.fixture
def chiffrement_simule(monkeypatch):
    """Coffre actif et DPAPI remplacé par une transformation réversible : les
    scénarios de format et de migration tournent aussi sous Linux et macOS."""
    monkeypatch.setattr(coffre, "actif", lambda: True)
    monkeypatch.setattr(coffre, "_proteger", lambda b: b"SIM" + b[::-1])

    def deproteger(b):
        if not b.startswith(b"SIM"):
            raise coffre.SecretIllisible("simulé")
        return b[3:][::-1]
    monkeypatch.setattr(coffre, "_deproteger", deproteger)


def _remplir(reglages: settings.Settings):
    reglages.update({
        "search_brave_api_key": CLE,
        "connectors": {"imap": {"host": "imap.exemple.fr", "password": MDP},
                       "notion": {"api_token": JETON}},
    })


def _sur_disque(chemin) -> str:
    return chemin.read_text(encoding="utf-8")


def test_les_trois_secrets_sont_declares():
    """Un secret oublié dans la liste resterait en clair sur disque."""
    noms = {".".join(c) for c in settings.SECRETS}
    assert noms == {"connectors.imap.password", "connectors.notion.api_token",
                    "search_brave_api_key"}
    for chemin in settings.SECRETS:
        assert settings._lire_chemin(settings.DEFAULTS, chemin) == ""


# ---------- Vrai DPAPI (Windows) ----------

@sous_windows
def test_aller_retour_dpapi():
    valeur = coffre.chiffrer("é€ secret ✓")
    assert valeur.startswith("dpapi:v1:")
    assert "secret" not in valeur
    assert coffre.dechiffrer(valeur) == "é€ secret ✓"


@sous_windows
def test_poste_installe_chiffre(monkeypatch, tmp_path):
    """Dossier des données choisi par OLIVIA_DATA_DIR (application de bureau)."""
    monkeypatch.setenv(emplacements.VARIABLE_ENV, str(tmp_path / "donnees"))
    assert coffre.actif()


@sous_windows
def test_secrets_illisibles_sur_disque_et_relus(monkeypatch, tmp_path):
    monkeypatch.setenv(emplacements.VARIABLE_ENV, str(tmp_path / "donnees"))
    chemin = tmp_path / "settings.json"
    reglages = settings.Settings(chemin)
    _remplir(reglages)
    texte = _sur_disque(chemin)
    for secret in SECRETS_CLAIRS:
        assert secret not in texte
    brut = json.loads(texte)
    assert brut["connectors"]["imap"]["password"].startswith("dpapi:v1:")
    assert brut["connectors"]["imap"]["host"] == "imap.exemple.fr"   # le reste en clair
    # En mémoire, le reste du backend (IMAP, recherche) lit la valeur en clair.
    assert reglages.get()["connectors"]["imap"]["password"] == MDP
    relu = settings.Settings(chemin).get()
    assert relu["connectors"]["imap"]["password"] == MDP
    assert relu["connectors"]["notion"]["api_token"] == JETON
    assert relu["search_brave_api_key"] == CLE


# ---------- Partout ----------

def test_cle_portable_reste_en_clair(monkeypatch):
    """Données dans le dossier de l'application (clé USB, développement) : elles
    doivent rester lisibles d'un ordinateur à l'autre."""
    monkeypatch.delenv(emplacements.VARIABLE_ENV, raising=False)
    monkeypatch.setattr(emplacements, "_lire_ini", lambda *a, **k: "")
    assert emplacements.origine_donnees() == emplacements.ORIGINE_DEFAUT
    assert coffre.actif() is False


def test_poste_non_chiffre_ecrit_en_clair(monkeypatch, tmp_path):
    monkeypatch.setattr(coffre, "actif", lambda: False)
    chemin = tmp_path / "settings.json"
    _remplir(settings.Settings(chemin))
    brut = json.loads(_sur_disque(chemin))
    assert brut["connectors"]["imap"]["password"] == MDP
    assert brut["search_brave_api_key"] == CLE
    assert settings.Settings(chemin).get()["connectors"]["notion"]["api_token"] == JETON


@pytest.mark.parametrize("abimee", ["dpapi:v1:xxx", "dpapi:v1:AAAA", "dpapi:v1:"])
def test_secret_corrompu_vaut_vide_et_est_signale(tmp_path, abimee):
    """Profil Windows changé, fichier copié d'un autre poste : jamais d'erreur."""
    chemin = tmp_path / "settings.json"
    chemin.write_text(json.dumps({
        "tone": "formal",
        "search_brave_api_key": abimee,
        "connectors": {"imap": {"password": abimee, "host": "h"}},
    }), encoding="utf-8")
    avant = _sur_disque(chemin)
    reglages = settings.Settings(chemin)
    lus = reglages.get()
    assert lus["connectors"]["imap"]["password"] == ""
    assert lus["search_brave_api_key"] == ""
    assert lus["tone"] == "formal"                     # le reste est intact
    assert reglages.secrets_a_ressaisir() == ["connectors.imap.password",
                                              "search_brave_api_key"]
    assert _sur_disque(chemin) == avant                # pas de réécriture au chargement


def test_secret_illisible_conserve_jusqu_a_ressaisie(tmp_path, chiffrement_simule):
    """Un autre réglage enregistré ne doit ni effacer la valeur illisible (un
    retour sur le bon compte Windows la retrouverait) ni faire oublier qu'elle
    est à ressaisir ; une nouvelle saisie, si."""
    chemin = tmp_path / "settings.json"
    chemin.write_text(json.dumps({"connectors": {"imap": {"password": "dpapi:v1:AAAA"}}}),
                      encoding="utf-8")
    reglages = settings.Settings(chemin)
    # L'interface renvoie "" pour le champ vide à chaque « Enregistrer ».
    reglages.update({"tone": "formal", "connectors": {"imap": {"password": ""}}})
    assert json.loads(_sur_disque(chemin))["connectors"]["imap"]["password"] == "dpapi:v1:AAAA"
    assert settings.Settings(chemin).secrets_a_ressaisir() == ["connectors.imap.password"]

    reglages.update({"connectors": {"imap": {"password": MDP}}})
    assert reglages.secrets_a_ressaisir() == []
    assert settings.Settings(chemin).get()["connectors"]["imap"]["password"] == MDP


def test_secret_en_clair_herite_puis_chiffre(tmp_path, chiffrement_simule):
    """Migration : relu tel quel, chiffré au prochain enregistrement seulement."""
    chemin = tmp_path / "settings.json"
    chemin.write_text(json.dumps({"connectors": {"imap": {"password": MDP}}}),
                      encoding="utf-8")
    reglages = settings.Settings(chemin)
    assert reglages.get()["connectors"]["imap"]["password"] == MDP
    assert reglages.secrets_a_ressaisir() == []
    assert MDP in _sur_disque(chemin)                  # pas de réécriture au démarrage

    reglages.update({"tone": "friendly"})
    texte = _sur_disque(chemin)
    assert MDP not in texte
    assert json.loads(texte)["connectors"]["imap"]["password"].startswith("dpapi:v1:")
    assert reglages.get()["connectors"]["imap"]["password"] == MDP
    assert settings.Settings(chemin).get()["connectors"]["imap"]["password"] == MDP


def test_secret_vide_non_chiffre(tmp_path, chiffrement_simule):
    chemin = tmp_path / "settings.json"
    settings.Settings(chemin).update({"tone": "formal"})
    brut = json.loads(_sur_disque(chemin))
    assert brut["connectors"]["imap"]["password"] == ""
    assert brut["search_brave_api_key"] == ""


def test_chiffrement_refuse_garde_le_secret(tmp_path, monkeypatch):
    """Windows refuse de chiffrer : le secret n'est ni perdu ni bloquant."""
    monkeypatch.setattr(coffre, "actif", lambda: True)

    def refus(_):
        raise coffre.SecretIllisible("refus")
    monkeypatch.setattr(coffre, "_proteger", refus)
    chemin = tmp_path / "settings.json"
    settings.Settings(chemin).update({"search_brave_api_key": CLE})
    assert settings.Settings(chemin).get()["search_brave_api_key"] == CLE


def test_effacement_ne_laisse_aucun_secret(tmp_path, chiffrement_simule):
    chemin = tmp_path / "settings.json"
    chemin.write_text(json.dumps({"search_brave_api_key": "dpapi:v1:AAAA"}),
                      encoding="utf-8")
    reglages = settings.Settings(chemin)
    reglages.update({"connectors": {"imap": {"password": MDP}}})
    assert reglages.secrets_a_ressaisir() == ["search_brave_api_key"]
    reglages.reset()
    texte = _sur_disque(chemin)
    assert "dpapi:v1:" not in texte
    for secret in SECRETS_CLAIRS:
        assert secret not in texte
    assert reglages.secrets_a_ressaisir() == []


def test_dechiffrer_valeur_sans_prefixe():
    assert coffre.dechiffrer("en clair") == "en clair"
    assert coffre.dechiffrer("") == ""


def test_hors_windows_valeur_chiffree_illisible(monkeypatch):
    monkeypatch.setattr(coffre, "_api", None)
    monkeypatch.setattr(coffre.sys, "platform", "linux")
    assert coffre.actif() is False
    with pytest.raises(coffre.SecretIllisible):
        coffre.dechiffrer("dpapi:v1:AAAA")
