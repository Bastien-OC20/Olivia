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
