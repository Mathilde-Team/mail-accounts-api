# SPDX-License-Identifier: GPL-3.0-or-later
"""Contrats des déploiements Compose standard et Swarm (issue #10)."""

from pathlib import Path

import pytest
import yaml

RACINE = Path(__file__).resolve().parent.parent


@pytest.fixture(params=["docker-compose.yml", "deploy/docker-compose.swarm.yml"])
def service(request):
    """Charge les deux variantes sans exécuter Docker ni substituer de secret."""
    contenu = yaml.safe_load((RACINE / request.param).read_text(encoding="utf-8"))
    assert set(contenu["services"]) == {"mail-accounts-api"}
    return request.param, contenu["services"]["mail-accounts-api"]


def test_configuration_et_stockage_obligatoires(service):
    """La clé et le répertoire existant ne sont jamais inventés au démarrage."""
    _, definition = service
    assert definition["environment"] == {
        "MAIL_API_KEY": "${MAIL_API_KEY:?MAIL_API_KEY requis}",
        "MAIL_API_PORT": "9942",
    }
    montage = definition["volumes"][0]
    assert montage["type"] == "bind"
    assert montage["source"] == "${MAIL_CONFIG_DIR:?MAIL_CONFIG_DIR requis}"
    assert montage["target"] == "/app/12-mail/config"
    assert not montage.get("read_only", False)
    assert definition["read_only"] is True
    assert definition["cap_drop"] == ["ALL"]


def test_standard_construction_locale_et_port_prive():
    """Compose construit depuis la racine, sans publier l'API sur tout le réseau."""
    definition = yaml.safe_load((RACINE / "docker-compose.yml").read_text())["services"]["mail-accounts-api"]
    assert definition["build"] == "."
    assert definition["image"] == "${MAIL_API_IMAGE:-mail-accounts-api:local}"
    assert definition["ports"] == ["127.0.0.1:9942:9942"]
    assert definition["volumes"][0]["bind"]["create_host_path"] is False
    assert definition["tmpfs"] == ["/tmp"]  # noqa: S108 (cible tmpfs, aucune écriture de fichier)
    assert definition["security_opt"] == ["no-new-privileges:true"]
    assert definition["restart"] == "unless-stopped"


def test_swarm_image_publiee_et_noeud_unique():
    """Une seule instance reste sur le nœud des données, même lors des mises à jour."""
    definition = yaml.safe_load((RACINE / "deploy/docker-compose.swarm.yml").read_text())["services"][
        "mail-accounts-api"
    ]
    assert definition["image"] == "${MAIL_API_IMAGE:?MAIL_API_IMAGE requis}"
    assert "build" not in definition
    assert "restart" not in definition
    assert "security_opt" not in definition  # Ignoré par docker stack, ne pas promettre cette protection.
    assert definition["volumes"][1] == {"type": "tmpfs", "target": "/tmp"}  # noqa: S108 (cible tmpfs)
    assert definition["ports"] == [{"target": 9942, "published": 9942, "protocol": "tcp", "mode": "host"}]
    deploiement = definition["deploy"]
    assert deploiement["replicas"] == 1
    assert deploiement["placement"]["constraints"] == ["node.labels.mail-accounts-data == true"]
    assert deploiement["restart_policy"] == {"condition": "any", "delay": "5s"}
    assert deploiement["update_config"] == {"parallelism": 1, "order": "stop-first", "failure_action": "rollback"}
    assert deploiement["rollback_config"] == {"parallelism": 1, "order": "stop-first"}


def test_documentation_deux_modes_et_limites():
    """L'opérateur dispose des commandes et avertissements propres à chaque moteur."""
    contenu = (RACINE / "README.md").read_text(encoding="utf-8")
    for attendu in (
        "docker compose up -d --build",
        "docker stack deploy",
        "docker service rollback",
        "mail-accounts-data=true",
        "MAIL_CONFIG_DIR",
        "stop-first",
        "aucun déploiement réel",
    ):
        assert attendu in contenu
