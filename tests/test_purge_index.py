"""
Purge RGPD de l'index sémantique pendant une construction (audit, point 8).

Le scénario rejoué : une construction tourne (au démarrage d'Olivia ou après
un import), l'organisation demande l'effacement de ses données, puis la
construction termine son fichier en cours. Auparavant, sa sauvegarde finale
RECRÉAIT l'index qu'on venait d'effacer : un effacement annoncé comme complet,
démenti quelques secondes plus tard.

Le modèle d'embeddings est simulé (pas d'Ollama) ; FAISS est réel. Tout se
passe dans un dossier temporaire.
"""
import threading

import pytest

from backend import docindex, profiles

pytestmark = pytest.mark.skipif(not docindex.FAISS_DISPONIBLE, reason="faiss absent")


@pytest.fixture
def org(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    # Point de sauvegarde après CHAQUE fichier : l'index existe sur disque dès
    # le premier document, comme sur un vrai dossier de plusieurs centaines.
    monkeypatch.setattr(docindex, "CHECKPOINT_FICHIERS", 1)
    docs = tmp_path / "docs"
    docs.mkdir()
    for nom, mot in (("a.txt", "AAA"), ("b.txt", "BBB"), ("c.txt", "CCC")):
        (docs / nom).write_text(f"{mot} " * 20, encoding="utf-8")
    pid = profiles.create_profile("Org")["id"]
    fichiers = [(docs / n, f"r0/{n}") for n in ("a.txt", "b.txt", "c.txt")]
    return pid, fichiers


def _embed_bloquant(sur: str, arrive: threading.Event, continuer: threading.Event):
    """Faux `_embed` : se met en pause sur le document contenant `sur`."""
    def _embed(textes, _client, premier_appel=False):
        if any(sur in t for t in textes):
            arrive.set()
            continuer.wait(timeout=10)
        return [[1.0] + [0.0] * (docindex.EMBED_DIM - 1) for _ in textes]
    return _embed


def _attendre_fin(pid: str) -> None:
    verrou = docindex._verrou_construction(pid)
    assert verrou.acquire(timeout=10), "la construction ne s'est pas terminée"
    verrou.release()


def test_purge_pendant_construction_n_est_pas_annulee(org, monkeypatch):
    pid, fichiers = org
    arrive, continuer = threading.Event(), threading.Event()
    monkeypatch.setattr(docindex, "_embed", _embed_bloquant("BBB", arrive, continuer))

    assert docindex.lancer_construction(pid, iter(fichiers))
    assert arrive.wait(timeout=10)                  # a.txt indexé et sauvé, b.txt en cours
    assert docindex.dossier_index(pid).exists()

    assert docindex.purger_index(pid) is True       # effacement RGPD demandé
    continuer.set()                                 # la construction termine b.txt…
    _attendre_fin(pid)

    # … et ne doit RIEN réécrire.
    assert not docindex.dossier_index(pid).exists()
    assert docindex.rechercher(pid, "AAA")["results"] == []


def test_annulation_ordinaire_conserve_le_travail_fait(org, monkeypatch):
    # Garde-fou : le bouton « Interrompre » garde ce qui est déjà indexé
    # (comportement documenté), seule la purge doit tout effacer.
    pid, fichiers = org
    arrive, continuer = threading.Event(), threading.Event()
    monkeypatch.setattr(docindex, "_embed", _embed_bloquant("BBB", arrive, continuer))

    assert docindex.lancer_construction(pid, iter(fichiers))
    assert arrive.wait(timeout=10)
    docindex.annuler_construction(pid)
    continuer.set()
    _attendre_fin(pid)

    index, meta = docindex._charger(pid, depuis_disque=True)
    assert index is not None and len(meta["files"]) >= 1


def test_construction_apres_purge_fonctionne(org, monkeypatch):
    pid, fichiers = org
    monkeypatch.setattr(docindex, "_embed", _embed_bloquant("rien", threading.Event(),
                                                            threading.Event()))
    docindex.purger_index(pid)
    assert docindex.lancer_construction(pid, iter(fichiers))
    _attendre_fin(pid)
    index, meta = docindex._charger(pid, depuis_disque=True)
    assert index is not None and len(meta["files"]) == 3
