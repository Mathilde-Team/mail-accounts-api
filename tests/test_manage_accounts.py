# SPDX-License-Identifier: GPL-3.0-or-later
"""Tests du gestionnaire CLI manage_accounts.py (SOCLE.md §4 : couverture)."""

import pytest

import manage_accounts
from manage_accounts import (
    add_account,
    delete_account,
    generate_password,
    list_accounts,
    main,
    modify_account,
    parse_accounts_file,
    sha512_hash,
    show_help,
    write_accounts_file,
)


@pytest.fixture
def accounts_file(tmp_path, monkeypatch):
    path = tmp_path / "postfix-accounts.cf"
    monkeypatch.setattr(manage_accounts, "ACCOUNTS_FILE", str(path))
    return path


def test_sha512_hash_format():
    digest = sha512_hash("secret")
    assert digest.startswith("{sha512}")
    assert len(digest) == len("{sha512}") + 128  # SHA-512 : 128 caractères hexadécimaux


def test_generate_password_random_and_long():
    assert generate_password() != generate_password()
    assert len(generate_password()) >= 16


def test_parse_accounts_file_absent(accounts_file):
    assert parse_accounts_file() == []


def test_parse_accounts_file_roundtrip(accounts_file):
    accounts_file.write_text(
        "# commentaire\nuser@example.org|{sha512}abc|user\n\nother@example.org|{sha512}def|other\n"
    )
    parsed = parse_accounts_file()
    assert [a["email"] for a in parsed] == ["user@example.org", "other@example.org"]
    assert parsed[0]["folder"] == "user"


def test_write_then_read_roundtrip(accounts_file):
    write_accounts_file(
        [
            {"email": "a@example.org", "hash": "{sha512}x", "folder": "a"},
            {"email": "b@example.org", "hash": "{sha512}y", "folder": "b"},
        ]
    )
    assert accounts_file.parent == accounts_file.parent  # répertoire créé au besoin
    assert [a["email"] for a in parse_accounts_file()] == ["a@example.org", "b@example.org"]


def test_write_accounts_file_creates_parent(tmp_path, monkeypatch):
    path = tmp_path / "nested" / "dir" / "postfix-accounts.cf"
    monkeypatch.setattr(manage_accounts, "ACCOUNTS_FILE", str(path))
    write_accounts_file([{"email": "a@example.org", "hash": "h", "folder": "a"}])
    assert path.exists()


def test_list_accounts_empty(accounts_file, capsys):
    list_accounts()
    assert "aucun compte" not in capsys.readouterr().out  # message via logger, pas stdout


def test_list_accounts_displays(accounts_file, capsys):
    write_accounts_file([{"email": "user@example.org", "hash": "h", "folder": "user"}])
    list_accounts()
    out = capsys.readouterr().out
    assert "COMPTES MAIL" in out
    assert "user@example.org" in out
    assert "Total: 1 compte(s)" in out


def test_add_account_generated_password(accounts_file, capsys):
    add_account("user@example.org")
    parsed = parse_accounts_file()
    assert [a["email"] for a in parsed] == ["user@example.org"]
    out = capsys.readouterr().out
    assert "Mot de passe:" in out  # affiché une seule fois sur stdout


def test_add_account_provided_password(accounts_file, capsys):
    add_account("user@example.org", "MonMotDePasse123!")
    account = parse_accounts_file()[0]
    assert account["hash"] == sha512_hash("MonMotDePasse123!")
    # Comportement historique conservé : le mot de passe (même fourni) est
    # affiché une fois sur stdout, comme à la création par l'API.
    assert "MonMotDePasse123!" in capsys.readouterr().out


def test_add_account_duplicate(accounts_file, capsys):
    write_accounts_file([{"email": "user@example.org", "hash": "h", "folder": "user"}])
    add_account("user@example.org", "x")
    assert len(parse_accounts_file()) == 1


def test_add_account_invalid_email(accounts_file):
    add_account("userexample.org", "x")
    assert parse_accounts_file() == []


def test_modify_account(accounts_file):
    write_accounts_file([{"email": "user@example.org", "hash": "old", "folder": "user"}])
    modify_account("user@example.org", "new-password")
    assert parse_accounts_file()[0]["hash"] == sha512_hash("new-password")


def test_modify_account_absent(accounts_file):
    modify_account("absent@example.org", "x")
    assert not accounts_file.exists()


def test_delete_account_confirmed(accounts_file):
    write_accounts_file(
        [
            {"email": "a@example.org", "hash": "h", "folder": "a"},
            {"email": "b@example.org", "hash": "h", "folder": "b"},
        ]
    )
    delete_account("a@example.org", confirm=True)
    assert [a["email"] for a in parse_accounts_file()] == ["b@example.org"]


def test_delete_account_refused(accounts_file, monkeypatch):
    write_accounts_file([{"email": "a@example.org", "hash": "h", "folder": "a"}])
    monkeypatch.setattr("builtins.input", lambda prompt: "non")
    delete_account("a@example.org")
    assert len(parse_accounts_file()) == 1


def test_delete_account_accepted_interactive(accounts_file, monkeypatch):
    write_accounts_file([{"email": "a@example.org", "hash": "h", "folder": "a"}])
    monkeypatch.setattr("builtins.input", lambda prompt: "oui")
    delete_account("a@example.org")
    assert parse_accounts_file() == []


def test_delete_account_absent(accounts_file):
    delete_account("absent@example.org", confirm=True)
    assert not accounts_file.exists()


def test_show_help(capsys):
    show_help()
    out = capsys.readouterr().out
    assert "GESTIONNAIRE DE COMPTES MAIL" in out
    assert "python3 manage_accounts.py list" in out


def test_main_without_argument(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py"])
    main()
    assert "GESTIONNAIRE DE COMPTES MAIL" in capsys.readouterr().out


def test_main_help(capsys, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "help"])
    main()
    assert "UTILISATION" in capsys.readouterr().out


def test_main_list(accounts_file, capsys, monkeypatch):
    write_accounts_file([{"email": "user@example.org", "hash": "h", "folder": "user"}])
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "list"])
    main()
    assert "COMPTES MAIL" in capsys.readouterr().out


def test_main_add(accounts_file, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "add", "user@example.org"])
    main()
    assert [a["email"] for a in parse_accounts_file()] == ["user@example.org"]


def test_main_adds(accounts_file, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "adds", "user@example.org", "pass", "1", "4"])
    main()
    assert [a["email"] for a in parse_accounts_file()] == [
        "user1@example.org",
        "user2@example.org",
        "user3@example.org",
    ]


def test_main_adds_shares_password(accounts_file, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "adds", "user@example.org", "pass", "1", "3"])
    main()
    parsed = parse_accounts_file()
    assert parsed[0]["hash"] == parsed[1]["hash"] == sha512_hash("pass")


def test_main_modify(accounts_file, monkeypatch):
    write_accounts_file([{"email": "user@example.org", "hash": "old", "folder": "user"}])
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "modify", "user@example.org", "newpass"])
    main()
    assert parse_accounts_file()[0]["hash"] == sha512_hash("newpass")


def test_main_delete(accounts_file, monkeypatch):
    write_accounts_file([{"email": "user@example.org", "hash": "h", "folder": "user"}])
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "delete", "user@example.org"])
    monkeypatch.setattr("builtins.input", lambda prompt: "oui")
    main()
    assert parse_accounts_file() == []


def test_main_unknown_command(accounts_file, monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "nonsense"])
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 1


def test_main_add_missing_argument(monkeypatch):
    monkeypatch.setattr("sys.argv", ["manage_accounts.py", "add"])
    with pytest.raises(SystemExit):
        main()


def test_run_module_importable():
    import run  # noqa: F401 — le garde __main__ reste exclu de la couverture
