# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixtures partagées entre les fichiers de tests."""

import pytest


@pytest.fixture
def accounts_file(tmp_path):
    path = tmp_path / "postfix-accounts.cf"
    path.write_text("# existing comment\nold@example.org|{sha512}old|old|extra\n\n")
    path.chmod(0o640)
    return path
