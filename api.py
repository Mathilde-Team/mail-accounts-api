# SPDX-License-Identifier: GPL-3.0-or-later
"""API FastAPI de gestion des comptes mail docker-mailserver.

Toutes les routes ``/accounts`` exigent une clé Bearer. Seuls les mots de
passe générés sont renvoyés, une seule fois à la création ; les hashes ne
sont jamais exposés.
"""

import os
import secrets
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from storage import AccountConflict, AccountNotFound, AccountStore, InvalidAccountsFile

# Version de l'application : coïncide avec [project] version de pyproject.toml
# (vérifié par tests/test_version.py, SOCLE.md §1 — une seule source de vérité).
VERSION = "1.0.0"

Email = Annotated[
    str,
    Field(
        min_length=3,
        max_length=254,
        pattern=r"^[A-Za-z0-9_+%-]+(?:\.[A-Za-z0-9_+%-]+)*@"
        r"[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?"
        r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$",
    ),
]
Password = Annotated[SecretStr, Field(min_length=1, max_length=1024)]


class CreateAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: Email = Field(description="Adresse du compte.", examples=["user@example.org"])
    password: Password | None = Field(
        default=None, description="Omis ou null : generation automatique ; sinon mot de passe fourni."
    )


class ChangePassword(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: Password = Field(description="Nouveau mot de passe, jamais renvoye dans la reponse.")


class BatchAccounts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    accounts: list[CreateAccount] = Field(min_length=1, max_length=100)


class NumberedAccounts(CreateAccount):
    start: int = Field(strict=True, description="Premier suffixe numerique inclus.", examples=[1])
    end: int = Field(strict=True, description="Dernier suffixe numerique exclu, comme range().", examples=[4])

    @model_validator(mode="after")
    def validate_range(self) -> "NumberedAccounts":
        logger.debug("NumberedAccounts.validate_range : entrée (start={}, end={})", self.start, self.end)
        if not 1 <= self.end - self.start <= 100:
            raise ValueError("A numbered request must create between 1 and 100 accounts")
        if max(len(str(self.start)), len(str(self.end - 1))) + len(self.email) > 254:
            raise ValueError("Numbered email address is too long")
        logger.debug("NumberedAccounts.validate_range : sortie (plage validée)")
        return self


class Account(BaseModel):
    email: str
    folder: str


class CreatedAccount(Account):
    password: str | None = None


class AccountList(BaseModel):
    accounts: list[Account]
    total: int


class JournalAuthentification:
    """Traçage des authentifications (SOCLE §7).

    INFO tant qu'aucune authentification n'a réussi — et après chaque nouvel
    échec —, DEBUG après une première réussite ; tout échec réactive le mode
    bavard. Aucun secret dans les messages (SOCLE §8, règle 6).
    """

    def __init__(self) -> None:
        logger.debug("JournalAuthentification.__init__ : entrée")
        self._bavard = True
        logger.debug("JournalAuthentification.__init__ : sortie")

    def etape(self, message: str) -> None:
        logger.debug("JournalAuthentification.etape : entrée")
        logger.log("INFO" if self._bavard else "DEBUG", "auth : {}", message)
        logger.debug("JournalAuthentification.etape : sortie")

    def reussie(self) -> None:
        logger.debug("JournalAuthentification.reussie : entrée")
        if self._bavard:
            self._bavard = False
            logger.debug("auth : première authentification réussie, passage en DEBUG")
        logger.debug("auth : authentification acceptée")

    def echouee(self) -> None:
        logger.debug("JournalAuthentification.echouee : entrée")
        self._bavard = True
        logger.warning("auth : authentification refusée (clé absente ou incorrecte)")
        logger.debug("JournalAuthentification.echouee : sortie")


def create_app(accounts_file: Path | None = None, api_key: str | None = None) -> FastAPI:
    logger.debug("create_app : entrée (accounts_file fourni={})", accounts_file is not None)
    load_dotenv(Path(__file__).with_name(".env"), override=False)
    key = api_key if api_key is not None else os.environ.get("MAIL_API_KEY", "")
    if len(key) < 32 or not key.isascii() or any(char.isspace() for char in key):
        logger.error("create_app : MAIL_API_KEY invalide (longueur={}, ascii={})", len(key), key.isascii())
        raise RuntimeError("MAIL_API_KEY must contain at least 32 non-whitespace ASCII characters")
    path = accounts_file or Path(os.environ.get("MAIL_ACCOUNTS_FILE", "/app/12-mail/config/postfix-accounts.cf"))
    store = AccountStore(path)
    app = FastAPI(
        title="Mail Accounts API",
        version=VERSION,
        description=(
            "Gestion docker-mailserver : list, add, adds, modify et delete. "
            "Toutes les routes /accounts exigent une cle Bearer. "
            "Seuls les mots de passe generes sont renvoyes, une seule fois a la creation. "
            "Les hashes ne sont jamais exposes. DELETE ne supprime pas les boites sur disque."
        ),
        swagger_ui_parameters={"persistAuthorization": False},
    )
    security = HTTPBearer(auto_error=False)
    journal_auth = JournalAuthentification()

    def authenticate(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    ) -> None:
        logger.debug("authenticate : entrée (credentials présent={})", credentials is not None)
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode("utf-8"), key.encode("ascii")
        ):
            journal_auth.echouee()
            raise HTTPException(
                status_code=401,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        journal_auth.reussie()
        logger.debug("authenticate : sortie (authentification acceptée)")

    @app.middleware("http")
    async def no_cache(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        logger.debug("no_cache : entrée ({} {})", request.method, request.url.path)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        logger.debug("no_cache : sortie (statut={})", response.status_code)
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        logger.debug("validation_error : entrée")
        logger.warning(
            "validation_error : requête rejetée ({} erreurs de validation)",
            len(exc.errors()),
        )
        # Pydantic's default errors include the input, which can contain passwords.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {"loc": error["loc"], "type": error["type"], "msg": "Invalid value"} for error in exc.errors()
                ]
            },
        )

    @app.exception_handler(AccountConflict)
    async def conflict(request: Request, exc: AccountConflict) -> JSONResponse:
        logger.debug("conflict : compte déjà existant")
        return JSONResponse(status_code=409, content={"detail": "Account already exists"})

    @app.exception_handler(AccountNotFound)
    async def not_found(request: Request, exc: AccountNotFound) -> JSONResponse:
        logger.debug("not_found : compte absent")
        return JSONResponse(status_code=404, content={"detail": "Account not found"})

    async def storage_error(request: Request, exc: Exception) -> JSONResponse:
        logger.debug("storage_error : entrée")
        logger.error("Account storage failed ({})", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "Account storage unavailable"})

    app.add_exception_handler(OSError, storage_error)
    app.add_exception_handler(UnicodeError, storage_error)
    app.add_exception_handler(InvalidAccountsFile, storage_error)

    @app.get("/health", tags=["Service"], summary="Verifier le processus API")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    router = APIRouter(
        prefix="/accounts",
        tags=["Comptes mail"],
        dependencies=[Depends(authenticate)],
        responses={
            401: {"description": "Cle Bearer absente ou incorrecte."},
            503: {"description": "Fichier de comptes absent, malforme ou inaccessible."},
        },
    )

    @router.get("", response_model=AccountList, summary="Lister les comptes (list)")
    def list_accounts() -> dict[str, object]:
        logger.debug("list_accounts : entrée")
        accounts = store.list_accounts()
        logger.debug("list_accounts : sortie (total={})", len(accounts))
        return {"accounts": accounts, "total": len(accounts)}

    @router.post(
        "",
        status_code=201,
        response_model=CreatedAccount,
        response_model_exclude_none=True,
        summary="Ajouter un compte (add)",
        responses={409: {"description": "Compte deja existant."}},
    )
    def add_account(body: CreateAccount) -> dict[str, str]:
        logger.debug("add_account : entrée (email présent, mot de passe fourni={})", body.password is not None)
        password = body.password.get_secret_value() if body.password is not None else None
        created = store.create([(body.email, password)])[0]
        logger.debug("add_account : sortie (compte créé)")
        return created

    @router.post(
        "/batch",
        status_code=201,
        response_model=list[CreatedAccount],
        response_model_exclude_none=True,
        summary="Ajouter un lot de comptes (transaction atomique)",
        responses={409: {"description": "Doublon dans le lot ou compte existant ; aucun ajout."}},
    )
    def add_accounts(body: BatchAccounts) -> list[dict[str, str]]:
        logger.debug("add_accounts : entrée (taille du lot={})", len(body.accounts))
        created = store.create(
            [
                (account.email, account.password.get_secret_value() if account.password is not None else None)
                for account in body.accounts
            ]
        )
        logger.debug("add_accounts : sortie (créés={})", len(created))
        return created

    @router.post(
        "/numbered",
        status_code=201,
        response_model=list[CreatedAccount],
        response_model_exclude_none=True,
        summary="Ajouter des comptes numerotes (adds)",
        description=(
            "Equivalent de manage_accounts.py adds EMAIL PASSWORD START END. "
            "Pour user@example.org, start=1 et end=4 : user1, user2 et user3. "
            "Le mot de passe fourni est partage ; si omis, chaque compte recoit "
            "un mot de passe aleatoire distinct. Lot atomique de 1 a 100 comptes."
        ),
        responses={409: {"description": "Un compte existe deja ; aucun ajout."}},
    )
    def add_numbered_accounts(body: NumberedAccounts) -> list[dict[str, str]]:
        logger.debug("add_numbered_accounts : entrée (start={}, end={})", body.start, body.end)
        local, domain = body.email.split("@", 1)
        password = body.password.get_secret_value() if body.password is not None else None
        created = store.create([(f"{local}{index}@{domain}", password) for index in range(body.start, body.end)])
        logger.debug("add_numbered_accounts : sortie (créés={})", len(created))
        return created

    @router.get(
        "/{email}",
        response_model=Account,
        summary="Lire un compte sans son hash",
        responses={404: {"description": "Compte absent."}},
    )
    def get_account(email: str) -> dict[str, str]:
        logger.debug("get_account : entrée (email={})", email)
        account = store.get(email)
        logger.debug("get_account : sortie (compte trouvé)")
        return account

    @router.patch(
        "/{email}",
        response_model=Account,
        summary="Modifier le mot de passe (modify)",
        responses={404: {"description": "Compte absent."}},
    )
    def modify_account(email: str, body: ChangePassword) -> dict[str, str]:
        logger.debug("modify_account : entrée (email={})", email)
        account = store.modify(email, body.password.get_secret_value())
        logger.debug("modify_account : sortie (mot de passe modifié)")
        return account

    @router.delete(
        "/{email}",
        status_code=204,
        summary="Supprimer un compte (delete)",
        description="Suppression sans confirmation interactive. Les donnees de la boite restent sur disque.",
        responses={404: {"description": "Compte absent."}},
    )
    def delete_account(email: str) -> Response:
        logger.debug("delete_account : entrée (email={})", email)
        store.delete(email)
        logger.debug("delete_account : sortie (compte supprimé)")
        return Response(status_code=204)

    app.include_router(router)
    logger.debug("create_app : sortie (application configurée)")
    return app
