# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface web servie par l'API elle-même (issue #9).

La page est publique (aucun secret dedans), servie same-origin : toutes
les données restent derrière les routes /accounts et leur clé Bearer.
"""

from fastapi.testclient import TestClient

from api import create_app

KEY = "test-only-" + "x" * 40


def _client(tmp_path, monkeypatch):
    monkeypatch.setenv("MAIL_ACCOUNTS_FILE", str(tmp_path / "postfix-accounts.cf"))
    (tmp_path / "postfix-accounts.cf").write_text("# commentaire\n")
    return TestClient(create_app(tmp_path / "postfix-accounts.cf", KEY))


def test_page_servie_sans_authentification(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # La page ne doit jamais être mise en cache (middleware no_cache).
    assert response.headers["cache-control"] == "no-store"


def test_page_dynamique_construite_sur_l_api(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    page = client.get("/").text
    assert "Mail Accounts — interface" in page
    # Entièrement dynamique : les données viennent des routes JSON de l'API,
    # en URLs relatives (same-origin), avec la clé Bearer saisie.
    assert 'api("/accounts' in page
    assert "Authorization" in page
    assert "sessionStorage" in page
    assert "localStorage" not in page
    # Les quatre familles de routes de l'API sont câblées dans la page.
    assert "/accounts/batch" in page
    assert "/accounts/numbered" in page
    assert "PATCH" in page
    assert "DELETE" in page
    # Aucune ressource externe : la page fonctionne sans accès Internet.
    assert "http://" not in page.replace("http://www.w3.org/1999/xhtml", "")
    assert "https://" not in page
    assert "src=" not in page


def test_page_ne_revele_rien(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    page = client.get("/").text
    assert KEY not in page
