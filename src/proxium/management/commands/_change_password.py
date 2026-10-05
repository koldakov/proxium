import asyncio
import getpass
import sys
from typing import TYPE_CHECKING, Annotated, ClassVar

from pydantic import Field, SecretStr, TypeAdapter, ValidationError
from sqlalchemy import Result, Select, Update, select, update
from sqlalchemy.exc import NoResultFound

from proxium.db import Hash, UserModel, session_manager
from proxium.management._base import BaseAsyncCommand, CommandError

if TYPE_CHECKING:
    from argparse import ArgumentParser, Namespace


class PasswordMismatchError(Exception):
    pass


class ChangePasswordCommand(BaseAsyncCommand):
    """Like Django's `changepassword`: prompts for a new password of any user, e.g. a forgotten one.

    The tokens the user already has stop working: they follow the password.
    """

    name: ClassVar[str] = "changepassword"
    help: ClassVar[str] = "Change a user's password."

    # Same limits as the API.
    password_adapter: ClassVar[TypeAdapter[SecretStr]] = TypeAdapter(
        Annotated[
            SecretStr,
            Field(
                min_length=8,
                max_length=128,
            ),
        ],
    )

    @staticmethod
    def _get_user_id_statement(email: str, /) -> Select[tuple[int]]:
        return select(UserModel.id).where(UserModel.email == email)

    @staticmethod
    def _update_password_statement(user_id: int, password: Hash, /) -> Update:
        return update(UserModel).where(UserModel.id == user_id).values(password=password)

    def add_arguments(self, parser: ArgumentParser, /) -> None:
        parser.add_argument(
            "email",
            help="Email of the user.",
        )

    async def _get_user_id(self, email: str, /) -> int:
        async with session_manager.session() as session:
            result: Result[tuple[int]] = await session.execute(self._get_user_id_statement(email))
            try:
                return result.scalars().one()
            except NoResultFound:
                raise CommandError(f"User {email} doesn't exist.") from None

    def _error(self, message: str, /) -> None:
        self.stderr.write(f"Error: {message}\n")

    def _read_password(self) -> SecretStr:
        while True:
            try:
                return self.password_adapter.validate_python(SecretStr(getpass.getpass()))
            except ValidationError as err:
                self._error("; ".join(error["msg"] for error in err.errors(include_url=False)))

    def _check_password(self, password: SecretStr, /) -> None:
        if getpass.getpass("Password (again): ") != password.get_secret_value():
            raise PasswordMismatchError()

    def _prompt_password(self) -> SecretStr:
        while True:
            password: SecretStr = self._read_password()
            try:
                self._check_password(password)
            except PasswordMismatchError:
                self._error("Your passwords didn't match.")
            else:
                return password

    async def ahandle(self, args: Namespace, /) -> None:
        if not sys.stdin.isatty():
            raise CommandError("Not running in a TTY.")

        user_id: int = await self._get_user_id(args.email)
        self.stdout.write(f"Changing password for {args.email}.\n")
        password: SecretStr = self._prompt_password()

        # Hashing is slow CPU work, it would stall the loop.
        hashed: Hash = await asyncio.to_thread(Hash.create, password.get_secret_value())
        async with session_manager.session() as session:
            await session.execute(self._update_password_statement(user_id, hashed))
            await session.commit()

        self.stdout.write("Password changed successfully.\n")
