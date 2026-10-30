# SPDX-License-Identifier: GPL-3.0-or-later
"""Stockage des comptes mail : fichier docker-mailserver postfix-accounts.cf.

Écritures atomiques (fichier temporaire + ``os.replace``) sous verrou
``flock`` sur un fichier de verrou séparé, pour rester valide malgré le
remplacement d'inode.
"""

import fcntl
import os
import tempfile
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger

from manage_accounts import generate_password, sha512_hash


class AccountConflict(Exception):
    pass


class AccountNotFound(Exception):
    pass


class InvalidAccountsFile(Exception):
    pass


class AccountStore:
    def __init__(self, path: Path):
        logger.debug("AccountStore.__init__ : entrée (path={})", path)
        self.path = path
        self._mutex = threading.RLock()
        logger.debug("AccountStore.__init__ : sortie")

    @contextmanager
    def _locked(self) -> Iterator[list[str]]:
        logger.debug("AccountStore._locked : entrée (verrou sur {})", self.path.name)
        # A separate inode keeps the lock valid across atomic file replacement.
        with self._mutex, self.path.with_name(self.path.name + ".lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                if self.path.is_symlink():
                    raise InvalidAccountsFile("Symlink account files are not supported")
                lines = self.path.read_text(encoding="utf-8").splitlines()
                seen = set()
                for line in lines:
                    if not line.strip() or line.lstrip().startswith("#"):
                        continue
                    fields = line.split("|")
                    if len(fields) < 3 or not all(fields[:3]) or fields[0] in seen:
                        raise InvalidAccountsFile("Malformed or duplicate account record")
                    seen.add(fields[0])
                logger.debug("AccountStore._locked : sortie ({} lignes lues)", len(lines))
                yield lines
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
            logger.debug("AccountStore._locked : sortie (verrou relâché)")

    @staticmethod
    def _indices(lines: list[str]) -> dict[str, int]:
        return {
            line.split("|", 1)[0]: index
            for index, line in enumerate(lines)
            if line.strip() and not line.lstrip().startswith("#")
        }

    @staticmethod
    def _public(line: str) -> dict[str, str]:
        logger.debug("AccountStore._public : entrée")
        fields = line.split("|")
        logger.debug("AccountStore._public : sortie")
        return {"email": fields[0], "folder": fields[2]}

    def _write(self, lines: list[str]) -> None:
        logger.debug("AccountStore._write : entrée ({} lignes à écrire)", len(lines))
        metadata = self.path.stat()
        fd, temporary = tempfile.mkstemp(prefix=".postfix-accounts-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                os.fchown(stream.fileno(), metadata.st_uid, metadata.st_gid)
                os.fchmod(stream.fileno(), metadata.st_mode & 0o777)
                stream.write("\n".join(lines) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        logger.debug("AccountStore._write : sortie (écriture atomique terminée)")

    def list_accounts(self) -> list[dict[str, str]]:
        logger.debug("AccountStore.list_accounts : entrée")
        with self._locked() as lines:
            accounts = [self._public(lines[index]) for index in self._indices(lines).values()]
        logger.debug("AccountStore.list_accounts : sortie (total={})", len(accounts))
        return accounts

    def get(self, email: str) -> dict[str, str]:
        logger.debug("AccountStore.get : entrée (email={})", email)
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            account = self._public(lines[index])
        logger.debug("AccountStore.get : sortie (compte trouvé)")
        return account

    def create(self, accounts: list[tuple[str, str | None]]) -> list[dict[str, str]]:
        logger.debug("AccountStore.create : entrée (demandés={})", len(accounts))
        with self._locked() as lines:
            existing = self._indices(lines)
            names = [email for email, _ in accounts]
            if len(set(names)) != len(names) or any(email in existing for email in names):
                raise AccountConflict()
            created = []
            for email, supplied_password in accounts:
                password = supplied_password if supplied_password is not None else generate_password()
                folder = email.split("@", 1)[0]
                lines.append(f"{email}|{sha512_hash(password)}|{folder}")
                account = {"email": email, "folder": folder}
                if supplied_password is None:
                    account["password"] = password
                created.append(account)
            self._write(lines)
            logger.debug("AccountStore.create : sortie (créés={})", len(created))
            return created

    def modify(self, email: str, password: str) -> dict[str, str]:
        logger.debug("AccountStore.modify : entrée (email={})", email)
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            fields = lines[index].split("|")
            fields[1] = sha512_hash(password)
            lines[index] = "|".join(fields)
            self._write(lines)
            account = self._public(lines[index])
        logger.debug("AccountStore.modify : sortie (mot de passe modifié)")
        return account

    def delete(self, email: str) -> None:
        logger.debug("AccountStore.delete : entrée (email={})", email)
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            del lines[index]
            self._write(lines)
        logger.debug("AccountStore.delete : sortie (compte supprimé)")
