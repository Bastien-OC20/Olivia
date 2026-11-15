"""
Échecs d'OCR mis en cache et cache de recherche figé (audit du 15/11/2026,
lot 2, point 14).

  - un OCR coupé par un délai, par le budget du document ou par une erreur du
    moteur (code retour non nul) était écrit dans le cache disque comme un
    résultat définitif : le document restait introuvable pour toujours ;
  - le cache mémoire de docsearch, keyé (chemin, date, taille), resservait le
    texte VIDE d'un PDF scanné lu sans OCR, même après activation de l'OCR,
    jusqu'au redémarrage.

Tesseract est simulé (remplacement de `subprocess.run`) : ni moteur ni réseau.
"""
import json
import subprocess

import pytest

from backend import docsearch, documents, ocr

P_A = "a" * 32
P_B = "b" * 32


@pytest.fixture
def moteur(tmp_path, monkeypatch):
    """Faux Tesseract : chaque appel consomme la réponse suivante de `reponses`
    (texte, code retour, ou exception à lever)."""
    monkeypatch.setattr(ocr, "DOSSIER_CACHE", tmp_path / "ocr_cache")
    monkeypatch.setattr(ocr, "chemin_moteur", lambda _pid: tmp_path / ocr.NOM_EXE)
    etat = {"reponses": [], "appels": 0}

    def faux_run(args, input=None, capture_output=True, timeout=None, env=None,
                 creationflags=0):
        etat["appels"] += 1
        reponse = etat["reponses"].pop(0)
        if isinstance(reponse, BaseException):
            raise reponse
        if isinstance(reponse, int):
            return subprocess.CompletedProcess(args, reponse, b"", b"erreur")
        return subprocess.CompletedProcess(args, 0, reponse.encode("utf-8"), b"")

    monkeypatch.setattr(ocr.subprocess, "run", faux_run)
    image = tmp_path / "circulaire.png"
    image.write_bytes(b"\x89PNG faux contenu")
    etat["image"] = image
    return etat


def _entree(etat):
    fichiers = list(ocr.DOSSIER_CACHE.glob("*.json"))
    assert len(fichiers) == 1
    return json.loads(fichiers[0].read_text(encoding="utf-8"))


def test_code_retour_non_nul_n_est_pas_un_resultat_definitif(moteur, monkeypatch):
    moteur["reponses"] = [1, "Circulaire de rentrée"]
    premier = ocr.texte_image(P_A, moteur["image"])
    assert premier.texte == "" and premier.complet is False
    assert _entree(moteur)["complet"] is False

    # Pendant le délai de nouvel essai, l'échec est resservi sans relancer le moteur.
    assert ocr.texte_image(P_A, moteur["image"]).complet is False
    assert moteur["appels"] == 1

    # Délai écoulé : recalcul, puis résultat complet mis en cache.
    monkeypatch.setattr(ocr, "RETENTE_ECHEC", 0.0)
    second = ocr.texte_image(P_A, moteur["image"])
    assert second.texte == "Circulaire de rentrée" and second.complet is True
    assert moteur["appels"] == 2
    assert ocr.texte_image(P_A, moteur["image"]).texte == "Circulaire de rentrée"
    assert moteur["appels"] == 2                  # complet : servi depuis le cache


def test_delai_depasse_n_est_pas_fige(moteur, monkeypatch):
    monkeypatch.setattr(ocr, "RETENTE_ECHEC", 0.0)
    moteur["reponses"] = [subprocess.TimeoutExpired("tesseract", 25), "Texte reconnu"]
    assert ocr.texte_image(P_A, moteur["image"]).complet is False
    assert ocr.texte_image(P_A, moteur["image"]).texte == "Texte reconnu"


def test_entree_ancienne_sans_marqueur_est_recalculee(moteur):
    """Les entrées écrites avant ce correctif peuvent être des échecs figés."""
    moteur["reponses"] = ["Texte reconnu"]
    cle = ocr._cle(moteur["image"])
    ocr.DOSSIER_CACHE.mkdir(parents=True)
    (ocr.DOSSIER_CACHE / f"{cle}.json").write_text(
        json.dumps({"texte": "", "pages": 0, "notice": "", "source_path": "x"}),
        encoding="utf-8")
    assert ocr.texte_image(P_A, moteur["image"]).texte == "Texte reconnu"
    entree = _entree(moteur)
    assert entree["complet"] is True and entree["profils"] == [P_A]


def test_budget_pdf_depasse_resultat_incomplet(moteur, tmp_path, monkeypatch):
    pdfium = pytest.importorskip("pypdfium2")
    document = pdfium.PdfDocument.new()
    document.new_page(200, 200)
    chemin = tmp_path / "scan.pdf"
    document.save(str(chemin))
    document.close()
    monkeypatch.setattr(ocr, "BUDGET_DOCUMENT", -1.0)   # coupe avant la première page
    resultat = ocr.texte_pdf(P_A, chemin)
    assert resultat is not None and resultat.complet is False
    assert "interrompue" in resultat.notice
    assert _entree(moteur)["complet"] is False


def test_extraction_signale_l_ocr_incomplet(moteur, monkeypatch):
    monkeypatch.setattr(documents, "ocr_actif", lambda _pid: True)
    moteur["reponses"] = [1]
    _texte, meta = documents.extract_text_meta(P_A, moteur["image"])
    assert meta["complet"] is False


def test_extraction_sans_moteur_est_incomplete(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "DOSSIER_CACHE", tmp_path / "ocr_cache")
    monkeypatch.setattr(ocr, "chemin_moteur", lambda _pid: None)
    monkeypatch.setattr(documents, "ocr_actif", lambda _pid: True)
    image = tmp_path / "fax.png"
    image.write_bytes(b"\x89PNG")
    texte, meta = documents.extract_text_meta(P_A, image)
    assert texte == "" and meta["complet"] is False


# ---------- Cache mémoire de docsearch ----------
@pytest.fixture
def extraction(tmp_path, monkeypatch):
    """Fausse extraction : compte les appels ; l'OCR suit `etat["ocr"]`."""
    docsearch.vider_cache()
    etat = {"ocr": False, "complet": True, "appels": 0}

    def fausse_extraction(_pid, _chemin):
        etat["appels"] += 1
        texte = "Convocation reconnue" if etat["ocr"] else ""
        return texte, {"ocr": etat["ocr"], "notice": "", "complet": etat["complet"]}

    monkeypatch.setattr(documents, "extract_text_meta", fausse_extraction)
    monkeypatch.setattr(documents, "ocr_actif", lambda _pid: etat["ocr"])
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    etat["pdf"] = pdf
    yield etat
    docsearch.vider_cache()


def _texte(pid, chemin):
    st = chemin.stat()
    return docsearch._texte_indexe(pid, chemin, st.st_mtime_ns, st.st_size)[0]


def test_activer_l_ocr_invalide_le_texte_vide_en_cache(extraction):
    assert _texte(P_A, extraction["pdf"]) == ""
    assert _texte(P_A, extraction["pdf"]) == ""
    assert extraction["appels"] == 1               # OCR désactivé : mis en cache

    extraction["ocr"] = True                       # l'utilisatrice active l'OCR
    assert _texte(P_A, extraction["pdf"]) == "Convocation reconnue"
    assert extraction["appels"] == 2


def test_texte_incomplet_jamais_mis_en_cache(extraction):
    extraction["ocr"] = True
    extraction["complet"] = False
    _texte(P_A, extraction["pdf"])
    _texte(P_A, extraction["pdf"])
    assert extraction["appels"] == 2


def test_une_organisation_sans_ocr_ne_recoit_pas_le_texte_reconnu_d_une_autre(
        extraction, monkeypatch):
    monkeypatch.setattr(documents, "ocr_actif", lambda pid: pid == P_A)
    extraction["ocr"] = True
    assert _texte(P_A, extraction["pdf"]) == "Convocation reconnue"
    extraction["ocr"] = False
    assert _texte(P_B, extraction["pdf"]) == ""
