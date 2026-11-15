"""
Tailles non bornées et bombes de décompression (audit du 15/11/2026, lot 2,
point 13).

  - l'aperçu lisait le fichier texte ENTIER (`read_bytes`) pour n'en montrer que
    30 000 caractères, dans une route `async` qui figeait tout le serveur ;
  - un .docx / .xlsx est une archive zip : la borne de 10 Mo portait sur la
    taille compressée, et python-docx / openpyxl décompressent chaque partie en
    entier. Quelques kilo-octets de zéros suffisaient à réclamer des gigaoctets.
"""
import inspect
import pathlib
import zipfile

import pytest

from backend import documents, main


def _archive(chemin, membres):
    """Archive zip à membres très compressibles : {nom: taille en octets}."""
    with zipfile.ZipFile(chemin, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for nom, taille in membres.items():
            with z.open(nom, "w", force_zip64=True) as f:
                bloc = b"\0" * (1024 * 1024)
                reste = taille
                while reste > 0:
                    f.write(bloc[:min(reste, len(bloc))])
                    reste -= len(bloc)
    return chemin


@pytest.fixture
def interdire_ouverture(monkeypatch):
    """python-docx et openpyxl ne doivent jamais être appelés sur une archive refusée."""
    docx = pytest.importorskip("docx")
    openpyxl = pytest.importorskip("openpyxl")

    def refuse(*_a, **_k):
        raise AssertionError("archive décompressée alors qu'elle devait être refusée")

    monkeypatch.setattr(docx, "Document", refuse)
    monkeypatch.setattr(openpyxl, "load_workbook", refuse)


def test_bombe_docx_refusee_sans_decompression(tmp_path, interdire_ouverture):
    # Taille réelle au-delà du plafond de production (200 Mo) : le fichier zip ne
    # pèse que quelques centaines de kilo-octets.
    taille = documents.ARCHIVE_MAX_OCTETS_DECOMPRESSES + 1024 * 1024
    bombe = _archive(tmp_path / "bombe.docx", {"word/document.xml": taille})
    assert bombe.stat().st_size < 2 * 1024 * 1024

    assert documents.controler_archive(bombe) == documents.MSG_ARCHIVE_TROP_VOLUMINEUSE
    apercu = documents.preview(bombe, "/api/fs/download?path=r0/bombe.docx")
    assert apercu["kind"] == "error"
    assert "trop volumineux" in apercu["detail"]
    # Recherche et index passent par extract_text_meta : texte vide, sans exception.
    texte, _meta = documents.extract_text_meta("p", bombe)
    assert texte == ""


def test_bombe_xlsx_refusee_sans_decompression(tmp_path, monkeypatch, interdire_ouverture):
    monkeypatch.setattr(documents, "ARCHIVE_MAX_OCTETS_DECOMPRESSES", 4 * 1024 * 1024)
    bombe = _archive(tmp_path / "bombe.xlsx", {"xl/worksheets/sheet1.xml": 3 * 1024 * 1024,
                                               "xl/sharedStrings.xml": 2 * 1024 * 1024})
    apercu = documents.preview(bombe, "/x")
    assert apercu["kind"] == "error" and "trop volumineux" in apercu["detail"]
    assert documents.extract_text("p", bombe) == ""


def test_archive_aux_membres_innombrables_refusee(tmp_path, monkeypatch, interdire_ouverture):
    monkeypatch.setattr(documents, "ARCHIVE_MAX_MEMBRES", 5)
    archive = _archive(tmp_path / "mille.docx", {f"word/p{i}.xml": 10 for i in range(6)})
    assert documents.controler_archive(archive) == documents.MSG_ARCHIVE_TROP_VOLUMINEUSE


def test_faux_docx_refuse_proprement(tmp_path, interdire_ouverture):
    faux = tmp_path / "pas-un-zip.docx"
    faux.write_text("ceci n'est pas une archive", encoding="utf-8")
    apercu = documents.preview(faux, "/x")
    assert apercu["kind"] == "error"
    assert apercu["detail"] == documents.MSG_ARCHIVE_ILLISIBLE
    assert documents.extract_text("p", faux) == ""


def test_vrai_docx_toujours_lisible(tmp_path):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("Convocation au conseil de classe")
    chemin = tmp_path / "convocation.docx"
    doc.save(str(chemin))
    assert documents.controler_archive(chemin) == ""
    assert documents.preview(chemin, "/x")["paragraphs"] == ["Convocation au conseil de classe"]
    assert "Convocation" in documents.extract_text("p", chemin)


# ---------- Aperçu des fichiers texte ----------
def test_apercu_texte_ne_lit_pas_tout_le_fichier(tmp_path, monkeypatch):
    gros = tmp_path / "journal.log"
    gros.write_bytes(b"ligne de journal\n" * 400_000)        # ~6,8 Mo
    lus = []

    class Espion:
        """Fichier ouvert qui compte les octets réellement lus."""

        def __init__(self, *a, **k):
            self.f = open(*a, **k)

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            self.f.close()

        def read(self, n=-1):
            donnees = self.f.read(n)
            lus.append(len(donnees))
            return donnees

    # `open` n'est remplacé que dans le module documents.
    monkeypatch.setattr(documents, "open", Espion, raising=False)
    monkeypatch.setattr(pathlib.Path, "read_bytes",
                        lambda self: (_ for _ in ()).throw(AssertionError("lecture entière")))
    apercu = documents.preview(gros, "/x")
    assert apercu["kind"] == "text"
    assert apercu["truncated"] is True
    assert len(apercu["content"]) == documents.MAX_CHARS
    assert sum(lus) <= documents.APERCU_MAX_OCTETS + 1


def test_apercu_texte_coupe_au_milieu_d_un_accent(tmp_path):
    """La coupure tombe au milieu d'un « é » (2 octets en UTF-8) : le texte ne
    doit pas basculer en cp1252 (« Ã© »)."""
    chemin = tmp_path / "notes.txt"
    chemin.write_text("a" + "é" * documents.APERCU_MAX_OCTETS, encoding="utf-8")
    apercu = documents.preview(chemin, "/x")
    assert "Ã" not in apercu["content"]
    assert apercu["content"].startswith("aéé")
    assert apercu["truncated"] is True


def test_petit_fichier_texte_intact(tmp_path):
    chemin = tmp_path / "court.txt"
    chemin.write_text("Réunion des élèves délégués", encoding="utf-8")
    apercu = documents.preview(chemin, "/x")
    assert apercu == {"kind": "text", "content": "Réunion des élèves délégués",
                      "truncated": False}


def test_apercu_csv_borne_et_cp1252(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "APERCU_CSV_MAX_OCTETS", 1000)
    chemin = tmp_path / "export.csv"
    lignes = ["nom,classe"] + [f"Élève {i},2nde" for i in range(500)]
    chemin.write_bytes("\r\n".join(lignes).encode("cp1252"))
    apercu = documents.preview(chemin, "/x")
    assert apercu["kind"] == "table"
    assert apercu["truncated"] is True
    assert apercu["columns"] == ["nom", "classe"]
    assert apercu["rows"][0] == ["Élève 0", "2nde"]
    # La dernière ligne lue, coupée par la borne, est écartée.
    assert all(len(r) == 2 for r in apercu["rows"])


def test_extraction_texte_bornee(tmp_path, monkeypatch):
    monkeypatch.setattr(documents, "EXTRACT_MAX_CHARS", 100)
    chemin = tmp_path / "long.txt"
    chemin.write_text("x" * 10_000, encoding="utf-8")
    texte, meta = documents.extract_text_meta("p", chemin)
    assert texte == "x" * 100
    assert meta["complet"] is True


def test_extraction_en_echec_est_marquee_incomplete(tmp_path, monkeypatch):
    chemin = tmp_path / "verrouille.txt"
    chemin.write_text("contenu", encoding="utf-8")

    def verrouille(*_a, **_k):
        raise PermissionError("fichier ouvert dans Word")

    monkeypatch.setattr(documents, "read_text_file", verrouille)
    texte, meta = documents.extract_text_meta("p", chemin)
    assert texte == "" and meta["complet"] is False


# ---------- Routes ----------
def test_routes_bloquantes_synchrones():
    """Une route async qui lit le disque fige tout le serveur, chat compris."""
    assert not inspect.iscoroutinefunction(main.fs_preview)
    assert not inspect.iscoroutinefunction(main.privacy_delete)
