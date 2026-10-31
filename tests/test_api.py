# SPDX-License-Identifier: GPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api import create_app
from manage_accounts import sha512_hash
from storage import AccountStore

KEY = "test-only-" + "x" * 40
HEADERS = {"Authorization": f"Bearer {KEY}"}


@pytest.fixture
def accounts_file(tmp_path):
    path = tmp_path / "postfix-accounts.cf"
    path.write_text("# existing comment\nold@example.org|{sha512}old|old|extra\n\n")
    path.chmod(0o640)
    return path


@pytest.fixture
def client(accounts_file):
    with TestClient(create_app(accounts_file, KEY)) as test_client:
        yield test_client


def test_key_required(accounts_file):
    for key in ("", "short", " " * 40, "a" * 32 + "\n", "é" * 40):
        with pytest.raises(RuntimeError, match="MAIL_API_KEY"):
            create_app(accounts_file, key)


@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/accounts"),
        ("get", "/accounts/old@example.org"),
        ("post", "/accounts"),
        ("post", "/accounts/batch"),
        ("post", "/accounts/numbered"),
        ("patch", "/accounts/old@example.org"),
        ("delete", "/accounts/old@example.org"),
    ],
)
def test_authentication_required(client, method, path):
    for headers in ({}, {"Authorization": "Bearer incorrect"}, {"Authorization": "Basic abc"}):
        response = client.request(method, path, headers=headers)
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == "Bearer"


def test_health_and_docs(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    schema = client.get("/openapi.json").json()
    assert "HTTPBearer" in schema["components"]["securitySchemes"]
    for path in ("/accounts", "/accounts/batch", "/accounts/numbered", "/accounts/{email}"):
        assert path in schema["paths"]
        for operation in schema["paths"][path].values():
            assert operation["security"] == [{"HTTPBearer": []}]
            assert "401" in operation["responses"]
            assert "503" in operation["responses"]


def test_list_hides_hashes(client):
    response = client.get("/accounts", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"accounts": [{"email": "old@example.org", "folder": "old"}], "total": 1}
    assert response.headers["cache-control"] == "no-store"
    assert "sha512" not in response.text


def test_create_modify_delete(client, accounts_file):
    response = client.post("/accounts", headers=HEADERS, json={"email": "new@example.org"})
    assert response.status_code == 201
    password = response.json()["password"]
    assert len(password) >= 16
    assert f"new@example.org|{sha512_hash(password)}|new" in accounts_file.read_text()
    assert client.get("/accounts/new@example.org", headers=HEADERS).json() == {
        "email": "new@example.org",
        "folder": "new",
    }
    response = client.patch(
        "/accounts/new@example.org",
        headers=HEADERS,
        json={"password": "replacement"},
    )
    assert response.status_code == 200
    assert "replacement" not in response.text
    assert sha512_hash("replacement") in accounts_file.read_text()
    response = client.delete("/accounts/new@example.org", headers=HEADERS)
    assert response.status_code == 204
    assert response.content == b""
    assert "new@example.org" not in accounts_file.read_text()
    assert "# existing comment" in accounts_file.read_text()
    assert "old@example.org|{sha512}old|old|extra" in accounts_file.read_text()
    assert accounts_file.stat().st_mode & 0o777 == 0o640


def test_supplied_password_never_echoed(client):
    response = client.post(
        "/accounts",
        headers=HEADERS,
        json={"email": "new@example.org", "password": "private-value"},
    )
    assert response.status_code == 201
    assert response.json() == {"email": "new@example.org", "folder": "new"}


def test_conflict_and_missing(client, accounts_file):
    before = accounts_file.read_bytes()
    assert client.post("/accounts", headers=HEADERS, json={"email": "old@example.org"}).status_code == 409
    for method in ("get", "patch", "delete"):
        kwargs = {"json": {"password": "test"}} if method == "patch" else {}
        assert client.request(method, "/accounts/missing@example.org", headers=HEADERS, **kwargs).status_code == 404
    assert accounts_file.read_bytes() == before


@pytest.mark.parametrize(
    "body",
    [
        {"email": "bad\n@example.org"},
        {"email": "../../user@example.org"},
        {"email": "user|injected@example.org"},
        {"email": "user@example.org", "password": ""},
        {"email": "user@example.org", "password": 123},
        {"email": "user@example.org", "unexpected": "secret-sentinel"},
        {"email": "user@example.org", "password": "secret-sentinel" * 100},
    ],
)
def test_invalid_input_no_secret_echo(client, accounts_file, body):
    before = accounts_file.read_bytes()
    response = client.post("/accounts", headers=HEADERS, json=body)
    assert response.status_code == 422
    assert "secret-sentinel" not in response.text
    assert accounts_file.read_bytes() == before


def test_batch_atomic_and_bounded(client, accounts_file):
    before = accounts_file.read_bytes()
    for names in (["new@example.org", "old@example.org"], ["new@example.org"] * 2):
        response = client.post(
            "/accounts/batch",
            headers=HEADERS,
            json={
                "accounts": [{"email": name} for name in names],
            },
        )
        assert response.status_code == 409
        assert accounts_file.read_bytes() == before
    for accounts in ([], [{"email": f"test{i}@example.org"} for i in range(101)]):
        assert client.post("/accounts/batch", headers=HEADERS, json={"accounts": accounts}).status_code == 422
        assert accounts_file.read_bytes() == before
    response = client.post(
        "/accounts/batch",
        headers=HEADERS,
        json={
            "accounts": [
                {"email": "one@example.org", "password": "one"},
                {"email": "two@example.org"},
            ]
        },
    )
    assert response.status_code == 201
    assert len(response.json()) == 2
    assert "password" not in response.json()[0]
    assert "password" in response.json()[1]


@pytest.mark.parametrize("content", ["broken\n", "a|hash|\n", "a|hash|a\na|hash|a\n"])
def test_malformed_storage_fails_closed(client, accounts_file, content):
    accounts_file.write_text(content)
    response = client.post("/accounts", headers=HEADERS, json={"email": "new@example.org"})
    assert response.status_code == 503
    assert accounts_file.read_text() == content


def test_missing_storage_not_recreated(client, accounts_file):
    accounts_file.unlink()
    assert client.get("/accounts", headers=HEADERS).status_code == 503
    assert client.post("/accounts", headers=HEADERS, json={"email": "new@example.org"}).status_code == 503
    assert not accounts_file.exists()


def test_write_failure_preserves_original(client, accounts_file):
    before = accounts_file.read_bytes()
    with patch("storage.os.replace", side_effect=OSError("test failure")):
        response = client.post("/accounts", headers=HEADERS, json={"email": "new@example.org"})
    assert response.status_code == 503
    assert accounts_file.read_bytes() == before
    assert not list(accounts_file.parent.glob(".postfix-accounts-*"))


def test_modify_preserves_extra_fields(client, accounts_file):
    assert client.patch("/accounts/old@example.org", headers=HEADERS, json={"password": "new"}).status_code == 200
    assert f"old@example.org|{sha512_hash('new')}|old|extra" in accounts_file.read_text()


def create_with_separate_store(path: Path, index: int):
    return AccountStore(path).create([(f"user{index}@example.org", "test")])


def test_concurrent_writes(accounts_file):
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: create_with_separate_store(accounts_file, index), range(30)))
    assert len(AccountStore(accounts_file).list_accounts()) == 31


def test_numbered_matches_cli_range(client, accounts_file):
    response = client.post(
        "/accounts/numbered",
        headers=HEADERS,
        json={
            "email": "user@example.org",
            "password": "shared-password",
            "start": 2,
            "end": 5,
        },
    )
    assert response.status_code == 201
    assert [account["email"] for account in response.json()] == [
        "user2@example.org",
        "user3@example.org",
        "user4@example.org",
    ]
    assert all("password" not in account for account in response.json())
    assert accounts_file.read_text().count(sha512_hash("shared-password")) == 3


def test_numbered_generated_passwords_distinct(client):
    response = client.post(
        "/accounts/numbered",
        headers=HEADERS,
        json={
            "email": "generated@example.org",
            "start": 0,
            "end": 3,
        },
    )
    assert response.status_code == 201
    assert len({account["password"] for account in response.json()}) == 3


@pytest.mark.parametrize("start,end", [(2, 2), (3, 2), (0, 101), ("1", 3), (True, 3)])
def test_numbered_invalid_range(client, accounts_file, start, end):
    before = accounts_file.read_bytes()
    response = client.post(
        "/accounts/numbered",
        headers=HEADERS,
        json={
            "email": "user@example.org",
            "start": start,
            "end": end,
        },
    )
    assert response.status_code == 422
    assert accounts_file.read_bytes() == before


def test_numbered_conflict_rolls_back(client, accounts_file):
    assert client.post("/accounts", headers=HEADERS, json={"email": "user2@example.org"}).status_code == 201
    before = accounts_file.read_bytes()
    response = client.post(
        "/accounts/numbered",
        headers=HEADERS,
        json={
            "email": "user@example.org",
            "start": 1,
            "end": 4,
        },
    )
    assert response.status_code == 409
    assert accounts_file.read_bytes() == before


def test_symlink_storage_rejected(tmp_path):
    target = tmp_path / "target"
    target.write_text("old@example.org|hash|old\n")
    symlink = tmp_path / "accounts.cf"
    symlink.symlink_to(target)
    with TestClient(create_app(symlink, KEY)) as test_client:
        assert test_client.get("/accounts", headers=HEADERS).status_code == 503
    assert symlink.is_symlink()
    assert target.read_text() == "old@example.org|hash|old\n"
