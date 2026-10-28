Feature: Proxy instances in the API
  Every proxy reports itself to the database, the admin sees which ones run. One that missed its reports is
  unknown by the database's clock. An admin deregisters stopped and unknown ones, e.g. a removed server.

  Background:
    Given an admin logged in to the API
    And a pending proxy instance "pending"
    And a running proxy instance "running"
    And a stopped proxy instance "stopped"
    And an unknown proxy instance "unknown"

  Scenario: The admin lists the instances, newest first
    When the admin sends GET "/api/proxy-instances"
    Then the API answers 200
    And the answer has:
      """
      {
        "items": [
          {"id": ${unknown.id}, "status": "unknown"},
          {"id": ${stopped.id}, "status": "stopped"},
          {"id": ${running.id}, "status": "running"},
          {"id": ${pending.id}, "status": "pending"}
        ],
        "total": 4
      }
      """

  Scenario Outline: The admin lists <status> instances
    When the admin sends GET "/api/proxy-instances?status=<status>"
    Then the API answers 200
    And the answer has:
      """
      {"items": [{"id": ${<status>.id}, "status": "<status>"}]}
      """

    Examples:
      | status  |
      | pending |
      | running |
      | stopped |
      | unknown |

  Scenario: An unknown status filter is refused
    When the admin sends GET "/api/proxy-instances?status=dead"
    Then the API answers 422

  Scenario: The admin counts the instances by status
    When the admin sends GET "/api/proxy-instances/counts"
    Then the API answers 200
    And the answer has:
      """
      {"pending": 1, "running": 1, "stopped": 1, "unknown": 1}
      """

  Scenario Outline: The admin deregisters a <status> instance
    When the admin sends POST "/api/proxy-instances/${<status>.id}/deregister"
    Then the API answers 204
    When the admin sends GET "/api/proxy-instances"
    Then the answer doesn't list "<status>"

    Examples:
      | status  |
      | stopped |
      | unknown |

  Scenario: Deregistered instances aren't counted
    Given the admin sent POST "/api/proxy-instances/${stopped.id}/deregister"
    When the admin sends GET "/api/proxy-instances/counts"
    Then the answer has:
      """
      {"pending": 1, "running": 1, "stopped": 0, "unknown": 1}
      """

  Scenario Outline: A <status> instance can't be deregistered
    When the admin sends POST "/api/proxy-instances/${<status>.id}/deregister"
    Then the API answers 409

    Examples:
      | status  |
      | pending |
      | running |

  Scenario: A deregistered instance can't be deregistered again
    Given the admin sent POST "/api/proxy-instances/${stopped.id}/deregister"
    When the admin sends POST "/api/proxy-instances/${stopped.id}/deregister"
    Then the API answers 404

  Scenario: A missing instance can't be deregistered
    When the admin sends POST "/api/proxy-instances/0/deregister"
    Then the API answers 404

  Scenario: A permission to view doesn't let deregister
    Given a user with "proxy_instances.view" logged in to the API
    When the user sends POST "/api/proxy-instances/${stopped.id}/deregister"
    Then the API answers 403

  Scenario: A user with the permission to deregister deregisters
    Given a user with "proxy_instances.deregister" logged in to the API
    When the user sends POST "/api/proxy-instances/${stopped.id}/deregister"
    Then the API answers 204
