import fcntl
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from manage_accounts import generate_password, sha512_hash


class AccountConflict(Exception):
    pass


class AccountNotFound(Exception):
    pass


class InvalidAccountsFile(Exception):
    pass


class AccountStore:
    def __init__(self, path: Path):
        self.path = path
        self._mutex = threading.RLock()

    @contextmanager
    def _locked(self) -> Iterator[list[str]]:
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
                yield lines
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def _indices(lines: list[str]) -> dict[str, int]:
        return {
            line.split("|", 1)[0]: index
            for index, line in enumerate(lines)
            if line.strip() and not line.lstrip().startswith("#")
        }

    @staticmethod
    def _public(line: str) -> dict[str, str]:
        fields = line.split("|")
        return {"email": fields[0], "folder": fields[2]}

    def _write(self, lines: list[str]) -> None:
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

    def list_accounts(self) -> list[dict[str, str]]:
        with self._locked() as lines:
            return [self._public(lines[index]) for index in self._indices(lines).values()]

    def get(self, email: str) -> dict[str, str]:
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            return self._public(lines[index])

    def create(self, accounts: list[tuple[str, str | None]]) -> list[dict[str, str]]:
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
            return created

    def modify(self, email: str, password: str) -> dict[str, str]:
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            fields = lines[index].split("|")
            fields[1] = sha512_hash(password)
            lines[index] = "|".join(fields)
            self._write(lines)
            return self._public(lines[index])

    def delete(self, email: str) -> None:
        with self._locked() as lines:
            index = self._indices(lines).get(email)
            if index is None:
                raise AccountNotFound()
            del lines[index]
            self._write(lines)
