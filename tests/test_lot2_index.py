"""
Index sémantique : ne purger que ce qui a réellement été balayé (audit du
15/11/2026, lot 2, point 12).

Le défaut : à la fin d'une construction, tout fichier de l'index non revu
pendant le balayage était retiré. Or le balayage peut être partiel : un seul
sous-dossier (`POST /api/docindex/build?path=r0/sous-dossier`), ou une racine
absente (clé USB débranchée au démarrage) que `main.get_fs_root_entries` saute
en silence. L'indexation automatique effaçait alors tous les extraits de la clé,
qu'il fallait revectoriser (lent).

Le modèle d'embeddings est simulé (pas d'Ollama) ; FAISS est réel. Tout se
passe dans un dossier temporaire.
"""
import pytest
from fastapi.testclient import TestClient

from backend import docindex, documents, main, profiles, sessions, settings, users, zones

pytestmark = pytest.mark.skipif(not docindex.FAISS_DISPONIBLE, reason="faiss absent")


def _faux_embed(textes, _client, premier_appel=False):
    return [[1.0] + [0.0] * (docindex.EMBED_DIM - 1) for _ in textes]


def _ecrire(dossier, nom, mot):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / nom).write_text(f"{mot} " * 20, encoding="utf-8")


def _fichiers(*dossiers):
    sortie = []
    for dossier in dossiers:
        for chemin in sorted(dossier.rglob("*.txt")):
            sortie.append((chemin, f"r0/{chemin.name}"))
    return sortie


def _cles(pid):
    _index, meta = docindex._charger(pid, depuis_disque=True)
    return set((meta or {}).get("files") or {})


@pytest.fixture
def org(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(docindex, "_embed", _faux_embed)
    cle = tmp_path / "cle-usb"
    bureau = tmp_path / "bureau"
    _ecrire(cle, "eleves.txt", "ELEVES")
    _ecrire(bureau, "budget.txt", "BUDGET")
    _ecrire(bureau / "conseils", "conseil.txt", "CONSEIL")
    pid = profiles.create_profile("Org")["id"]
    return pid, cle.resolve(), bureau.resolve()


def test_racine_absente_garde_ses_extraits(org):
    """Clé USB débranchée : sa racine n'est pas balayée, ses extraits restent."""
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    eleves = str(cle / "eleves.txt")
    assert eleves in _cles(pid)

    # Démarrage suivant, clé débranchée : seule la racine « bureau » est balayée.
    docindex.construire_index(pid, _fichiers(bureau), dossiers_balayes=[bureau])
    assert eleves in _cles(pid)


def test_balayage_d_un_sous_dossier_garde_le_reste(org):
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    avant = _cles(pid)
    assert len(avant) == 3

    sous_dossier = bureau / "conseils"
    docindex.construire_index(pid, _fichiers(sous_dossier), dossiers_balayes=[sous_dossier])
    assert _cles(pid) == avant


def test_fichier_supprime_dans_un_dossier_balaye_est_retire(org):
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    (bureau / "budget.txt").unlink()

    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    cles = _cles(pid)
    assert str(bureau / "budget.txt") not in cles
    assert str(bureau / "conseils" / "conseil.txt") in cles
    assert str(cle / "eleves.txt") in cles


def test_fichier_supprime_dans_le_sous_dossier_balaye_est_retire(org):
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    sous_dossier = bureau / "conseils"
    (sous_dossier / "conseil.txt").unlink()

    docindex.construire_index(pid, _fichiers(sous_dossier), dossiers_balayes=[sous_dossier])
    cles = _cles(pid)
    assert str(sous_dossier / "conseil.txt") not in cles
    assert str(bureau / "budget.txt") in cles


def test_dossier_disparu_pendant_le_balayage_n_est_pas_purge(org):
    """La clé est débranchée PENDANT l'indexation : son parcours a rendu une liste
    vide (os.walk ignore l'erreur), ce qui ne prouve pas que ses documents ont été
    supprimés."""
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    for f in cle.iterdir():
        f.unlink()
    cle.rmdir()

    docindex.construire_index(pid, _fichiers(bureau), dossiers_balayes=[cle, bureau])
    assert str(cle / "eleves.txt") in _cles(pid)


def test_sans_liste_de_dossiers_rien_n_est_purge(org):
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle, bureau), dossiers_balayes=[cle, bureau])
    docindex.construire_index(pid, _fichiers(bureau))
    assert str(cle / "eleves.txt") in _cles(pid)


def test_texte_incomplet_est_retente(org, monkeypatch):
    """Un OCR interrompu ne doit pas être figé par l'index (date et taille
    inchangées) : le document est retenté à la construction suivante."""
    pid, cle, bureau = org
    appels = []
    complet = {"valeur": False}

    def fausse_extraction(_pid, chemin):
        appels.append(chemin.name)
        return ("PARTIEL " * 10, {"ocr": True, "notice": "", "complet": complet["valeur"]})

    monkeypatch.setattr(documents, "extract_text_meta", fausse_extraction)
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    assert appels == ["eleves.txt", "eleves.txt"]

    complet["valeur"] = True
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    assert appels == ["eleves.txt"] * 3        # complet : plus de nouvel essai


def test_echec_de_lecture_garde_la_version_indexee(org, monkeypatch):
    """Un document modifié mais momentanément illisible (verrouillé par Word)
    n'efface pas sa version déjà indexée."""
    pid, cle, bureau = org
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    eleves = cle / "eleves.txt"
    eleves.write_text("ELEVES modifie " * 20, encoding="utf-8")
    monkeypatch.setattr(documents, "extract_text_meta",
                        lambda _pid, _chemin: ("", {"ocr": False, "notice": "",
                                                    "complet": False}))
    docindex.construire_index(pid, _fichiers(cle), dossiers_balayes=[cle])
    assert str(eleves) in _cles(pid)


# ---------- Bout en bout : la route et la racine absente ----------
@pytest.fixture
def client(tmp_path, monkeypatch, org):
    pid, cle, bureau = org
    monkeypatch.setattr(users, "USERS_PATH", tmp_path / "profiles" / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", tmp_path / "profiles" / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    monkeypatch.setattr(docindex, "_modele_disponible", lambda: True)
    zones.dossiers_reserves.cache_clear()
    users.create_user("marie", "Secret-01", pid)
    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    assert c.put("/api/settings",
                 json={"fs_roots": [str(cle), str(bureau)]}).status_code == 200
    c.pid, c.cle, c.bureau = pid, cle, bureau
    yield c
    zones.dossiers_reserves.cache_clear()


def _attendre_fin(pid):
    verrou = docindex._verrou_construction(pid)
    assert verrou.acquire(timeout=20), "la construction ne s'est pas terminée"
    verrou.release()


def test_route_cle_debranchee_garde_ses_extraits(client, tmp_path):
    assert client.post("/api/docindex/build").json()["demarree"]
    _attendre_fin(client.pid)
    eleves = str(client.cle / "eleves.txt")
    assert eleves in _cles(client.pid)

    # La clé est « débranchée » : la racine n'existe plus, get_fs_root_entries la
    # saute et seule « bureau » est balayée.
    client.cle.rename(tmp_path / "ailleurs")
    assert client.post("/api/docindex/build").json()["demarree"]
    _attendre_fin(client.pid)
    assert eleves in _cles(client.pid)


def test_route_sous_dossier_garde_le_reste(client):
    assert client.post("/api/docindex/build").json()["demarree"]
    _attendre_fin(client.pid)
    avant = _cles(client.pid)
    (client.bureau / "budget.txt").unlink()        # hors du sous-dossier balayé

    r = client.post("/api/docindex/build", params={"path": "r1/conseils"})
    assert r.json()["demarree"]
    _attendre_fin(client.pid)
    assert _cles(client.pid) == avant


def test_route_balayage_complet_retire_le_fichier_supprime(client):
    assert client.post("/api/docindex/build").json()["demarree"]
    _attendre_fin(client.pid)
    (client.bureau / "budget.txt").unlink()
    assert client.post("/api/docindex/build").json()["demarree"]
    _attendre_fin(client.pid)
    assert str(client.bureau / "budget.txt") not in _cles(client.pid)
