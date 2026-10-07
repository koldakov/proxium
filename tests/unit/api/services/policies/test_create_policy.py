from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from proxium.api.services.policies._create_policy import CreatePolicyRuleRequest

if TYPE_CHECKING:
    from faker import Faker


class TestCreatePolicyRuleRequest:
    def test_validate_raises_when_proxy_would_refuse_condition(self, faker: Faker) -> None:
        # Arrange
        # Of the right shape for the API, but no such zone: the proxy couldn't build the rule.
        condition = {
            "kind": "schedule",
            "days": [faker.pyint(min_value=1, max_value=7)],
            "start": "09:00",
            "end": "18:00",
            "timezone": f"Unknown/{faker.word()}",
        }

        # Act & Assert
        with pytest.raises(ValidationError, match="Unknown time zone"):
            CreatePolicyRuleRequest.model_validate({"name": faker.word(), "condition": condition})

    def test_validate_raises_when_condition_has_too_many_blocks(self, faker: Faker) -> None:
        # Arrange
        # 64 blocks in a group pass its own cap, with the group itself they're 65.
        condition = {"kind": "any", "conditions": [{"kind": "always"}] * 64}

        # Act & Assert
        with pytest.raises(ValidationError, match="at most 64 blocks"):
            CreatePolicyRuleRequest.model_validate({"name": faker.word(), "condition": condition})
