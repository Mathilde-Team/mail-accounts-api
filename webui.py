# SPDX-License-Identifier: GPL-3.0-or-later
"""Interface web de l'API (issue #9).

Page unique servie par l'application elle-même : aucun outil de build, aucun
fichier externe. L'interface ne contient ni secret ni donnée de compte : la
clé Bearer est saisie par l'opérateur et gardée en ``sessionStorage`` (jamais
dans un cookie ni dans l'URL) ; toutes les données viennent des routes
``/accounts`` existantes.
"""

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from loguru import logger
from pydantic import Field

REPERTOIRE_UI = Path(__file__).with_name("ui")

# Seuls ces fichiers sont servables : tout le reste est un 404, sans jamais
# lire un chemin arbitraire du disque (pas de traversée possible).
FICHIERS_SERVABLES = {"index.html": "text/html", "app.js": "text/javascript", "style.css": "text/css"}


def creer_routeur_ui() -> APIRouter:
    """Routes de l'interface : page et ressources statiques, sans authentification."""
    logger.debug("creer_routeur_ui : entrée")
    router = APIRouter(prefix="/ui", tags=["Interface"], include_in_schema=False)

    @router.get("", summary="Page de l'interface web")
    @router.get("/", summary="Page de l'interface web")
    def page() -> FileResponse:
        logger.debug("ui.page : entrée")
        logger.debug("ui.page : sortie (index.html)")
        return FileResponse(
            REPERTOIRE_UI / "index.html",
            media_type="text/html",
            headers={"Content-Security-Policy": "default-src 'self'"},
        )

    @router.get("/{fichier}", summary="Ressource statique de l'interface")
    def ressource(
        fichier: Annotated[str, Field(pattern=r"^[a-z0-9.-]+$")],
    ) -> FileResponse:
        logger.debug("ui.ressource : entrée (fichier={})", fichier)
        if fichier not in FICHIERS_SERVABLES:
            logger.debug("ui.ressource : sortie (refusé)")
            raise HTTPException(status_code=404, detail="Ressource inconnue")
        logger.debug("ui.ressource : sortie (servi)")
        return FileResponse(
            REPERTOIRE_UI / fichier,
            media_type=FICHIERS_SERVABLES[fichier],
            headers={"Content-Security-Policy": "default-src 'self'"},
        )

    logger.debug("creer_routeur_ui : sortie (routeur prêt)")
    return router
