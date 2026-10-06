from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

# The identity claim with the ids of the policies assigned to the account or trusted network.
POLICIES_CLAIM: Final[str] = "policies"


def policy_claims(policy_ids: Sequence[int], /) -> dict[str, Any]:
    """Claims for an identity with these policies assigned. Without any, only global policies apply to it."""
    if not policy_ids:
        return {}
    return {POLICIES_CLAIM: tuple(policy_ids)}
