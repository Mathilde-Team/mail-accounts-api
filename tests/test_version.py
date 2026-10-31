# SPDX-License-Identifier: GPL-3.0-or-later
"""La version n'est déclarée qu'une fois (SOCLE.md §1) : pyproject.toml est
la source de vérité ; la version exposée par l'application doit coïncider."""

import tomllib
from pathlib import Path

import api


def test_version_fastapi_egal_pyproject():
    racine = Path(__file__).resolve().parent.parent
    pyproject = tomllib.loads((racine / "pyproject.toml").read_text())
    # La version exposée par l'application doit coïncider avec pyproject.toml.
    assert api.VERSION == pyproject["project"]["version"]
