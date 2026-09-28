from typing import TYPE_CHECKING

from proxium.management import ManagementUtility
from proxium.management.commands import CreateSuperuserCommand

if TYPE_CHECKING:
    from collections.abc import Sequence


def run_manage(args: Sequence[str] | None = None) -> int:
    """Run a management command, e.g. `proxium-manage createsuperuser`."""
    utility: ManagementUtility = ManagementUtility(
        [
            CreateSuperuserCommand(),
        ],
    )
    return utility.run(args)
