"""
Boucle d'outils du chat (`POST /api/chat/stream`, voir backend/outils.py).

Le modèle GPU consulte de lui-même, en lecture seule, les documents de
l'organisation (et ses mails, son agenda), et peut PROPOSER un document Word.
Ces tests garantissent :
- qu'un seul `done` parvient à l'interface (Ollama en envoie un à la fin de
  CHAQUE tour, et l'interface s'arrête au premier reçu) ;
- que les outils restent cloisonnés à l'organisation de la session (aucun
  contenu ni chemin absolu d'ailleurs dans le flux) ;
- qu'une proposition ne crée aucun fichier ;
- que la boucle est bornée ;
- qu'hors des conditions d'activation, le chat est exactement celui d'avant.

Ollama est simulé (httpx.MockTransport) en distinguant `/api/show` (capacités)
et `/api/chat` (une réponse NDJSON par tour). Rien n'est écrit hors de tmp_path.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import docsearch, main, outils, profiles, sessions, settings, users, zones

MODELE = "ministral-3:8b"
DEMANDE = {"model": MODELE, "messages": [{"role": "user", "content": "Quand a lieu le CA ?"}]}

CONVOCATION = "Convocation au conseil d'administration du 12 décembre. Ordre du jour : budget."
SECRET_B = "SECRET-ORGANISATION-B"
HORS_PERIMETRE = "CONTENU-HORS-PERIMETRE"


@pytest.fixture
def env(tmp_path, monkeypatch):
    dossier = tmp_path / "profiles"
    monkeypatch.setattr(profiles, "PROFILES_DIR", dossier)
    monkeypatch.setattr(profiles, "REGISTRY_PATH", dossier / "registry.json")
    monkeypatch.setattr(users, "USERS_PATH", dossier / "users.json")
    monkeypatch.setattr(sessions, "SESSIONS_PATH", dossier / "sessions.json")
    monkeypatch.setattr(settings, "registry", settings.SettingsRegistry())
    # Caches de module qui survivent d'un test à l'autre.
    monkeypatch.setattr(main, "_capacites_outils", {})
    zones.dossiers_reserves.cache_clear()
    docsearch.vider_cache()

    docs = tmp_path / "docs_a"
    docs.mkdir()
    (docs / "convocation.txt").write_text(CONVOCATION, encoding="utf-8")
    (docs / "cantine.txt").write_text("Note interne sur la cantine.", encoding="utf-8")
    docs_b = tmp_path / "docs_b"
    docs_b.mkdir()
    (docs_b / "secret_b.txt").write_text(SECRET_B, encoding="utf-8")
    hors = tmp_path / "hors"
    hors.mkdir()
    (hors / "hors.txt").write_text(HORS_PERIMETRE, encoding="utf-8")

    pid = profiles.create_profile("Org A")["id"]
    users.create_user("marie", "Secret-01", pid)
    pid_b = profiles.create_profile("Org B")["id"]
    settings.reglages(pid_b).update({"fs_roots": [{"path": str(docs_b), "label": ""}]})

    c = TestClient(main.app)
    assert c.post("/api/auth/login",
                  json={"username": "marie", "password": "Secret-01"}).status_code == 200
    # Le périphérique d'un profil neuf est détecté sur le poste : on le fixe.
    r = c.put("/api/settings", json={"fs_roots": [str(docs)], "compute_device": "gpu",
                                     "temperature": 0.7})
    assert r.status_code == 200, r.text
    yield {"client": c, "pid": pid, "docs": docs, "docs_b": docs_b, "hors": hors,
           "tmp": tmp_path}
    zones.dossiers_reserves.cache_clear()
    docsearch.vider_cache()


# ---------- Ollama simulé ----------
class FauxOllama:
    """`tours` : une réponse par requête `/api/chat` (la dernière est répétée).
    Chaque réponse est une liste de morceaux (dict, ou texte brut pour une ligne
    invalide), une `httpx.Response`, ou une exception à lever."""

    def __init__(self, tours, capacites=("completion", "tools"), statut_show=200):
        self.tours = tours
        self.capacites = list(capacites)
        self.statut_show = statut_show
        self.chats: list[dict] = []
        self.shows: list[dict] = []

    def __call__(self, requete):
        corps = json.loads(requete.content)
        if requete.url.path == "/api/show":
            self.shows.append(corps)
            if self.statut_show != 200:
                return httpx.Response(self.statut_show, json={"error": "panne"})
            return httpx.Response(200, json={"capabilities": self.capacites})
        assert requete.url.path == "/api/chat", requete.url
        self.chats.append(corps)
        reponse = self.tours[min(len(self.chats), len(self.tours)) - 1]
        if isinstance(reponse, Exception):
            raise reponse
        if isinstance(reponse, httpx.Response):
            return reponse
        lignes = [m if isinstance(m, str) else json.dumps(m, ensure_ascii=False)
                  for m in reponse]
        return httpx.Response(200, text="\n".join(lignes) + "\n")


def _brancher(monkeypatch, faux):
    vrai = httpx.AsyncClient

    class _Client(vrai):
        def __init__(self, *a, **k):
            k["transport"] = httpx.MockTransport(faux)
            super().__init__(*a, **k)
    monkeypatch.setattr(main.httpx, "AsyncClient", _Client)
    return faux


def appel(nom, **arguments):
    return {"message": {"role": "assistant", "content": "",
                        "tool_calls": [{"function": {"name": nom, "arguments": arguments}}]},
            "done": False}


def texte(t):
    return {"message": {"role": "assistant", "content": t}, "done": False}


def fin(t=""):
    return {"message": {"role": "assistant", "content": t}, "done": True, "done_reason": "stop"}


def _evenements(reponse) -> list[dict]:
    """Charges des lignes `data:` du flux SSE, en exigeant du JSON valide."""
    lignes = [ligne[5:].strip() for ligne in reponse.text.splitlines()
              if ligne.startswith("data:")]
    assert lignes, "flux vide"
    return [json.loads(ligne) for ligne in lignes]   # lève si une ligne est invalide


def _etapes(evts):
    return [e["etape"] for e in evts if "etape" in e]


def _texte(evts):
    return "".join((e.get("message") or {}).get("content") or "" for e in evts)


def _fins(evts):
    return [e for e in evts if e.get("done")]


def _variantes(chemin) -> list[str]:
    """Un chemin absolu tel qu'il pourrait apparaître dans le flux (brut ou
    échappé en JSON, les antislashs de Windows y étant doublés)."""
    brut = str(chemin)
    return [brut, json.dumps(brut)[1:-1]]


# ---------- Un tour d'outil, puis la réponse ----------
def test_lecture_d_un_document_puis_reponse_un_seul_done(env, monkeypatch):
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("lire_document", chemin="r0/convocation.txt"), fin()],
        [texte("Le CA a lieu "), fin("le 12 décembre.")],
    ]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))

    etapes = _etapes(evts)
    assert etapes[0] == {"id": 1, "outil": "lire_document", "etat": "en_cours",
                         "libelle": "Lecture de « convocation.txt »"}
    assert etapes[1]["id"] == 1 and etapes[1]["etat"] == "fini"
    assert etapes[1]["outil"] == "lire_document"
    assert etapes[1]["libelle"] == "Lecture de « convocation.txt »"
    assert etapes[1]["documents"] == [{"path": "r0/convocation.txt", "name": "convocation.txt"}]
    assert _texte(evts) == "Le CA a lieu le 12 décembre."
    # UN SEUL done, le dernier évènement du flux.
    assert len(_fins(evts)) == 1 and evts[-1]["done"] is True
    assert evts[-1]["done_reason"] == "stop"

    assert len(faux.shows) == 1 and faux.shows[0] == {"model": MODELE}
    assert len(faux.chats) == 2
    premier, second = faux.chats
    assert premier["tools"] == second["tools"]
    assert {o["function"]["name"] for o in premier["tools"]} == {
        "chercher_documents", "lire_document", "proposer_document_word"}
    assert outils.DIRECTIVE_OUTILS in premier["messages"][0]["content"]
    assistant, outil = second["messages"][-2:]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["function"]["name"] == "lire_document"
    assert outil["role"] == "tool" and outil["tool_name"] == "lire_document"
    assert CONVOCATION in outil["content"]


def test_recherche_par_mots_cles_en_chemins_virtuels(env, monkeypatch):
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("chercher_documents", requete="convocation conseil"), fin()],
        [fin("J'ai trouvé la convocation.")],
    ]))
    reponse = env["client"].post("/api/chat/stream", json=DEMANDE)
    evts = _evenements(reponse)
    finie = _etapes(evts)[1]
    assert finie["etat"] == "fini" and finie["resume"] == "1 document trouvé"
    assert finie["libelle"] == "Recherche dans les documents : « convocation conseil »"
    assert finie["documents"] == [{"path": "r0/convocation.txt", "name": "convocation.txt"}]
    resultat = faux.chats[1]["messages"][-1]["content"]
    assert "r0/convocation.txt" in resultat and "cantine" not in resultat
    for variante in _variantes(env["docs"]):
        assert variante not in reponse.text and variante not in resultat


@pytest.mark.parametrize("chemin", [
    "r0/../hors/hors.txt",          # sortie de la racine par « .. »
    "../hors/hors.txt",
    "__HORS__",                     # chemin absolu hors des dossiers de travail
    "__B__",                        # chemin absolu d'un document de l'organisation B
    "r1/secret_b.txt",              # « r1 » n'existe pas pour l'organisation A
])
def test_lecture_hors_perimetre_refusee(env, monkeypatch, chemin):
    chemin = (chemin.replace("__HORS__", str(env["hors"] / "hors.txt"))
              .replace("__B__", str(env["docs_b"] / "secret_b.txt")))
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("lire_document", chemin=chemin), fin()],
        [fin("Je ne peux pas lire ce document.")],
    ]))
    reponse = env["client"].post("/api/chat/stream", json=DEMANDE)
    evts = _evenements(reponse)
    finie = _etapes(evts)[1]
    assert finie["etat"] == "echec" and finie["documents"] == []
    resultat = faux.chats[1]["messages"][-1]["content"]
    for interdit in (SECRET_B, HORS_PERIMETRE):
        assert interdit not in reponse.text and interdit not in resultat
    # Aucun chemin absolu dans le flux, ni dans le résultat rendu au modèle.
    for variante in _variantes(env["tmp"]):
        assert variante not in reponse.text and variante not in resultat
    assert len(_fins(evts)) == 1


def test_proposition_de_document_sans_creation_de_fichier(env, monkeypatch):
    avant = sorted(p.relative_to(env["tmp"]) for p in env["tmp"].rglob("*")
                   if "profiles" not in p.parts)
    _brancher(monkeypatch, FauxOllama([
        [texte("Je prépare la convocation."),
         appel("proposer_document_word", type_document="convocation",
               titre="Convocation au CA", objet="Conseil d'administration",
               destinataire="Membres du CA", texte="Vous êtes convoqués le 12 décembre."),
         fin()],
        [fin("Je vous propose ce document : cliquez pour le créer.")],
    ]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    propositions = [e["proposition"] for e in evts if "proposition" in e]
    assert propositions == [{
        "type": "document_word", "type_document": "convocation",
        "titre": "Convocation au CA", "objet": "Conseil d'administration",
        "destinataire": "Membres du CA", "texte": "Vous êtes convoqués le 12 décembre.",
    }]
    # La proposition suit l'étape finie de son outil.
    rangs = [i for i, e in enumerate(evts) if "etape" in e or "proposition" in e]
    assert "proposition" in evts[rangs[-1]] and evts[rangs[-2]]["etape"]["etat"] == "fini"
    assert _texte(evts).startswith("Je prépare la convocation.")
    apres = sorted(p.relative_to(env["tmp"]) for p in env["tmp"].rglob("*")
                   if "profiles" not in p.parts)
    assert apres == avant                    # aucun fichier créé


def test_boucle_bornee_puis_tour_final_sans_outils(env, monkeypatch):
    """Un modèle qui réclame un outil à chaque tour ne boucle pas sans fin."""
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("chercher_documents", requete="budget"), fin()],
    ]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    assert len(faux.chats) == outils.MAX_TOURS_OUTILS + 1
    assert all("tools" in c for c in faux.chats[:-1])
    assert "tools" not in faux.chats[-1]
    etapes = _etapes(evts)
    assert [e["id"] for e in etapes if e["etat"] == "fini"] == list(
        range(1, outils.MAX_TOURS_OUTILS + 1))
    assert len(_fins(evts)) == 1 and evts[-1]["done"] is True


def test_plusieurs_appels_dans_un_tour_ids_incrementaux(env, monkeypatch):
    double = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "chercher_documents", "arguments": {"requete": "budget"}}},
        # Arguments en texte JSON : décodés avant l'exécution.
        {"function": {"name": "lire_document",
                      "arguments": json.dumps({"chemin": "r0/cantine.txt"})}},
    ]}, "done": False}
    faux = _brancher(monkeypatch, FauxOllama([[double, fin()], [fin("Voilà.")]]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    etapes = _etapes(evts)
    assert [(e["id"], e["etat"]) for e in etapes] == [
        (1, "en_cours"), (1, "fini"), (2, "en_cours"), (2, "fini")]
    outils_rendus = [m for m in faux.chats[1]["messages"] if m["role"] == "tool"]
    assert [m["tool_name"] for m in outils_rendus] == ["chercher_documents", "lire_document"]
    assert "Note interne sur la cantine." in outils_rendus[1]["content"]


def test_appels_d_un_tour_plafonnes(env, monkeypatch):
    """Un modèle qui émet des dizaines d'appels dans un même tour n'en fait
    exécuter que MAX_APPELS_PAR_TOUR (lectures en rafale qui figeaient la réponse
    et saturaient le contexte), et l'historique rendu au modèle est cohérent."""
    rafale = {"message": {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "chercher_documents", "arguments": {"requete": f"sujet {i}"}}}
        for i in range(30)]}, "done": False}
    faux = _brancher(monkeypatch, FauxOllama([[rafale, fin()], [fin("Voilà.")]]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    finies = [e for e in _etapes(evts) if e["etat"] != "en_cours"]
    assert len(finies) == outils.MAX_APPELS_PAR_TOUR
    second = faux.chats[1]["messages"]
    assert len([m for m in second if m["role"] == "tool"]) == outils.MAX_APPELS_PAR_TOUR
    assert len(second[-outils.MAX_APPELS_PAR_TOUR - 1]["tool_calls"]) == \
        outils.MAX_APPELS_PAR_TOUR
    assert _texte(evts).endswith("Voilà.")


# ---------- Désactivation : le chat d'avant, à l'identique ----------
LIGNES_AVANT = [json.dumps({"message": {"content": "Bon"}, "done": False}),
                json.dumps({"message": {"content": "jour"}, "done": True,
                            "done_reason": "stop"})]


@pytest.mark.parametrize("reglage, modele, capacites, show_attendu", [
    ({"outils_actifs": False}, MODELE, ("completion", "tools"), False),
    ({"compute_device": "cpu"}, MODELE, ("completion", "tools"), False),
    ({"compute_device": "leger"}, MODELE, ("completion", "tools"), False),
    ({}, MODELE, ("completion",), True),                  # modèle sans « tools »
    # Modèle non validé au banc, même s'il annonce « tools » (mistral-nemo).
    ({}, "mistral-nemo", ("completion", "tools"), False),
])
def test_sans_les_conditions_le_chat_est_celui_d_avant(env, monkeypatch, reglage, modele,
                                                       capacites, show_attendu):
    if reglage:
        assert env["client"].put("/api/settings", json=reglage).status_code == 200
    reponse_ollama = httpx.Response(200, text="\n".join(LIGNES_AVANT) + "\n")
    faux = _brancher(monkeypatch, FauxOllama([reponse_ollama], capacites=capacites))
    demande = {**DEMANDE, "model": modele}
    reponse = env["client"].post("/api/chat/stream", json=demande)
    # Flux relayé tel quel, ligne à ligne.
    assert reponse.text == "".join(f"data: {ligne}\n\n" for ligne in LIGNES_AVANT)
    assert len(faux.chats) == 1
    corps = faux.chats[0]
    assert "tools" not in corps
    assert outils.DIRECTIVE_OUTILS not in corps["messages"][0]["content"]
    assert corps["options"]["temperature"] == 0.7      # pas de plafond
    assert bool(faux.shows) is show_attendu


def test_capacites_en_cache_seulement_si_lisibles(env, monkeypatch):
    """Un échec de `/api/show` n'est pas retenu (modèle téléchargé entre-temps) ;
    une réponse lisible l'est (pas d'aller-retour à chaque message)."""
    faux = _brancher(monkeypatch, FauxOllama([[fin("Bonjour.")]], statut_show=500))
    for _ in range(2):
        env["client"].post("/api/chat/stream", json=DEMANDE)
    assert len(faux.shows) == 2
    assert all("tools" not in c for c in faux.chats)
    faux.statut_show = 200
    for _ in range(2):
        env["client"].post("/api/chat/stream", json=DEMANDE)
    assert len(faux.shows) == 3
    assert all("tools" in c for c in faux.chats[2:])


@pytest.mark.parametrize("demandee, envoyee", [(None, 0.3), (0.1, 0.1), (1.5, 0.3)])
def test_temperature_plafonnee_en_mode_outils(env, monkeypatch, demandee, envoyee):
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("chercher_documents", requete="budget"), fin()], [fin("Voilà.")]]))
    demande = {**DEMANDE, "temperature": demandee} if demandee is not None else DEMANDE
    env["client"].post("/api/chat/stream", json=demande)
    assert [c["options"]["temperature"] for c in faux.chats] == [envoyee, envoyee]
    # Le reste des options est inchangé.
    assert faux.chats[0]["options"]["num_ctx"] == settings.NUM_CTX["gpu"]


def test_toutes_les_lignes_sont_du_json_valide(env, monkeypatch):
    """Une ligne d'Ollama incomplète n'est jamais relayée, et les guillemets
    d'un texte ne cassent pas le JSON."""
    _brancher(monkeypatch, FauxOllama([
        ['{"message": {"content": "incompl', appel("lire_document", chemin='r0/"x".txt'),
         fin()],
        [texte('Le « CA » dit "oui".'), fin()],
    ]))
    reponse = env["client"].post("/api/chat/stream", json=DEMANDE)
    lignes = [ligne for ligne in reponse.text.split("\n\n") if ligne]
    assert all(ligne.startswith("data: ") for ligne in lignes)
    evts = [json.loads(ligne[6:]) for ligne in lignes]
    assert _texte(evts) == 'Le « CA » dit "oui".'
    assert _etapes(evts)[1]["etat"] == "echec"


# ---------- Erreurs ----------
@pytest.mark.parametrize("panne, attendu", [
    (httpx.Response(500, text='panne "interne"'),
     "Le moteur d'IA a refusé la demande (erreur 500)"),
    (httpx.ConnectError("All connection attempts failed"), main.MESSAGE_OLLAMA_INJOIGNABLE),
    (httpx.ReadError("connexion perdue"), "La connexion au moteur d'IA a été interrompue"),
])
def test_erreur_au_deuxieme_tour_message_lisible_puis_plus_rien(
        env, monkeypatch, panne, attendu):
    _brancher(monkeypatch, FauxOllama([
        [appel("lire_document", chemin="r0/convocation.txt"), fin()], panne]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    assert [e["etape"]["etat"] for e in evts[:-1]] == ["en_cours", "fini"]
    assert evts[-1]["error"].startswith(attendu)
    assert not _fins(evts)


def test_erreur_d_ollama_dans_le_flux(env, monkeypatch):
    _brancher(monkeypatch, FauxOllama([[texte("Début"), {"error": "plus de mémoire"}]]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    assert evts[-1] == {"error": "plus de mémoire"}
    assert not _fins(evts)


# ---------- Mails et agenda : seulement s'ils sont configurés ----------
def _noms_outils(corps):
    return {o["function"]["name"] for o in corps["tools"]}


def test_mails_et_agenda_absents_sans_configuration(env, monkeypatch):
    # Boîte activée mais sans mot de passe : pas encore configurée.
    env["client"].put("/api/settings", json={"connectors": {
        "imap": {"enabled": True, "host": "imap.exemple.fr", "user": "marie"},
        "calendar_ics": {"enabled": False, "path": "agenda.ics"}}})
    faux = _brancher(monkeypatch, FauxOllama([[fin("Bonjour.")]]))
    env["client"].post("/api/chat/stream", json=DEMANDE)
    noms = _noms_outils(faux.chats[0])
    assert "lister_mails_non_lus" not in noms and "consulter_agenda" not in noms


def test_mails_et_agenda_offerts_et_lus_quand_configures(env, monkeypatch):
    ics = env["tmp"] / "agenda.ics"
    ics.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
    env["client"].put("/api/settings", json={"connectors": {
        "imap": {"enabled": True, "host": "imap.exemple.fr", "user": "marie",
                 "password": "MDP-IMAP"},
        "calendar_ics": {"enabled": True, "path": str(ics)}}})
    lus = []

    def faux_inbox(hote, compte, secret, dossier, limit=10):
        lus.append((hote, compte, secret, dossier, limit))
        return [{"id": "1", "from": "parent@exemple.fr", "subject": "Absence",
                 "date": "lun.", "snippet": "Mon fils sera absent."}]
    monkeypatch.setattr(main, "read_inbox", faux_inbox)
    monkeypatch.setattr(main, "calendar_list_events", lambda chemin, limit=10: [
        {"name": "Conseil de classe", "begin": "2026-12-12", "end": "", "location": ""}])
    faux = _brancher(monkeypatch, FauxOllama([
        [appel("lister_mails_non_lus", nombre=3), appel("consulter_agenda"), fin()],
        [fin("Un mail et un rendez-vous.")],
    ]))
    evts = _evenements(env["client"].post("/api/chat/stream", json=DEMANDE))
    assert {"lister_mails_non_lus", "consulter_agenda"} <= _noms_outils(faux.chats[0])
    assert lus == [("imap.exemple.fr", "marie", "MDP-IMAP", "INBOX", 3)]
    resumes = [e["resume"] for e in _etapes(evts) if e["etat"] == "fini"]
    assert resumes == ["1 mail non lu", "1 événement à venir"]
    rendus = [m["content"] for m in faux.chats[1]["messages"] if m["role"] == "tool"]
    assert "Mon fils sera absent." in rendus[0] and "Conseil de classe" in rendus[1]
    assert "MDP-IMAP" not in json.dumps(evts, ensure_ascii=False)


def test_agenda_dans_un_dossier_reserve_non_offert(env, monkeypatch):
    reserve = profiles.PROFILES_DIR / "agenda.ics"
    reserve.parent.mkdir(parents=True, exist_ok=True)
    reserve.write_text("BEGIN:VCALENDAR\nEND:VCALENDAR\n", encoding="utf-8")
    zones.dossiers_reserves.cache_clear()
    env["client"].put("/api/settings", json={"connectors": {
        "calendar_ics": {"enabled": True, "path": str(reserve)}}})
    faux = _brancher(monkeypatch, FauxOllama([[fin("Bonjour.")]]))
    env["client"].post("/api/chat/stream", json=DEMANDE)
    assert "consulter_agenda" not in _noms_outils(faux.chats[0])
