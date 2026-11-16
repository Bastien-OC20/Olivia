"""Tests de la boucle d'outils (backend/outils.py), avec un faux contexte :
ni réseau, ni Ollama, ni disque."""
import json

from backend import docgen, outils
from backend.outils import ContexteOutils, executer


def _contexte(**surcharges):
    base = dict(
        chercher=lambda requete: [],
        lire=lambda chemin: "texte",
        mails=None,
        agenda=None,
    )
    base.update(surcharges)
    return ContexteOutils(**base)


def _noms(ctx):
    return [o["function"]["name"] for o in outils.definitions(ctx)]


def _verifier_entete(resultat):
    assert resultat.texte_modele.startswith(outils.ENTETE_RESULTAT)


ARGS_WORD = {"type_document": "courrier", "titre": "Titre", "texte": "Corps"}


# ---------- Définitions ----------

def test_mails_et_agenda_absents_quand_non_configures():
    """Un outil impossible à honorer pousserait le modèle à des appels vains."""
    assert _noms(_contexte()) == [
        "chercher_documents", "lire_document", "proposer_document_word"]


def test_mails_et_agenda_presents_quand_configures():
    """Une boîte ou un agenda configurés doivent être offerts au modèle."""
    ctx = _contexte(mails=lambda n: [], agenda=lambda: [])
    assert sorted(_noms(ctx)) == sorted([
        "chercher_documents", "lire_document", "lister_mails_non_lus",
        "consulter_agenda", "proposer_document_word"])


def test_types_de_document_proposes_viennent_de_docgen():
    """Un type ajouté à docgen.PROFILS doit être proposé sans toucher ici."""
    ctx = _contexte()
    word = [o for o in outils.definitions(ctx)
            if o["function"]["name"] == "proposer_document_word"][0]
    enum = word["function"]["parameters"]["properties"]["type_document"]["enum"]
    assert enum == list(docgen.PROFILS)


# ---------- Recherche ----------

def test_recherche_bornee_a_cinq_resultats_avec_documents_et_extrait_coupe():
    """Une recherche large ne doit pas inonder la fenêtre de contexte."""
    trouves = [{"path": f"r0/d{i}.docx", "name": f"d{i}.docx", "extrait": "x" * 1000}
               for i in range(9)]
    res = executer(_contexte(chercher=lambda r: trouves), "chercher_documents",
                   {"requete": "ca"})
    _verifier_entete(res)
    assert res.etape["etat"] == "fini"
    assert res.etape["resume"] == "5 documents trouvés"
    assert res.etape["documents"][0] == {"path": "r0/d0.docx", "name": "d0.docx"}
    assert len(res.etape["documents"]) == 5
    # Les données tiennent sur la première ligne ; la suivante invite le modèle à
    # lire le document plutôt que de répondre sur un extrait coupé.
    premiere, suite = res.texte_modele[len(outils.ENTETE_RESULTAT):].split("\n", 1)
    donnees = json.loads(premiere)
    assert len(donnees) == 5
    assert len(donnees[0]["extrait"]) <= outils.LONGUEUR_EXTRAIT
    assert "lire_document" in suite


def test_recherche_sans_resultat_dit_aucun_document_trouve():
    """Le modèle ne doit pas inventer un document quand rien n'est trouvé."""
    res = executer(_contexte(), "chercher_documents", {"requete": "zzz"})
    _verifier_entete(res)
    assert res.etape["resume"] == "Aucun document trouvé"
    assert res.etape["documents"] == []


def test_recherche_sans_requete_est_un_echec_lisible():
    """Un appel sans sujet ne doit pas lancer une recherche vide."""
    res = executer(_contexte(), "chercher_documents", {})
    assert res.etape["etat"] == "echec"


# ---------- Lecture ----------

def test_lecture_longue_est_tronquee_et_signalee():
    """Un long document ne doit pas saturer le contexte, et le modèle doit savoir
    qu'il n'en voit que le début."""
    res = executer(_contexte(lire=lambda c: "a" * 20000), "lire_document",
                   {"chemin": "r0/Dossier/CA.docx"})
    _verifier_entete(res)
    assert res.texte_modele.endswith("[tronqué]")
    assert len(res.texte_modele) < len(outils.ENTETE_RESULTAT) + 6100
    assert "tronqué" in res.etape["resume"]
    assert res.etape["documents"] == [{"path": "r0/Dossier/CA.docx", "name": "CA.docx"}]


def test_lecture_courte_n_est_pas_marquee_tronquee():
    """Pas de fausse mention « tronqué » sur un petit document."""
    res = executer(_contexte(lire=lambda c: "Bonjour"), "lire_document",
                   {"chemin": "r0/a.txt"})
    assert "tronqué" not in res.texte_modele
    assert res.etape["resume"] == "Document lu"


def test_lecture_hors_perimetre_echec_sans_chemin_absolu():
    """Un refus de cloisonnement ne doit rien révéler du disque."""
    def lire(chemin):
        raise PermissionError(r"D:\Olivia\backend\profiles\secret.json")
    res = executer(_contexte(lire=lire), "lire_document", {"chemin": "r0/../x"})
    _verifier_entete(res)
    assert res.etape["etat"] == "echec"
    assert "hors des dossiers de travail" in res.etape["resume"]
    assert "Olivia" not in res.texte_modele and "profiles" not in res.texte_modele


def test_lecture_introuvable_ou_illisible_echec_lisible():
    """Fichier absent ou format illisible : message clair, pas de trace."""
    def absent(chemin):
        raise FileNotFoundError(r"C:\x\y")

    def illisible(chemin):
        raise ValueError("zip corrompu /tmp/abc")
    for lire in (absent, illisible):
        res = executer(_contexte(lire=lire), "lire_document", {"chemin": "r0/a.docx"})
        assert res.etape["etat"] == "echec"
        assert "zip" not in res.texte_modele and "\\" not in res.texte_modele


# ---------- Mails ----------

def test_nombre_de_mails_est_borne_et_converti():
    """Le modèle envoie parfois « 5 », 0 ou 99 : on ramène entre 1 et 10."""
    demandes = []

    def mails(n):
        demandes.append(n)
        return []
    ctx = _contexte(mails=mails)
    for valeur in ("5", 0, 99, -3, 4.0, "beaucoup", None, True):
        executer(ctx, "lister_mails_non_lus",
                 {} if valeur is None else {"nombre": valeur})
    assert demandes == [5, 1, 10, 1, 4, 10, 10, 10]


def test_mails_resume_et_extrait_borne():
    """Le début d'un mail est coupé : un mail piégé ne doit pas tout envahir."""
    ctx = _contexte(mails=lambda n: [
        {"from": "a@b.fr", "subject": "S", "date": "d", "snippet": "y" * 2000}] * 2)
    res = executer(ctx, "lister_mails_non_lus", {"nombre": 2})
    _verifier_entete(res)
    assert res.etape["resume"] == "2 mails non lus"
    donnees = json.loads(res.texte_modele[len(outils.ENTETE_RESULTAT):])
    assert len(donnees[0]["snippet"]) <= outils.LONGUEUR_MAIL


def test_boite_mail_injoignable_echec_lisible():
    """Un serveur IMAP en panne ne doit ni planter la boucle ni montrer la trace."""
    def mails(n):
        raise OSError("imap.exemple.fr:993 timed out")
    res = executer(_contexte(mails=mails), "lister_mails_non_lus", {})
    assert res.etape["etat"] == "echec"
    assert "imap" not in res.texte_modele and "993" not in res.texte_modele


def test_mails_non_configures_appel_quand_meme_est_un_echec():
    """Un modèle peut appeler un outil absent des définitions."""
    res = executer(_contexte(), "lister_mails_non_lus", {})
    assert res.etape["etat"] == "echec"


# ---------- Agenda ----------

def test_agenda_borne_a_vingt_evenements():
    """Un agenda chargé ne doit pas saturer le contexte."""
    ctx = _contexte(agenda=lambda: [{"summary": f"E{i}"} for i in range(50)])
    res = executer(ctx, "consulter_agenda", {})
    assert res.etape["resume"] == "20 événements à venir"


def test_agenda_en_erreur_est_un_echec_lisible():
    """Un agenda qui renvoie seulement une erreur n'est pas un agenda vide."""
    res = executer(_contexte(agenda=lambda: [{"error": "403 boom"}]),
                   "consulter_agenda", {})
    assert res.etape["etat"] == "echec"
    assert "403" not in res.texte_modele


# ---------- Proposition ----------

def test_proposition_bornee_et_dite_proposee_pas_creee():
    """Le modèle ne doit jamais laisser croire que le document est créé."""
    res = executer(_contexte(), "proposer_document_word", {
        "type_document": "circulaire", "titre": "T" * 500, "objet": "O" * 500,
        "destinataire": "D" * 500, "texte": "x" * 20000})
    _verifier_entete(res)
    p = res.proposition
    assert p["type"] == "document_word" and p["type_document"] == "circulaire"
    assert len(p["titre"]) <= outils.LONGUEUR_CHAMP_PROPOSITION
    assert len(p["objet"]) <= outils.LONGUEUR_CHAMP_PROPOSITION
    assert len(p["destinataire"]) <= outils.LONGUEUR_CHAMP_PROPOSITION
    assert len(p["texte"]) <= outils.LONGUEUR_TEXTE_PROPOSITION
    assert "PROPOSÉ" in res.texte_modele and "PAS créé" in res.texte_modele
    assert res.etape["etat"] == "fini"


def test_proposition_champs_facultatifs_vides_et_types_stricts():
    """Objet et destinataire absents deviennent des chaînes vides, jamais None."""
    res = executer(_contexte(), "proposer_document_word", ARGS_WORD)
    assert res.proposition["objet"] == "" and res.proposition["destinataire"] == ""


def test_proposition_type_inconnu_refusee_avec_liste_des_types():
    """Un type inventé échouerait au clic ; mieux vaut le refuser au modèle."""
    res = executer(_contexte(), "proposer_document_word",
                   dict(ARGS_WORD, type_document="facture"))
    assert res.proposition is None and res.etape["etat"] == "echec"
    assert "circulaire" in res.texte_modele


def test_proposition_sans_titre_ou_texte_refusee():
    """Pas de document vide proposé à l'utilisatrice."""
    for manque in ("titre", "texte"):
        args = {k: v for k, v in ARGS_WORD.items() if k != manque}
        res = executer(_contexte(), "proposer_document_word", args)
        assert res.proposition is None and res.etape["etat"] == "echec"


# ---------- Robustesse ----------

def test_outil_inconnu_ne_leve_pas():
    """Un modèle peut inventer un outil."""
    res = executer(_contexte(), "supprimer_tout", {})
    _verifier_entete(res)
    assert res.etape["etat"] == "echec"


def test_arguments_non_dict_ne_levent_pas():
    """Des arguments mal formés (texte, liste, nombre) ne doivent rien casser."""
    for args in ("{\"requete\": 1", ["a"], 3):
        res = executer(_contexte(), "chercher_documents", args)
        _verifier_entete(res)
        assert res.etape["etat"] == "echec"


def test_arguments_mal_types_ne_levent_pas():
    """Une requête numérique ou une liste à la place d'une chaîne."""
    for outil, args in (("chercher_documents", {"requete": 12}),
                        ("lire_document", {"chemin": ["r0/a"]}),
                        ("proposer_document_word", {"type_document": 3,
                                                    "titre": None, "texte": {}})):
        res = executer(_contexte(), outil, args)
        assert res.etape["etat"] == "echec"


def test_exception_inattendue_devient_un_echec_lisible():
    """Un bogue dans une fonction injectée ne doit jamais couper le chat."""
    def casse(requete):
        raise RuntimeError("Traceback D:\\Olivia\\x")
    res = executer(_contexte(chercher=casse), "chercher_documents", {"requete": "a"})
    _verifier_entete(res)
    assert res.etape["etat"] == "echec"
    assert "Traceback" not in res.texte_modele and "Olivia" not in res.texte_modele


# ---------- Libellés ----------

def test_libelles_en_francais_et_bornes():
    """Une requête énorme ne doit pas déformer l'interface."""
    assert outils.libelle("chercher_documents", {"requete": "convocation CA"}) \
        == "Recherche dans les documents : « convocation CA »"
    assert outils.libelle("lire_document", {"chemin": "r0/Comptes/CA 2026-10.docx"}) \
        == "Lecture de « CA 2026-10.docx »"
    assert outils.libelle("lister_mails_non_lus", {}) == "Consultation des mails non lus"
    assert outils.libelle("consulter_agenda", None) == "Consultation de l'agenda"
    long = outils.libelle("chercher_documents", {"requete": "m" * 5000})
    assert long.count("…") == 1 and len(long) < 120
    assert outils.libelle("inconnu", "pas un dict")
