"""
Connecteur IMAP (audit, points 3, 4 et 11) : certificat vérifié, délai
d'expiration, lecture seule, nombre de messages borné, routes non bloquantes.

Aucune connexion réseau : l'ouverture (`_ouvrir`) ou `imaplib.IMAP4_SSL` est
remplacée par un faux serveur.
"""
import inspect
import ssl

import pytest

from backend import main
from backend.connectors import imap_client

MESSAGE = (b"From: =?utf-8?q?Andr=C3=A9?= <a@b.fr>\r\n"
           b"Subject: =?x-inconnu-9?q?Bonjour?=\r\n"
           b"Date: Mon, 1 Jan 2026 10:00:00 +0000\r\n\r\nCorps du message\r\n")


class FauxImap:
    def __init__(self, nb_messages=3):
        self.ids = [str(i + 1).encode() for i in range(nb_messages)]
        self.select_appels = []
        self.fetch_appels = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def login(self, *_):
        pass

    def select(self, dossier, readonly=False):
        self.select_appels.append((dossier, readonly))
        return "OK", [b"1"]

    def search(self, *_):
        return "OK", [b" ".join(self.ids)]

    def fetch(self, mid, partie):
        self.fetch_appels.append((mid, partie))
        return "OK", [(b"1 (BODY[] {10}", MESSAGE), b")"]

    def close(self):
        pass


@pytest.fixture
def faux(monkeypatch):
    objet = FauxImap(nb_messages=80)
    monkeypatch.setattr(imap_client, "_ouvrir", lambda host: objet)
    return objet


def test_connexion_verifie_le_certificat_et_a_un_delai(monkeypatch):
    recu = {}

    def faux_ssl(host, **kw):
        recu["host"] = host
        recu.update(kw)
        return FauxImap()
    monkeypatch.setattr(imap_client.imaplib, "IMAP4_SSL", faux_ssl)
    imap_client.unread_count("imap.exemple.fr", "u", "p")
    contexte = recu["ssl_context"]
    assert contexte.verify_mode == ssl.CERT_REQUIRED
    assert contexte.check_hostname is True
    assert recu["timeout"] == imap_client.DELAI_IMAP == 15


def test_lecture_seule_et_peek(faux):
    imap_client.read_inbox("h", "u", "p", limit=2)
    assert faux.select_appels == [("INBOX", True)]
    assert faux.fetch_appels and all(p == "(BODY.PEEK[])" for _, p in faux.fetch_appels)
    imap_client.unread_count("h", "u", "p")
    assert faux.select_appels[-1] == ("INBOX", True)


@pytest.mark.parametrize("limit, attendu", [(0, 1), (-5, 1), (10_000, 50), (7, 7)])
def test_limit_borne(faux, limit, attendu):
    assert len(imap_client.read_inbox("h", "u", "p", limit=limit)) == attendu


def test_jeu_de_caracteres_inconnu_ne_fait_pas_echouer_la_lecture(faux):
    messages = imap_client.read_inbox("h", "u", "p", limit=1)
    assert messages[0]["from"].startswith("André")
    assert "Bonjour" in messages[0]["subject"]
    assert messages[0]["snippet"].startswith("Corps")


def test_decode_octets_invalides():
    assert imap_client._decode("=?utf-8?q?=FF=FE?=") != ""


def test_les_routes_imap_ne_bloquent_pas_le_serveur():
    assert not inspect.iscoroutinefunction(main.connectors_mail_unread)
    assert not inspect.iscoroutinefunction(main.connectors_imap)
