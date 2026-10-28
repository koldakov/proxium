Feature: Outgoing IPs in the API
  An admin adds the IPs of this server the proxy may go out from, then puts them in the pools of accounts
  and trusted networks. An IP is added once, and one in a pool stays until it's taken out of it. Every live proxy
  reports the IPs it has, so each IP tells how many of them lack it.

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

  Scenario Outline: An <family> IP every live proxy has
    Given a running proxy instance "first" with IPs "<ip>"
    And a pending proxy instance "second" with IPs "<other>, <ip>"
    And the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "<ip>"}
      """
    When the admin sends GET "/api/outgoing-ips/${exit.id}"
    Then the API answers 200
    And the answer has:
      """
      {"liveInstances": 2, "instancesWithoutIp": 0}
      """

    Examples:
      | family | ip           | other        |
      | IPv4   | 203.0.113.10 | 203.0.113.11 |
      | IPv6   | 2001:db8::10 | 2001:db8::11 |

  Scenario: Only live proxies count, those without the IP are told
    Given a running proxy instance "with" with IPs "203.0.113.10"
    And a running proxy instance "without" with IPs "203.0.113.11"
    And a stopped proxy instance "stopped" with IPs "203.0.113.11"
    And an unknown proxy instance "unknown" with IPs "203.0.113.11"
    And the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends GET "/api/outgoing-ips"
    Then the API answers 200
    And the answer has:
      """
      {"items": [{"id": ${exit.id}, "liveInstances": 2, "instancesWithoutIp": 1}]}
      """

  Scenario: A proxy that reported no IPs doesn't have the IP
    Given a running proxy instance "bare"
    And the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends GET "/api/outgoing-ips/${exit.id}"
    Then the answer has:
      """
      {"liveInstances": 1, "instancesWithoutIp": 1}
      """

  Scenario: With no live proxy there's nothing to miss
    Given a stopped proxy instance "stopped" with IPs "203.0.113.11"
    And the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    When the admin sends GET "/api/outgoing-ips/${exit.id}"
    Then the answer has:
      """
      {"liveInstances": 0, "instancesWithoutIp": 0}
      """

  Scenario: An admin lists IPs some proxy doesn't have, and those every one has
    Given a running proxy instance "first" with IPs "203.0.113.10, 203.0.113.11"
    And a running proxy instance "second" with IPs "203.0.113.10"
    And the admin added "everywhere" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    And the admin added "somewhere" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 2", "ip": "203.0.113.11"}
      """
    When the admin sends GET "/api/outgoing-ips?missing=true"
    Then the API answers 200
    And the answer lists "somewhere"
    And the answer doesn't list "everywhere"
    When the admin sends GET "/api/outgoing-ips?missing=false"
    Then the API answers 200
    And the answer lists "everywhere"
    And the answer doesn't list "somewhere"

  Scenario: A pool and the IPs it can take tell which proxies lack them
    Given a running proxy instance "first" with IPs "203.0.113.10"
    And a running proxy instance "second" with IPs "203.0.113.11"
    And the admin added "pooled" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 1", "ip": "203.0.113.10"}
      """
    And the admin added "spare" at "/api/outgoing-ips":
      """
      {"name": "Frankfurt 2", "ip": "203.0.113.12"}
      """
    And the admin added "alice" at "/api/basic-proxy-accounts":
      """
      {"name": "Alice", "outgoingMode": "pool", "outgoingIpIds": [${pooled.id}]}
      """
    When the admin sends GET "/api/basic-proxy-accounts/${alice.id}/outgoing-ips"
    Then the API answers 200
    And the answer has:
      """
      {"items": [{"id": ${pooled.id}, "liveInstances": 2, "instancesWithoutIp": 1}]}
      """
    When the admin sends GET "/api/basic-proxy-accounts/${alice.id}/outgoing-ips/available"
    Then the API answers 200
    And the answer has:
      """
      {"items": [{"id": ${spare.id}, "liveInstances": 2, "instancesWithoutIp": 2}]}
      """
