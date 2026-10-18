Feature: Access to the API
  Every route but logging in needs an access token. A user may do what their permissions allow: given to them
  or to a group of theirs, a superuser has them all. Permissions are checked on every request, so a user
  turned off loses access with their next one, whatever their token says.

  Scenario: The API refuses a client without a token
    When a client without a token sends GET "/api/users/me"
    Then the API answers 401

  Scenario: The API refuses an invalid token
    When a client with an invalid token sends GET "/api/users/me"
    Then the API answers 401

  Scenario Outline: A user without <permission> is refused <path>
    Given a user without permissions logged in to the API
    When the user sends GET "<path>"
    Then the API answers 403

    Examples:
      | path                      | permission                |
      | /api/basic-proxy-accounts | basic_proxy_accounts.view |
      | /api/token-proxy-accounts | token_proxy_accounts.view |
      | /api/trusted-networks     | trusted_networks.view     |
      | /api/outgoing-ips         | outgoing_ips.view         |
      | /api/policies             | policies.view             |
      | /api/certificates         | certificates.view         |
      | /api/users                | users.view                |
      | /api/groups               | groups.view               |
      | /api/settings             | settings.view             |

  Scenario Outline: A user with <permission> gets <path>
    Given a user with "<permission>" logged in to the API
    When the user sends GET "<path>"
    Then the API answers 200

    Examples:
      | path                      | permission                |
      | /api/basic-proxy-accounts | basic_proxy_accounts.view |
      | /api/token-proxy-accounts | token_proxy_accounts.view |
      | /api/trusted-networks     | trusted_networks.view     |
      | /api/outgoing-ips         | outgoing_ips.view         |
      | /api/policies             | policies.view             |
      | /api/certificates         | certificates.view         |
      | /api/users                | users.view                |
      | /api/groups               | groups.view               |
      | /api/settings             | settings.view             |

  Scenario: A permission to view doesn't let change
    Given a user with "trusted_networks.view" logged in to the API
    When the user sends POST "/api/trusted-networks" with:
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    Then the API answers 403

  Scenario: A user gets the permissions of their group
    Given a user in a group with "trusted_networks.view" logged in to the API
    When the user sends GET "/api/trusted-networks"
    Then the API answers 200

  Scenario: An admin may do everything
    Given an admin logged in to the API
    When the admin sends GET "/api/settings"
    Then the API answers 200

  Scenario Outline: Any user gets <path>
    Given a user without permissions logged in to the API
    When the user sends GET "<path>"
    Then the API answers 200

    Examples:
      | path             |
      | /api/users/me    |
      | /api/permissions |
      | /api/configs     |

  Scenario: A user turned off loses access at once
    Given a user with "trusted_networks.view" logged in to the API
    And the user is turned off
    When the user sends GET "/api/trusted-networks"
    Then the API answers 401
