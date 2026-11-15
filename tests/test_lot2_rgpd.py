"""
Effacement RGPD incomplet (audit du 15/11/2026, lot 2, point 15).

  - le cache OCR, commun au poste, n'était purgé que sous les racines
    configurées AU MOMENT de l'effacement : une racine retirée des Paramètres
    (ou une clé débranchée) avant l'effacement gardait son texte reconnu ;
  - le cache mémoire de la recherche par mots-clés n'était jamais vidé ;
  - un `.tmp` laissé par un plantage pendant l'écriture d'une conversation ou
    d'un tableau survivait à l'effacement ;
  - un message dont `content` n'est pas une chaîne faisait planter la création
    d'une conversation (erreur 500).

Tesseract est simulé ; le cache OCR vit dans un dossier temporaire.
"""
import json
import subprocess

import pytest
from fastapi.testclient import TestClient

from backend import (conversations, docindex, docsearch, main, ocr, profiles, sessions,
                     settings, tableaux, users, zones)


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    # Jamais le vrai cache OCR du poste.
    monkeypatch.setattr(ocr, "DOSSIER_CACHE", tmp_path / "ocr_cache")
    monkeypatch.setattr(ocr, "chemin_moteur", lambda _pid: tmp_path / ocr.NOM_EXE)
    monkeypatch.setattr(ocr.subprocess, "run", lambda args, **_k: subprocess.CompletedProcess(
        args, 0, "Liste des élèves boursiers".encode("utf-8"), b""))
    monkeypatch.setattr(docindex, "_modele_disponible", lambda: False)
    zones.dossiers_reserves.cache_clear()
    docsearch.vider_cache()

    clients = {}
    for nom in ("alice", "bruno"):
        pid = profiles.create_profile(f"Org {nom}")["id"]
        users.create_user(nom, "Secret-01", pid)
        c = TestClient(main.app)
        assert c.post("/api/auth/login",
                      json={"username": nom, "password": "Secret-01"}).status_code == 200
        c.pid = pid
        clients[nom] = c
    commun = tmp_path / "commun"
    commun.mkdir()
    image = commun / "boursiers.png"
    image.write_bytes(b"\x89PNG faux")
    yield {"tmp": tmp_path, "commun": commun, "image": image, **clients}
    zones.dossiers_reserves.cache_clear()
    docsearch.vider_cache()


def _entrees():
    return [json.loads(f.read_text(encoding="utf-8")) for f in ocr.DOSSIER_CACHE.glob("*.json")]


def test_racine_retiree_avant_l_effacement_texte_reconnu_purge(env):
    alice = env["alice"]
    assert alice.put("/api/settings", json={"fs_roots": [str(env["commun"])]}).status_code == 200
    assert ocr.texte_image(alice.pid, env["image"]).texte == "Liste des élèves boursiers"
    assert len(_entrees()) == 1

    # Le dossier est retiré des Paramètres, PUIS l'effacement est demandé.
    autre = env["tmp"] / "autre"
    autre.mkdir()
    assert alice.put("/api/settings", json={"fs_roots": [str(autre)]}).status_code == 200
    r = alice.post("/api/privacy/delete")
    assert r.status_code == 200
    assert r.json()["ocr_cache_removed"] == 1
    assert _entrees() == []


def test_entree_partagee_conservee_pour_l_autre_organisation(env):
    alice, bruno = env["alice"], env["bruno"]
    ocr.texte_image(alice.pid, env["image"])          # calculée pour Alice…
    ocr.texte_image(bruno.pid, env["image"])          # … servie à Bruno
    assert sorted(_entrees()[0]["profils"]) == sorted([alice.pid, bruno.pid])

    assert alice.post("/api/privacy/delete").status_code == 200
    entrees = _entrees()
    assert len(entrees) == 1 and entrees[0]["profils"] == [bruno.pid]

    assert bruno.post("/api/privacy/delete").status_code == 200
    assert _entrees() == []


def test_entree_d_une_autre_organisation_intacte(env):
    alice, bruno = env["alice"], env["bruno"]
    ocr.texte_image(bruno.pid, env["image"])
    assert alice.post("/api/privacy/delete").json()["ocr_cache_removed"] == 0
    assert _entrees()[0]["profils"] == [bruno.pid]


def test_entrees_anciennes_et_tmp_supprimees(env):
    ocr.DOSSIER_CACHE.mkdir(parents=True)
    (ocr.DOSSIER_CACHE / "ancienne.json").write_text(
        json.dumps({"texte": "ancien", "source_path": str(env["tmp"] / "ailleurs" / "x.pdf")}),
        encoding="utf-8")
    (ocr.DOSSIER_CACHE / "coupure.tmp").write_text("{\"texte\": \"partiel\"",
                                                   encoding="utf-8")
    assert env["alice"].post("/api/privacy/delete").status_code == 200
    assert list(ocr.DOSSIER_CACHE.iterdir()) == []


def test_cache_memoire_de_la_recherche_purge(env):
    alice, bruno = env["alice"], env["bruno"]
    texte = env["commun"] / "note.txt"
    texte.write_text("Conseil de classe", encoding="utf-8")
    st = texte.stat()
    docsearch._texte_indexe(alice.pid, texte, st.st_mtime_ns, st.st_size)
    seul_alice = env["commun"] / "privé.txt"
    seul_alice.write_text("Dossier médical", encoding="utf-8")
    st2 = seul_alice.stat()
    docsearch._texte_indexe(alice.pid, seul_alice, st2.st_mtime_ns, st2.st_size)
    docsearch._texte_indexe(bruno.pid, texte, st.st_mtime_ns, st.st_size)

    assert alice.post("/api/privacy/delete").status_code == 200
    restant = {cle[0]: valeur[3] for cle, valeur in docsearch._cache.items()}
    assert str(seul_alice) not in restant
    assert restant[str(texte)] == {bruno.pid}


def test_fichiers_tmp_des_conversations_et_tableaux_supprimes(env):
    alice = env["alice"]
    alice.post("/api/conversations", json={"messages": [{"role": "user", "content": "x"}]})
    dossier_conv = profiles.profile_dir(alice.pid) / conversations.SOUS_DOSSIER
    (dossier_conv / "0123.tmp").write_text("{\"messages\": [\"secret\"", encoding="utf-8")
    (dossier_conv / "a-garder.txt").write_text("rien à voir", encoding="utf-8")

    assert alice.post("/api/tableaux", json={"titre": "Plan"}).status_code == 200
    dossier_tab = profiles.profile_dir(alice.pid) / tableaux.SOUS_DOSSIER
    (dossier_tab / "4567.tmp").write_text("{\"elements\": [", encoding="utf-8")

    r = alice.post("/api/privacy/delete").json()
    assert r["conversations_removed"] == 1 and r["tableaux_removed"] == 1
    assert sorted(p.name for p in dossier_conv.iterdir()) == ["a-garder.txt"]
    assert list(dossier_tab.iterdir()) == []


def test_supprimer_tout_directement(env):
    pid = env["alice"].pid
    conversations.create_conversation(pid, messages=[])
    dossier = profiles.profile_dir(pid) / conversations.SOUS_DOSSIER
    (dossier / "reste.tmp").write_text("x", encoding="utf-8")
    assert conversations.delete_all_conversations(pid) == 1
    assert list(dossier.iterdir()) == []
    assert tableaux.supprimer_tout(pid) == 0


@pytest.mark.parametrize("contenu", [["morceau"], 12, {"texte": "x"}, None])
def test_titre_avec_contenu_non_texte(env, contenu):
    r = env["alice"].post("/api/conversations",
                          json={"messages": [{"role": "user", "content": contenu},
                                             {"role": "user", "content": "Sortie au musée"}]})
    assert r.status_code == 200
    assert r.json()["title"] == "Sortie au musée"


def test_titre_non_texte_ignore(env):
    r = env["alice"].post("/api/conversations", json={"title": 42, "messages": []})
    assert r.status_code == 200
    assert r.json()["title"] == conversations.TITLE_FALLBACK
    conv_id = r.json()["id"]
    r = env["alice"].put(f"/api/conversations/{conv_id}", json={"title": ["x"]})
    assert r.status_code == 200 and r.json()["title"] == conversations.TITLE_FALLBACK
