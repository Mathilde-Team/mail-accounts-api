# SPDX-License-Identifier: GPL-3.0-or-later
"""Containerisation Docker (issue #10) : l'image est validée statiquement.

Le runner de CI ne construit pas d'image (SOCLE.md « Environnement », espace
disque des runners maison) : ces tests verrouillent les invariants de
sécurité du Dockerfile — base figée, utilisateur non privilégié, aucun
secret embarqué, port et santé explicites.
"""

from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent


def dockerfile() -> str:
    return (RACINE / "Dockerfile").read_text(encoding="utf-8")


def test_base_figee_sans_latest():
    lignes = dockerfile().splitlines()
    froms = [ligne for ligne in lignes if ligne.startswith("FROM ")]
    assert len(froms) == 1
    # Version figée : tag précis python:<version>-slim-bookworm, jamais latest.
    assert froms[0] == "FROM python:3.12.8-slim-bookworm"


def test_utilisateur_non_privilegie():
    contenu = dockerfile()
    assert "USER mailapi" in contenu
    # L'installation des dépendances se fait avant le passage en utilisateur
    # non privilégié : pip ne doit jamais tourner en root.
    assert contenu.index("RUN pip install") < contenu.index("USER mailapi")


def test_aucun_secret_embarque():
    contenu = dockerfile()
    # La clé est fournie à l'exécution, jamais dans l'image
    # (ENV/ARG du Dockerfile, ni .env copié).
    assert "ENV MAIL_API_KEY" not in contenu
    assert "ARG MAIL_API_KEY" not in contenu
    assert "COPY .env" not in contenu


def test_port_et_sante_explicites():
    contenu = dockerfile()
    assert "EXPOSE 9941" in contenu
    assert "HEALTHCHECK" in contenu
    assert "/health" in contenu


def test_ecoute_reseau_et_fichier_comptes_par_defaut():
    contenu = dockerfile()
    # Dans un conteneur, écouter sur 127.0.0.1 rendrait le port injoignable.
    assert "MAIL_API_HOST=0.0.0.0" in contenu
    # Le chemin par défaut du fichier des comptes reste celui du dépôt.
    assert "MAIL_ACCOUNTS_FILE=/app/12-mail/config/postfix-accounts.cf" in contenu


def test_dockerignore_exclut_env_et_git():
    ignore = (RACINE / ".dockerignore").read_text(encoding="utf-8")
    for attendu in (".env", ".git", "tests", ".venv"):
        assert attendu in ignore.splitlines()


def test_compose_example_sans_secret_et_montage_repertoire():
    # Pas de dépendance YAML dans le dépôt : le fichier d'exemple est
    # validé par analyse textuelle (structure figée, jamais parsée au
    # démarrage de l'application).
    compose = (RACINE / "deploy" / "docker-compose.example.yml").read_text(encoding="utf-8")
    # La clé vient de l'environnement de l'opérateur, jamais du fichier.
    assert "MAIL_API_KEY: ${MAIL_API_KEY:?MAIL_API_KEY requis}" in compose
    assert "mail-accounts-api:" in compose
    # Le répertoire entier est monté : écriture atomique + verrou à côté
    # du fichier des comptes ; système de fichiers en lecture seule.
    assert ":/app/12-mail/config" in compose
    assert "read_only: true" in compose


def test_readme_documente_docker():
    readme = (RACINE / "README.md").read_text(encoding="utf-8")
    assert "docker run" in readme or "docker compose" in readme
    assert "MAIL_API_KEY" in readme
