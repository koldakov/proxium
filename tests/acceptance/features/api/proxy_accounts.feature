Feature: Proxy accounts in the API
  An admin creates proxy accounts: basic ones with a username and password, token ones with a bearer token.
  The API shows the secret once, on creation, and never again. Credentials don't change: an account gets
  revoked for good, a new login is a new account. The proxy lets the account in as soon as it's created.

  Both kinds are managed alike: names, pools of outgoing IPs, policies and traffic.

  Background:
    Given an admin logged in to the API

  Scenario: An admin creates a basic account
    When the admin sends POST "/api/basic-proxy-accounts" with:
      """
      {"name": "Alice"}
      """
    Then the API answers 201
    And the answer has "username"
    And the answer has "password"
    And the answer has:
      """
      {"name": "Alice", "isActive": true, "expiresAt": null, "outgoingMode": "system", "createdById": ${admin.id}}
      """

  Scenario: A basic account reaches the website as soon as it's created
    Given a website
    And the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice"}
      """
    And the proxy is running
    When the client requests the website over SOCKS5 with the credentials of "alice"
    Then the client gets the website

  Scenario: The password isn't shown again
    Given the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice"}
      """
    When the admin sends GET "/api/basic-proxy-accounts/${alice.id}"
    Then the API answers 200
    And the answer has:
      """
      {"id": ${alice.id}, "name": "Alice", "username": ${alice.username}}
      """
    And the answer has no "password"

  Scenario: A revoked account is refused by the proxy
    Given a website
    And the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice"}
      """
    And the admin sent POST "/api/basic-proxy-accounts/${alice.id}/revoke"
    And the proxy is running
    When the client requests the website over HTTP with the credentials of "alice"
    Then the proxy asks for credentials

  Scenario: An admin creates a token account
    When the admin sends POST "/api/token-proxy-accounts" with:
      """
      {"name": "Backend"}
      """
    Then the API answers 201
    And the answer has "key"
    And the answer has "token"
    And the answer has:
      """
      {"name": "Backend", "isActive": true, "expiresAt": null, "outgoingMode": "system", "createdById": ${admin.id}}
      """

  Scenario: A token account reaches the website as soon as it's created
    Given a website
    And the admin added "backend" at "/api/token-proxy-accounts":
      """
      {"name": "Backend"}
      """
    And the proxy is running
    When the client requests the website over HTTP with the token of "backend"
    Then the client gets the website

  Scenario: The token isn't shown again
    Given the admin added "backend" at "/api/token-proxy-accounts":
      """
      {"name": "Backend"}
      """
    When the admin sends GET "/api/token-proxy-accounts/${backend.id}"
    Then the API answers 200
    And the answer has:
      """
      {"id": ${backend.id}, "name": "Backend", "key": ${backend.key}}
      """
    And the answer has no "token"

  Scenario: A revoked token is refused by the proxy
    Given a website
    And the admin added "backend" at "/api/token-proxy-accounts":
      """
      {"name": "Backend"}
      """
    And the admin sent POST "/api/token-proxy-accounts/${backend.id}/revoke"
    And the proxy is running
    When the client requests the website over HTTP with the token of "backend"
    Then the proxy asks for credentials

  Scenario Outline: An admin lists <accounts>
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends GET "/api/<accounts>"
    Then the API answers 200
    And the answer lists "alice"

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: An admin renames one of <accounts>
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends PATCH "/api/<accounts>/${alice.id}" with:
      """
      {"name": "Alice Smith"}
      """
    Then the API answers 200
    And the answer has:
      """
      {"id": ${alice.id}, "name": "Alice Smith"}
      """

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: One of <accounts> expiring in the past is refused
    When the admin sends POST "/api/<accounts>" with:
      """
      {"name": "Alice", "expiresAt": "2000-01-01T00:00:00Z"}
      """
    Then the API answers 422

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: A revoked one of <accounts> stays in the list, turned off
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends POST "/api/<accounts>/${alice.id}/revoke"
    Then the API answers 204
    When the admin sends GET "/api/<accounts>/${alice.id}"
    Then the answer has:
      """
      {"isActive": false}
      """

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: An admin fills the pool of one of <accounts> and switches it to the pool
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends GET "/api/<accounts>/${alice.id}/outgoing-ips/available"
    Then the answer lists "exit"
    When the admin sends PUT "/api/<accounts>/${alice.id}/outgoing-ips/${exit.id}"
    Then the API answers 204
    When the admin sends GET "/api/<accounts>/${alice.id}/outgoing-ips"
    Then the answer lists "exit"
    When the admin sends PATCH "/api/<accounts>/${alice.id}" with:
      """
      {"outgoingMode": "pool"}
      """
    Then the API answers 200
    And the answer has:
      """
      {"outgoingMode": "pool"}
      """

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: The pool mode of <accounts> needs IPs in the pool
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends PATCH "/api/<accounts>/${alice.id}" with:
      """
      {"outgoingMode": "pool"}
      """
    Then the API answers 409

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: An admin takes an IP out of the pool of one of <accounts>
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    And the admin sent PUT "/api/<accounts>/${alice.id}/outgoing-ips/${exit.id}"
    When the admin sends DELETE "/api/<accounts>/${alice.id}/outgoing-ips/${exit.id}"
    Then the API answers 204
    When the admin sends GET "/api/<accounts>/${alice.id}/outgoing-ips"
    Then the answer doesn't list "exit"

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: The last IP of a pool in use of <accounts> stays
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice", "outgoingMode": "pool", "outgoingIpIds": [${exit.id}]}
      """
    When the admin sends DELETE "/api/<accounts>/${alice.id}/outgoing-ips/${exit.id}"
    Then the API answers 409

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: An admin assigns a policy to one of <accounts> and takes it off
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    And the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    When the admin sends GET "/api/<accounts>/${alice.id}/policies/available"
    Then the answer lists "plan"
    When the admin sends PUT "/api/<accounts>/${alice.id}/policies/${plan.id}"
    Then the API answers 204
    When the admin sends GET "/api/<accounts>/${alice.id}/policies"
    Then the answer lists "plan"
    When the admin sends PATCH "/api/<accounts>/${alice.id}/policies/${plan.id}" with:
      """
      {"startsOn": "2026-01-15"}
      """
    Then the API answers 204
    When the admin sends DELETE "/api/<accounts>/${alice.id}/policies/${plan.id}"
    Then the API answers 204
    When the admin sends GET "/api/<accounts>/${alice.id}/policies"
    Then the answer doesn't list "plan"

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: A global policy isn't assigned to <accounts>: it applies anyway
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    And the admin added "everyone" at "/api/policies":
      """
      {"name": "Everyone", "isGlobal": true}
      """
    When the admin sends PUT "/api/<accounts>/${alice.id}/policies/${everyone.id}"
    Then the API answers 409

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |

  Scenario Outline: A new one of <accounts> has no traffic yet
    Given the admin added "alice" at "/api/<accounts>":
      """
      {"name": "Alice"}
      """
    When the admin sends GET "/api/traffic/<accounts>/${alice.id}/total"
    Then the API answers 200
    And the answer has:
      """
      {"bytesSent": 0, "bytesReceived": 0}
      """
    When the admin sends GET "/api/traffic/<accounts>/${alice.id}"
    Then the API answers 200
    And the answer has:
      """
      {"items": []}
      """

    Examples:
      | accounts             |
      | basic-proxy-accounts |
      | token-proxy-accounts |
