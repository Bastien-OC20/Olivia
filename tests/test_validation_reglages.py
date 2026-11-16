"""
Validation des réglages enregistrés (audit, point 12).

Avant : `PUT /api/settings` acceptait n'importe quoi (HTTP 200 pour
`temperature: "chaud"` ou `compute_device: 42`), et la valeur faisait ensuite
échouer chaque appel au modèle. Désormais chaque réglage connu a un type et des
bornes ; une clé inconnue (héritée d'une ancienne version) est ignorée.
"""
import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users


@pytest.fixture
def client(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", "Secret-01", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    c.pid = pid
    return c


@pytest.mark.parametrize("patch, champ", [
    ({"temperature": "chaud"}, "temperature"),
    ({"temperature": 3}, "temperature"),
    ({"temperature": True}, "temperature"),
    ({"compute_device": 42}, "compute_device"),
    ({"compute_device": "tpu"}, "compute_device"),
    ({"reasoning_style": "bavard"}, "reasoning_style"),
    ({"tone": None}, "tone"),
    ({"search_provider": "google"}, "search_provider"),
    ({"simple_mode": "oui"}, "simple_mode"),
    ({"ocr_enabled": 1}, "ocr_enabled"),
    ({"system_prompt": 12}, "system_prompt"),
    ({"system_prompt": "x" * 4001}, "system_prompt"),
    ({"searxng_url": "localhost:8888"}, "searxng_url"),
    ({"connectors": "imap"}, "connectors"),
    ({"connectors": {"imap": {"enabled": "true"}}}, "connectors.imap.enabled"),
    ({"connectors": {"imap": {"host": ["a"]}}}, "connectors.imap.host"),
])
def test_valeur_invalide_refusee_avec_le_nom_du_champ(client, patch, champ):
    avant = client.get("/api/settings").json()
    r = client.put("/api/settings", json=patch)
    assert r.status_code == 400
    assert champ in r.json()["detail"]
    assert client.get("/api/settings").json() == avant        # rien d'enregistré


def test_renvoyer_tous_les_reglages_lus_reste_accepte(client):
    # Exactement ce que fait l'interface à chaque « Enregistrer ».
    reglages = client.get("/api/settings").json()
    r = client.put("/api/settings", json=reglages)
    assert r.status_code == 200, r.text


def test_valeurs_valides_enregistrees(client):
    r = client.put("/api/settings", json={
        "temperature": 1, "compute_device": "cpu", "reasoning_style": "concise",
        "tone": "formal", "search_provider": "searxng", "simple_mode": False,
        "searxng_url": "http://localhost:8888", "system_prompt": "Réponds en français.",
        "connectors": {"imap": {"enabled": True, "host": "imap.exemple.fr"}},
    })
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["temperature"] == 1.0 and corps["compute_device"] == "cpu"
    assert corps["connectors"]["imap"]["host"] == "imap.exemple.fr"


def test_mode_leger_accepte(client):
    r = client.put("/api/settings", json={"compute_device": "leger"})
    assert r.status_code == 200 and r.json()["compute_device"] == "leger"


def test_theme_suit_le_systeme_par_defaut(client):
    assert client.get("/api/settings").json()["theme"] == "systeme"


def test_theme_clair_accepte_et_relu(client):
    r = client.put("/api/settings", json={"theme": "clair"})
    assert r.status_code == 200 and r.json()["theme"] == "clair"
    assert client.get("/api/settings").json()["theme"] == "clair"


@pytest.mark.parametrize("valeur", ["rose", 42])
def test_theme_invalide_refuse(client, valeur):
    """Un thème inconnu ou non textuel est refusé comme les autres choix."""
    r = client.put("/api/settings", json={"theme": valeur})
    assert r.status_code == 400
    assert "theme" in r.json()["detail"]
    assert client.get("/api/settings").json()["theme"] == "systeme"


def test_outils_actifs_par_defaut_et_booleen(client):
    """Boucle d'outils du chat : active par défaut, et un vrai booléen exigé
    (« non » serait vrai en Python et laisserait les outils actifs)."""
    assert client.get("/api/settings").json()["outils_actifs"] is True
    for valeur in ("non", 0, None):
        r = client.put("/api/settings", json={"outils_actifs": valeur})
        assert r.status_code == 400 and "outils_actifs" in r.json()["detail"]
    r = client.put("/api/settings", json={"outils_actifs": False})
    assert r.status_code == 200 and r.json()["outils_actifs"] is False
    assert settings.reglages(client.pid).get()["outils_actifs"] is False


def test_cle_inconnue_ignoree_sans_bloquer_l_enregistrement(client):
    # Clés d'anciennes versions renvoyées par l'interface : ignorées, pas refusées.
    r = client.put("/api/settings", json={
        "temperature": 0.3,
        "ancien_reglage": "x",
        "docgen_template_path": "C:/ailleurs/modele.docx",
        "connectors": {"gmail_oauth": {"enabled": True}, "imap": {"inconnu": 1}},
    })
    assert r.status_code == 200, r.text
    corps = r.json()
    assert corps["temperature"] == 0.3
    assert "ancien_reglage" not in corps and "docgen_template_path" not in corps
    assert "gmail_oauth" not in corps["connectors"]
    assert "inconnu" not in corps["connectors"]["imap"]


def test_secret_masque_renvoye_ne_remplace_pas_le_vrai(client):
    client.put("/api/settings", json={"connectors": {"imap": {"password": "Vrai-MDP-1"}}})
    lus = client.get("/api/settings").json()
    assert lus["connectors"]["imap"]["password"] == "••••••••"
    assert client.put("/api/settings", json=lus).status_code == 200
    vrais = settings.reglages(client.pid).get()
    assert vrais["connectors"]["imap"]["password"] == "Vrai-MDP-1"


def _coffre_simule(monkeypatch):
    """Chiffrement actif, DPAPI remplacé par une transformation réversible
    (vrai DPAPI : tests/test_coffre.py, sous Windows)."""
    from backend import coffre
    monkeypatch.setattr(coffre, "actif", lambda: True)
    monkeypatch.setattr(coffre, "_proteger", lambda b: b"SIM" + b[::-1])

    def deproteger(b):
        if not b.startswith(b"SIM"):
            raise coffre.SecretIllisible("simulé")
        return b[3:][::-1]
    monkeypatch.setattr(coffre, "_deproteger", deproteger)


def test_secret_chiffre_reste_masque_et_utilisable(client, monkeypatch):
    """Lot 4d : chiffré sur disque, masqué dans l'API, en clair pour le backend."""
    _coffre_simule(monkeypatch)
    client.put("/api/settings", json={"search_brave_api_key": "Cle-Brave-9",
                                      "connectors": {"imap": {"password": "Vrai-MDP-1"}}})
    fichier = profiles.profile_dir(client.pid) / "settings.json"
    texte = fichier.read_text(encoding="utf-8")
    assert "Vrai-MDP-1" not in texte and "Cle-Brave-9" not in texte
    lus = client.get("/api/settings").json()
    assert lus["connectors"]["imap"]["password"] == "••••••••"
    assert lus["search_brave_api_key"] == "••••••••"
    assert client.put("/api/settings", json=lus).status_code == 200
    vrais = settings.reglages(client.pid).get()
    assert vrais["connectors"]["imap"]["password"] == "Vrai-MDP-1"
    assert vrais["search_brave_api_key"] == "Cle-Brave-9"


def test_secret_illisible_ne_bloque_pas_les_reglages(client, monkeypatch):
    """Fichier copié d'un autre compte Windows : jamais d'erreur 500."""
    fichier = profiles.profile_dir(client.pid) / "settings.json"
    fichier.parent.mkdir(parents=True, exist_ok=True)
    fichier.write_text('{"connectors": {"imap": {"password": "dpapi:v1:AAAA"}}}',
                       encoding="utf-8")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    r = client.get("/api/settings")
    assert r.status_code == 200
    assert r.json()["connectors"]["imap"]["password"] == ""
    assert settings.reglages(client.pid).secrets_a_ressaisir() == ["connectors.imap.password"]
