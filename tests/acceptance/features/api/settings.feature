Feature: Settings in the API
  An admin reads and replaces the proxy settings: the private networks it may reach, timeouts and how long
  it reuses checks of clients. The proxy applies them to new connections within a few seconds.

  Background:
    Given an admin logged in to the API

  Scenario: The settings start at their defaults
    When the admin sends GET "/api/settings"
    Then the API answers 200
    And the answer has:
      """
      {
        "guardAllow": [],
        "handshakeTimeout": 10.0,
        "idleTimeout": 300.0,
        "connectTimeout": 10.0,
        "basicAccountCacheTtl": 10.0,
        "certificateCacheTtl": 10.0
      }
      """

  Scenario: An admin replaces the settings
    When the admin sends PUT "/api/settings" with:
      """
      {
        "guardAllow": ["10.0.0.0/8"],
        "handshakeTimeout": 5.0,
        "idleTimeout": 600.0,
        "connectTimeout": 5.0,
        "basicAccountCacheTtl": 30.0,
        "basicAccountRefusalCacheTtl": 5.0,
        "tokenAccountCacheTtl": 30.0,
        "tokenAccountRefusalCacheTtl": 5.0,
        "trustedNetworkCacheTtl": 30.0,
        "trustedNetworkRefusalCacheTtl": 5.0,
        "certificateCacheTtl": 60.0
      }
      """
    Then the API answers 200
    When the admin sends GET "/api/settings"
    Then the answer has:
      """
      {"guardAllow": ["10.0.0.0/8"], "handshakeTimeout": 5.0, "idleTimeout": 600.0, "certificateCacheTtl": 60.0}
      """

  Scenario Outline: A <setting> out of range is refused
    When the admin sends PUT "/api/settings" with:
      """
      {
        "guardAllow": <guard_allow>,
        "handshakeTimeout": <handshake_timeout>,
        "idleTimeout": 300.0,
        "connectTimeout": 10.0,
        "basicAccountCacheTtl": 10.0,
        "basicAccountRefusalCacheTtl": 10.0,
        "tokenAccountCacheTtl": 10.0,
        "tokenAccountRefusalCacheTtl": 10.0,
        "trustedNetworkCacheTtl": 10.0,
        "trustedNetworkRefusalCacheTtl": 10.0,
        "certificateCacheTtl": 10.0
      }
      """
    Then the API answers 422

    Examples:
      | setting                | guard_allow                  | handshake_timeout |
      | zero timeout           | []                           | 0.0               |
      | network with host bits | ["10.0.0.1/8"]               | 10.0              |
      | network given twice    | ["10.0.0.0/8", "10.0.0.0/8"] | 10.0              |

  Scenario: The admin UI gets the limits of the API
    When the admin sends GET "/api/configs"
    Then the API answers 200
    And the answer has "policiesMaxPerOwner"
    And the answer has "globalPoliciesMax"
