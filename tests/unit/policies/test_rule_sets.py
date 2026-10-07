from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from proxium.policies import ALWAYS, Rule, RuleSet, RuleSetPolicy, policy_claims
from proxium.proxy import ConnectionLimitExceeded, ConnectionLimitPolicy, IdentityScope

if TYPE_CHECKING:
    from collections.abc import Callable

    from faker import Faker

    from proxium.proxy import Request, Session
    from tests.fixtures.policies import SwitchCondition


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
        proxy_request = proxy_request_factory(claims=policy_claims({policy_id: faker.date_object()}))

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
        proxy_request = proxy_request_factory(claims=policy_claims({faker.unique.random_int(): faker.date_object()}))

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
        proxy_request = proxy_request_factory(claims=policy_claims({policy_id: faker.date_object()}))

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

    async def test_grant_switches_to_next_rule_when_condition_stops_matching(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
        switch_condition: SwitchCondition,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        first_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        second_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(
            RuleSet(
                policies={
                    policy_id: (
                        Rule(condition=switch_condition, limits=(first_limit,)),
                        Rule(condition=ALWAYS, limits=(second_limit,)),
                    ),
                },
                global_ids=(policy_id,),
            ),
            check_interval=0,
        )
        grant = await policy.admit(proxy_request, session)
        switch_condition.matching = False

        # Act
        await grant.on_sent(faker.pyint(min_value=1))

        # Assert
        assert proxy_request.identity.subject not in first_limit.counts
        assert second_limit.counts[proxy_request.identity.subject] == 1

    async def test_grant_applies_rule_when_condition_starts_matching(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
        switch_condition: SwitchCondition,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        policy = RuleSetPolicy(
            RuleSet(
                policies={policy_id: (Rule(condition=switch_condition, limits=(limit,)),)},
                global_ids=(policy_id,),
            ),
            check_interval=0,
        )
        switch_condition.matching = False
        grant = await policy.admit(proxy_request, session)
        switch_condition.matching = True

        # Act
        await grant.on_received(faker.pyint(min_value=1))

        # Assert
        assert limit.counts[proxy_request.identity.subject] == 1

    async def test_grant_raises_and_holds_no_limit_when_next_rule_refuses(
        self,
        faker: Faker,
        proxy_request: Request,
        session: Session,
        switch_condition: SwitchCondition,
    ) -> None:
        # Arrange
        policy_id = faker.unique.random_int()
        first_limit = ConnectionLimitPolicy(IdentityScope(), limit=faker.pyint(min_value=1, max_value=10))
        full_limit = ConnectionLimitPolicy(IdentityScope(), limit=1)
        await full_limit.admit(proxy_request, session)
        policy = RuleSetPolicy(
            RuleSet(
                policies={
                    policy_id: (
                        Rule(condition=switch_condition, limits=(first_limit,)),
                        Rule(condition=ALWAYS, limits=(full_limit,)),
                    ),
                },
                global_ids=(policy_id,),
            ),
            check_interval=0,
        )
        grant = await policy.admit(proxy_request, session)
        switch_condition.matching = False

        # Act
        with pytest.raises(ConnectionLimitExceeded):
            await grant.on_sent(faker.pyint(min_value=1))
        await grant.release()

        # Assert
        assert proxy_request.identity.subject not in first_limit.counts
        assert full_limit.counts[proxy_request.identity.subject] == 1
