Feature: Policies in the API
  An admin writes policies: rules in order, each with a condition and its limits. Conditions are checked
  by the proxy's own parser, so what the API saves, the proxy can build. A deleted policy is taken off
  every account and network it was assigned to.

  Background:
    Given an admin logged in to the API

  Scenario: An admin writes a policy with rules
    When the admin sends POST "/api/policies" with:
      """
      {
        "name": "Basic 50 GB",
        "rules": [
          {
            "name": "SOCKS5",
            "condition": {"kind": "protocol", "protocols": ["socks5"]},
            "connectionLimits": [{"scope": "identity", "maxConnections": 5}]
          },
          {
            "name": "The rest",
            "speedLimits": [{"scope": "identity", "direction": "both", "rate": 1048576, "burst": 1048576}],
            "trafficQuotas": [{"direction": "both", "maxBytes": 53687091200, "period": "month"}]
          }
        ]
      }
      """
    Then the API answers 201
    And the answer has:
      """
      {
        "name": "Basic 50 GB",
        "isActive": true,
        "isGlobal": false,
        "createdById": ${admin.id},
        "rules": [
          {
            "name": "SOCKS5",
            "condition": {"kind": "protocol", "protocols": ["socks5"]},
            "connectionLimits": [{"scope": "identity", "maxConnections": 5}],
            "speedLimits": [],
            "trafficQuotas": []
          },
          {
            "name": "The rest",
            "condition": {"kind": "always"},
            "connectionLimits": [],
            "speedLimits": [{"scope": "identity", "direction": "both", "rate": 1048576, "burst": 1048576}],
            "trafficQuotas": [{"direction": "both", "maxBytes": 53687091200, "period": "month", "periodLength": 1}]
          }
        ]
      }
      """

  Scenario: An admin gets a policy
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan", "rules": [{"name": "All", "connectionLimits": [{"scope": "identity", "maxConnections": 5}]}]}
      """
    When the admin sends GET "/api/policies/${plan.id}"
    Then the API answers 200
    And the answer has:
      """
      {"id": ${plan.id}, "name": "Plan", "rules": [{"name": "All", "connectionLimits": [{"maxConnections": 5}]}]}
      """

  Scenario: An admin renames a policy and turns it off
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    When the admin sends PATCH "/api/policies/${plan.id}" with:
      """
      {"name": "Old plan", "isActive": false}
      """
    Then the API answers 200
    And the answer has:
      """
      {"name": "Old plan", "isActive": false}
      """

  Scenario: An admin changes a limit of a rule and adds another rule
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan", "rules": [{"name": "All", "connectionLimits": [{"scope": "identity", "maxConnections": 5}]}]}
      """
    When the admin sends PATCH "/api/policies/${plan.id}" with:
      """
      {
        "rules": [
          {
            "id": ${plan.rules.0.id},
            "name": "All",
            "connectionLimits": [{"id": ${plan.rules.0.connectionLimits.0.id}, "scope": "identity", "maxConnections": 10}]
          },
          {
            "name": "Night",
            "speedLimits": [{"scope": "global", "direction": "received", "rate": 1024, "burst": 2048}],
            "trafficQuotas": [{"direction": "sent", "maxBytes": 1048576, "period": "day", "periodLength": 7}]
          }
        ]
      }
      """
    Then the API answers 200
    And the answer has:
      """
      {
        "rules": [
          {
            "id": ${plan.rules.0.id},
            "connectionLimits": [{"id": ${plan.rules.0.connectionLimits.0.id}, "maxConnections": 10}]
          },
          {
            "name": "Night",
            "speedLimits": [{"scope": "global", "direction": "received", "rate": 1024, "burst": 2048}],
            "trafficQuotas": [{"direction": "sent", "maxBytes": 1048576, "period": "day", "periodLength": 7}]
          }
        ]
      }
      """

  Scenario: Rules left out of the list are deleted
    Given the admin added "plan" at "/api/policies":
      """
      {
        "name": "Plan",
        "rules": [
          {
            "name": "All",
            "connectionLimits": [{"scope": "identity", "maxConnections": 5}],
            "speedLimits": [{"scope": "identity", "direction": "both", "rate": 1024, "burst": 1024}],
            "trafficQuotas": [{"direction": "both", "maxBytes": 1024, "period": "total"}]
          }
        ]
      }
      """
    When the admin sends PATCH "/api/policies/${plan.id}" with:
      """
      {"rules": []}
      """
    Then the API answers 200
    And the answer has:
      """
      {"rules": []}
      """

  Scenario: A rule of another policy is refused
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    And the admin added "other" at "/api/policies":
      """
      {"name": "Other", "rules": [{"name": "All"}]}
      """
    When the admin sends PATCH "/api/policies/${plan.id}" with:
      """
      {"rules": [{"id": ${other.rules.0.id}, "name": "Stolen"}]}
      """
    Then the API answers 422

  Scenario: An admin lists policies
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    When the admin sends GET "/api/policies"
    Then the API answers 200
    And the answer lists "plan"

  Scenario: A condition of an unknown kind is refused
    When the admin sends POST "/api/policies" with:
      """
      {"name": "Plan", "rules": [{"name": "Moon", "condition": {"kind": "moon_phase"}}]}
      """
    Then the API answers 422

  Scenario: A limit must be positive
    When the admin sends POST "/api/policies" with:
      """
      {"name": "Plan", "rules": [{"name": "All", "connectionLimits": [{"scope": "identity", "maxConnections": 0}]}]}
      """
    Then the API answers 422

  Scenario: A deleted policy is taken off its accounts
    Given the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    And the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice", "policyIds": [${plan.id}]}
      """
    When the admin sends DELETE "/api/policies/${plan.id}"
    Then the API answers 204
    When the admin sends GET "/api/basic-proxy-accounts/${alice.id}/policies"
    Then the API answers 200
    And the answer doesn't list "plan"
    When the admin sends GET "/api/policies/${plan.id}"
    Then the API answers 404
