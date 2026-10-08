from typing import TYPE_CHECKING

from proxium.management import ManagementUtility
from proxium.management.commands import (
    ChangePasswordCommand,
    CreateSuperuserCommand,
    ImportCertificateCommand,
    MigrateCommand,
    RotateEncryptionKeyCommand,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_manage(args: Sequence[str] | None = None) -> int:
    """Run a management command, e.g. `proxium-manage createsuperuser`."""
    utility: ManagementUtility = ManagementUtility(
        [
            ChangePasswordCommand(),
            CreateSuperuserCommand(),
            ImportCertificateCommand(),
            MigrateCommand(),
            RotateEncryptionKeyCommand(),
        ],
    )
    return utility.run(args)
