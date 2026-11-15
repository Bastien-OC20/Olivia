"""
Réglages communs à tous les tests du backend.

Le cache OCR (`ocr.DOSSIER_CACHE`) est calculé au chargement du module, à partir
du dossier des données du poste : sans redirection, tout test qui appelle
`POST /api/privacy/delete` ou qui extrait le texte d'une image lisait et purgeait
le VRAI cache de développement (texte reconnu sur des documents personnels).
Chaque test reçoit donc un cache vide, dans son dossier temporaire.
"""
import pytest

from backend import ocr


@pytest.fixture(autouse=True)
def cache_ocr_temporaire(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "DOSSIER_CACHE", tmp_path / "ocr_cache_test")
