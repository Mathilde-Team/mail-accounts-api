# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface web (issue #9) : desserte de la page et des ressources statiques.

L'interface ne porte aucun secret ni donnée de compte : ces tests
vérifient la desserte (page, ressources, refus des chemins inconnus,
en-têtes de sécurité) et l'absence d'authentification exigée pour la page.
"""

from pathlib import Path

from fastapi.testclient import TestClient

from api import create_app

KEY = "test-only-" + "x" * 40
RACINE = Path(__file__).resolve().parent.parent


def client(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as test_client:
        yield test_client


def test_page_sans_authentification(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        reponse = http.get("/ui")
    assert reponse.status_code == 200
    assert reponse.headers["content-type"].startswith("text/html")
    # La page est le point d'entrée : elle référence les ressources servies.
    assert "/ui/app.js" in reponse.text
    assert "/ui/style.css" in reponse.text


def test_page_barre_oblique_finale(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        assert http.get("/ui/").status_code == 200


def test_ressources_statiques(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        for fichier, type_mime in (
            ("app.js", "text/javascript"),
            ("style.css", "text/css"),
        ):
            reponse = http.get(f"/ui/{fichier}")
            assert reponse.status_code == 200
            assert reponse.headers["content-type"].startswith(type_mime)
            assert len(reponse.content) > 0


def test_page_et_ressources_sans_cle(accounts_file):
    # Pas d'en-tête Authorization : la page reste serviable, seules les
    # données /accounts exigent la clé.
    with TestClient(create_app(accounts_file, KEY)) as http:
        assert http.get("/ui").status_code == 200
        assert http.get("/ui/app.js").status_code == 200


def test_ressource_inconnue_refusee(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        for chemin in ("/ui/inexistant.js", "/ui/secret.txt", "/ui/INDEX.HTML"):
            reponse = http.get(chemin)
            # Nom inconnu : 404 ; casse non prévue par le motif : 422.
            assert reponse.status_code in (404, 422), chemin


def test_traversee_refusee(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        # Le motif du paramètre rejette tout ce qui n'est pas un nom simple.
        assert http.get("/ui/..%2Fapi.py").status_code in (404, 422)
        assert http.get("/ui/../pyproject.toml").status_code in (404, 422)


def test_en_tetes_securite(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as http:
        for chemin in ("/ui", "/ui/app.js", "/ui/style.css"):
            reponse = http.get(chemin)
            # Le middleware du socle interdit la mise en cache.
            assert reponse.headers["cache-control"] == "no-store"
            # La page ne charge rien d'externe : CSP restrictive.
            assert reponse.headers["content-security-policy"] == "default-src 'self'"


def test_fichiers_ui_references_existent():
    # La page ne référence que des fichiers réellement présents dans ui/.
    for fichier in ("index.html", "app.js", "style.css"):
        assert (RACINE / "ui" / fichier).is_file(), fichier
