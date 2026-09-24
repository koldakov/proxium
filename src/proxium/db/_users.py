from sqlalchemy import VARCHAR
from sqlalchemy.orm import Mapped, mapped_column

from ._base import BaseTimestampModel
from ._fields import Hash, HashField


class UserModel(BaseTimestampModel):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(
        VARCHAR(length=255),
        unique=True,
    )
    name: Mapped[str] = mapped_column(
        VARCHAR(length=150),
    )
    surname: Mapped[str] = mapped_column(
        VARCHAR(length=150),
    )
    password: Mapped[Hash] = mapped_column(
        HashField(length=255),
    )
    is_active: Mapped[bool] = mapped_column(
        default=False,
        server_default="false",
    )
