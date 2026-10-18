Feature: Trusted networks in the API
  An admin adds, changes, lists and deletes trusted networks, gives them a pool of outgoing IPs and assigns
  them policies. A network is trusted once and without host bits: 10.0.0.1/8 is a typo.

  Background:
    Given an admin logged in to the API

  Scenario: An admin trusts a network
    When the admin sends POST "/api/trusted-networks" with:
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    Then the API answers 201
    And the answer has:
      """
      {
        "name": "Office",
        "network": "10.0.0.0/8",
        "isActive": true,
        "outgoingMode": "system",
        "createdById": ${admin.id}
      }
      """

  Scenario: An admin gets a network
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends GET "/api/trusted-networks/${office.id}"
    Then the API answers 200
    And the answer has:
      """
      {"id": ${office.id}, "name": "Office", "network": "10.0.0.0/8"}
      """

  Scenario: An admin renames a network and turns it off
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends PATCH "/api/trusted-networks/${office.id}" with:
      """
      {"name": "Headquarters", "isActive": false}
      """
    Then the API answers 200
    And the answer has:
      """
      {"name": "Headquarters", "network": "10.0.0.0/8", "isActive": false}
      """

  Scenario: An admin finds the networks containing an address
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    And the admin added "lab" at "/api/trusted-networks":
      """
      {"name": "Lab", "network": "192.168.0.0/16"}
      """
    When the admin sends GET "/api/trusted-networks?contains=10.1.2.0/24"
    Then the API answers 200
    And the answer lists "office"
    And the answer doesn't list "lab"

  Scenario: An admin deletes a network
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends DELETE "/api/trusted-networks/${office.id}"
    Then the API answers 204
    When the admin sends GET "/api/trusted-networks/${office.id}"
    Then the API answers 404

  Scenario: A network with traffic stays: its history is kept
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    And the network "office" has traffic
    When the admin sends DELETE "/api/trusted-networks/${office.id}"
    Then the API answers 409

  Scenario: A network can't be trusted twice
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends POST "/api/trusted-networks" with:
      """
      {"name": "Office again", "network": "10.0.0.0/8"}
      """
    Then the API answers 409

  Scenario: A network with host bits is refused
    When the admin sends POST "/api/trusted-networks" with:
      """
      {"name": "Office", "network": "10.0.0.1/8"}
      """
    Then the API answers 422

  Scenario: A network goes out from its pool
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8", "outgoingMode": "pool", "outgoingIpIds": [${exit.id}]}
      """
    When the admin sends GET "/api/trusted-networks/${office.id}/outgoing-ips"
    Then the API answers 200
    And the answer lists "exit"

  Scenario: An admin fills the pool of a network and takes an IP out of it
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends GET "/api/trusted-networks/${office.id}/outgoing-ips/available"
    Then the answer lists "exit"
    When the admin sends PUT "/api/trusted-networks/${office.id}/outgoing-ips/${exit.id}"
    Then the API answers 204
    When the admin sends GET "/api/trusted-networks/${office.id}/outgoing-ips/available"
    Then the answer doesn't list "exit"
    When the admin sends DELETE "/api/trusted-networks/${office.id}/outgoing-ips/${exit.id}"
    Then the API answers 204
    When the admin sends GET "/api/trusted-networks/${office.id}/outgoing-ips"
    Then the answer doesn't list "exit"

  Scenario: The last IP of a pool in use stays
    Given the admin added "exit" at "/api/outgoing-ips":
      """
      {"name": "Exit", "ip": "203.0.113.10"}
      """
    And the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8", "outgoingMode": "pool", "outgoingIpIds": [${exit.id}]}
      """
    When the admin sends DELETE "/api/trusted-networks/${office.id}/outgoing-ips/${exit.id}"
    Then the API answers 409

  Scenario: A new network has no traffic yet
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    When the admin sends GET "/api/traffic/trusted-networks/${office.id}/total"
    Then the API answers 200
    And the answer has:
      """
      {"bytesSent": 0, "bytesReceived": 0}
      """
    When the admin sends GET "/api/traffic/trusted-networks/${office.id}"
    Then the API answers 200
    And the answer has:
      """
      {"items": []}
      """

  Scenario: The pool mode needs IPs in the pool
    When the admin sends POST "/api/trusted-networks" with:
      """
      {"name": "Office", "network": "10.0.0.0/8", "outgoingMode": "pool"}
      """
    Then the API answers 422

  Scenario: An admin assigns a policy to a network and takes it off
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    And the admin added "plan" at "/api/policies":
      """
      {"name": "Plan"}
      """
    When the admin sends GET "/api/trusted-networks/${office.id}/policies/available"
    Then the answer lists "plan"
    When the admin sends PUT "/api/trusted-networks/${office.id}/policies/${plan.id}"
    Then the API answers 204
    When the admin sends GET "/api/trusted-networks/${office.id}/policies"
    Then the answer lists "plan"
    When the admin sends PATCH "/api/trusted-networks/${office.id}/policies/${plan.id}" with:
      """
      {"startsOn": "2026-01-15"}
      """
    Then the API answers 204
    When the admin sends DELETE "/api/trusted-networks/${office.id}/policies/${plan.id}"
    Then the API answers 204
    When the admin sends GET "/api/trusted-networks/${office.id}/policies"
    Then the answer doesn't list "plan"

  Scenario: A global policy isn't assigned: it applies anyway
    Given the admin added "office" at "/api/trusted-networks":
      """
      {"name": "Office", "network": "10.0.0.0/8"}
      """
    And the admin added "everyone" at "/api/policies":
      """
      {"name": "Everyone", "isGlobal": true}
      """
    When the admin sends PUT "/api/trusted-networks/${office.id}/policies/${everyone.id}"
    Then the API answers 409
