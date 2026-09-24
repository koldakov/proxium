"""${message}

Revision ID: ${up_revision}
${("Revises: " + comma(down_revision)).rstrip()}
Create Date: ${create_date}

"""
from typing import TYPE_CHECKING

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

if TYPE_CHECKING:
    from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = ${repr(up_revision)}
down_revision: str | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
