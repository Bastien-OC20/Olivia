"""
Calendrier `.ics` : les messages d'erreur ne révèlent pas l'emplacement du fichier.

Le chemin du `.ics` est un réglage de l'organisation. `GET
/api/connectors/calendar/preview`, ouvert à tout compte de l'organisation, le
recopiait pourtant dans ses erreurs (« Fichier .ics introuvable : C:\\… »), et
l'erreur d'analyse reprenait le message brut de l'exception, qui contient lui
aussi le chemin (« [Errno 13] Permission denied: 'C:\\…' »). Un membre y lisait
l'arborescence du poste. Les erreurs doivent rester lisibles, sans chemin.
"""
import json

import pytest
from fastapi.testclient import TestClient

from backend import main, profiles, sessions, settings, users, zones
from backend.connectors import calendar_list_events

ICS_VALIDE = (
    "BEGIN:VCALENDAR\nVERSION:2.0\nPRODID:-//essai//FR\n"
    "BEGIN:VEVENT\nUID:1@essai\nDTSTART:20261119T140000Z\nDTEND:20261119T150000Z\n"
    "SUMMARY:Rendez-vous avec la CPE\nLOCATION:Bureau 3\nEND:VEVENT\n"
    "END:VCALENDAR\n"
)


def _sans_chemin(evenements, dossier) -> None:
    """Aucune trace du dossier (ni sous sa forme brute, ni échappée en JSON)."""
    texte = json.dumps(evenements, ensure_ascii=False)
    for forme in (str(dossier), json.dumps(str(dossier))[1:-1], dossier.name):
        assert forme not in texte, (forme, texte)


@pytest.mark.parametrize("cas", ["absent", "dossier", "illisible"])
def test_les_erreurs_du_calendrier_ne_citent_pas_le_chemin(tmp_path, cas):
    dossier = tmp_path / "Agenda-secret-du-poste"
    dossier.mkdir()
    if cas == "absent":
        chemin = dossier / "agenda.ics"
    elif cas == "dossier":
        chemin = dossier                # ouvrir un dossier lève une erreur qui le cite
    else:
        chemin = dossier / "agenda.ics"
        chemin.write_text("ceci n'est pas un calendrier", encoding="utf-8")
    evenements = calendar_list_events(str(chemin))
    assert len(evenements) == 1 and evenements[0]["error"]
    _sans_chemin(evenements, dossier)


def test_un_calendrier_valide_est_toujours_lu(tmp_path):
    """Non-régression : la correction des messages ne touche pas à la lecture."""
    chemin = tmp_path / "agenda.ics"
    chemin.write_text(ICS_VALIDE, encoding="utf-8")
    evenements = calendar_list_events(str(chemin))
    assert [e["name"] for e in evenements] == ["Rendez-vous avec la CPE"]
    assert evenements[0]["location"] == "Bureau 3"


@pytest.fixture
def membre(tmp_path, monkeypatch):
    """Une organisation : un responsable qui règle le calendrier, un membre qui lit."""
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    zones.dossiers_reserves.cache_clear()
    pid = profiles.create_profile("Org")["id"]
    users.create_user("marie", "Secret-01", pid)       # premier compte : responsable
    users.create_user("paul", "Secret-02", pid)
    responsable, lecteur = TestClient(main.app), TestClient(main.app)
    assert responsable.post("/api/auth/login",
                            json={"username": "marie", "password": "Secret-01"}).status_code == 200
    assert lecteur.post("/api/auth/login",
                        json={"username": "paul", "password": "Secret-02"}).status_code == 200
    yield responsable, lecteur
    zones.dossiers_reserves.cache_clear()


def test_un_membre_ne_lit_pas_le_chemin_du_calendrier_dans_l_apercu(membre, tmp_path):
    responsable, lecteur = membre
    dossier = tmp_path / "Agenda-secret-du-poste"
    dossier.mkdir()
    assert responsable.put("/api/settings", json={"connectors": {"calendar_ics": {
        "enabled": True, "path": str(dossier / "agenda.ics")}}}).status_code == 200
    r = lecteur.get("/api/connectors/calendar/preview")
    assert r.status_code == 200
    evenements = r.json()["events"]
    assert evenements[0]["error"]
    _sans_chemin(evenements, dossier)
