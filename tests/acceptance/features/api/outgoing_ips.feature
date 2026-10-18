Feature: Outgoing IPs in the API
  An admin adds the IPs of this server the proxy may go out from, then puts them in the pools of accounts
  and trusted networks. An IP is added once, and one in a pool stays until it's taken out of it.

  Background:
    Given an admin logged in to the API

  Scenario: An admin adds an IP
    When the admin sends POST "/api/outgoing-ips" with:
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    Then the API answers 201
    And the answer has:
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10", "createdById": ${admin.id}}
      """

  Scenario: An IP can't be added twice
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends POST "/api/outgoing-ips" with:
      """
      {"name": "Frankfurt 2", "ip": "203.0.113.10"}
      """
    Then the API answers 409

  Scenario: An invalid IP is refused
    When the admin sends POST "/api/outgoing-ips" with:
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.300"}
      """
    Then the API answers 422

  Scenario: An admin renames an IP
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends PATCH "/api/outgoing-ips/${exit.id}" with:
      """
      {"name": "Berlin 1"}
      """
    Then the API answers 200
    And the answer has:
      """
      {"name": "Berlin 1", "ip": "203.0.113.10"}
      """

  Scenario: An IP doesn't change its family
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends PATCH "/api/outgoing-ips/${exit.id}" with:
      """
      {"ip": "2001:db8::10"}
      """
    Then the API answers 422

  Scenario: An admin lists the IPs of one family
    Given the admin added "v4" at "/api/outgoing-ips":
      """
      {"name": "IPv4", "ip": "203.0.113.10"}
      """
    And the admin added "v6" at "/api/outgoing-ips":
      """
      {"name": "IPv6", "ip": "2001:db8::10"}
      """
    When the admin sends GET "/api/outgoing-ips?version=6"
    Then the API answers 200
    And the answer lists "v6"
    And the answer doesn't list "v4"

  Scenario: An admin deletes an IP
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends DELETE "/api/outgoing-ips/${exit.id}"
    Then the API answers 204
    When the admin sends GET "/api/outgoing-ips/${exit.id}"
    Then the API answers 404

  Scenario: An IP in a pool can't be deleted
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    And the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice", "outgoingMode": "pool", "outgoingIpIds": [${exit.id}]}
      """
    When the admin sends DELETE "/api/outgoing-ips/${exit.id}"
    Then the API answers 409
