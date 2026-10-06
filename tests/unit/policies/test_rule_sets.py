from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.policies import ALWAYS, Rule, RuleSet, RuleSetPolicy, policy_claims
from proxium.proxy import ConnectionLimitExceeded, ConnectionLimitPolicy, IdentityScope

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session


class TestRuleSetPolicy:
    async def test_admit_applies_global_policy(self, faker: Faker, proxy_request: Request, session: Session) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(
            RuleSet(policies={policy_id: (Rule(condition=ALWAYS, limits=(limit,)),)}, global_ids=(policy_id,)),
        )

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert limit.counts[proxy_request.identity.subject] == 1

    async def test_admit_applies_assigned_policy(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(RuleSet(policies={policy_id: (Rule(condition=ALWAYS, limits=(limit,)),)}))
        proxy_request = proxy_request_factory(claims=policy_claims([policy_id]))

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert limit.counts[proxy_request.identity.subject] == 1

    async def test_admit_skips_policy_when_not_global_nor_assigned(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(RuleSet(policies={policy_id: (Rule(condition=ALWAYS, limits=(limit,)),)}))
        proxy_request = proxy_request_factory(claims=policy_claims([faker.unique.random_int()]))

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert proxy_request.identity.subject not in limit.counts

    async def test_admit_applies_policy_once_when_global_and_assigned(
        self,
        faker: Faker,
        proxy_request_factory: Callable[..., Request],
        session: Session,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(
            RuleSet(policies={policy_id: (Rule(condition=ALWAYS, limits=(limit,)),)}, global_ids=(policy_id,)),
        )
        proxy_request = proxy_request_factory(claims=policy_claims([policy_id]))

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert limit.counts[proxy_request.identity.subject] == 1

    async def test_admit_applies_first_matching_rule_only(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        first_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        second_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(
            RuleSet(
                policies={
                    policy_id: (
                        Rule(condition=ALWAYS, limits=(first_limit,)),
                        Rule(condition=ALWAYS, limits=(second_limit,)),
                    ),
                },
                global_ids=(policy_id,),
            ),
        )

        # Act
        await policy.admit(proxy_request, session)

        # Assert
        assert proxy_request.identity.subject not in second_limit.counts

    async def test_admit_releases_admitted_limits_when_later_limit_refuses(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        admitting_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        full_limit = ConnectionLimitPolicy(IdentityScope(), limit=1)
        await full_limit.admit(proxy_request, session)
        policy = RuleSetPolicy(
            RuleSet(
                policies={policy_id: (Rule(condition=ALWAYS, limits=(admitting_limit, full_limit)),)},
                global_ids=(policy_id,),
            ),
        )

        # Act
        with pytest.raises(ConnectionLimitExceeded):
            await policy.admit(proxy_request, session)

        # Assert
        assert proxy_request.identity.subject not in admitting_limit.counts

    async def test_release_releases_every_limit(self, faker: Faker, proxy_request: Request, session: Session) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limits = [
            ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
            for _ in range(faker.pyint(min_value=2, max_value=5))
        ]
        policy = RuleSetPolicy(
            RuleSet(policies={policy_id: (Rule(condition=ALWAYS, limits=tuple(limits)),)}, global_ids=(policy_id,)),
        )
        grant = await policy.admit(proxy_request, session)

        # Act
        await grant.release()

        # Assert
        assert all(proxy_request.identity.subject not in limit.counts for limit in limits)
