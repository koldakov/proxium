from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import date

# The identity claim with the policies assigned to the account or trusted network: the day each assignment's quota
# periods count from, by policy id.
POLICIES_CLAIM: Final[str] = "policies"


def policy_claims(assignments: Mapping[int, date], /) -> dict[str, Any]:
    """Claims for an identity with these policies assigned. Without any, only global policies apply to it."""
    if not assignments:
        return {}
    return {POLICIES_CLAIM: dict(assignments)}
