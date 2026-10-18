Feature: Users and groups in the API
  An admin creates users of the admin, gives them permissions directly or through groups, turns them off
  and sets their passwords: a new password ends the user's sessions. An admin can't lock themselves out,
  and changes their own password only knowing the old one.

  Background:
    Given an admin logged in to the API

  Scenario: An admin creates a user
    When the admin sends POST "/api/users" with:
      """
      {
        "email": "ann@example.com",
        "name": "Ann",
        "surname": "Lee",
        "password": "correct horse battery",
        "permissions": ["trusted_networks.view"]
      }
      """
    Then the API answers 201
    And the answer has:
      """
      {
        "email": "ann@example.com",
        "isActive": true,
        "isSuperuser": false,
        "groupIds": [],
        "permissions": ["trusted_networks.view"]
      }
      """
    And the answer has no "password"

  Scenario: An email is taken once
    Given the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends POST "/api/users" with:
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Other", "password": "correct horse battery"}
      """
    Then the API answers 409

  Scenario: A short password is refused
    When the admin sends POST "/api/users" with:
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "short"}
      """
    Then the API answers 422

  Scenario: An admin lists users
    Given the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends GET "/api/users"
    Then the API answers 200
    And the answer lists "ann"
    And the answer lists "admin"

  Scenario: An admin turns a user off
    Given the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends PATCH "/api/users/${ann.id}" with:
      """
      {"isActive": false}
      """
    Then the API answers 200
    And the answer has:
      """
      {"isActive": false}
      """

  Scenario: An admin can't turn themselves off
    When the admin sends PATCH "/api/users/${admin.id}" with:
      """
      {"isActive": false}
      """
    Then the API answers 409

  Scenario: A new password ends the user's sessions
    Given the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends POST "/api/tokens" with:
      """
      {"email": "ann@example.com", "password": "correct horse battery"}
      """
    And the answer is kept as "session"
    And the admin sends PUT "/api/users/${ann.id}/password" with:
      """
      {"password": "battery staple horse"}
      """
    Then the API answers 204
    When the client uses the access token of "session"
    And the user sends GET "/api/users/me"
    Then the API answers 401

  Scenario: An admin renames themselves
    When the admin sends PATCH "/api/users/me" with:
      """
      {"name": "Ada"}
      """
    Then the API answers 200
    And the answer has:
      """
      {"id": ${admin.id}, "name": "Ada"}
      """

  Scenario: An own password changes only with the old one
    When the admin sends PUT "/api/users/me/password" with:
      """
      {"oldPassword": "not the password", "newPassword": "battery staple horse"}
      """
    Then the API answers 400

  Scenario: An own password changes with the old one
    When the admin sends PUT "/api/users/me/password" with:
      """
      {"oldPassword": ${admin.password}, "newPassword": "battery staple horse"}
      """
    Then the API answers 200
    And the answer has "access"

  Scenario: An admin creates a group
    When the admin sends POST "/api/groups" with:
      """
      {"name": "Support", "permissions": ["trusted_networks.view", "traffic.view"]}
      """
    Then the API answers 201
    And the answer has:
      """
      {"name": "Support"}
      """

  Scenario: A group of an unknown permission is refused
    When the admin sends POST "/api/groups" with:
      """
      {"name": "Support", "permissions": ["moon.landing"]}
      """
    Then the API answers 422

  Scenario: A group name is taken once
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support"}
      """
    When the admin sends POST "/api/groups" with:
      """
      {"name": "Support"}
      """
    Then the API answers 409

  Scenario: A user gets the permissions of a group they're put in
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support", "permissions": ["trusted_networks.view"]}
      """
    And the admin added "ann" at "/api/users":
      """
      {
        "email": "ann@example.com",
        "name": "Ann",
        "surname": "Lee",
        "password": "correct horse battery",
        "groupIds": [${support.id}]
      }
      """
    When the admin sends POST "/api/tokens" with:
      """
      {"email": "ann@example.com", "password": "correct horse battery"}
      """
    And the answer is kept as "session"
    And the client uses the access token of "session"
    And the user sends GET "/api/trusted-networks"
    Then the API answers 200

  Scenario: An admin renames a group and changes its permissions
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support", "permissions": ["trusted_networks.view"]}
      """
    When the admin sends PATCH "/api/groups/${support.id}" with:
      """
      {"name": "Network team", "permissions": ["trusted_networks.change"]}
      """
    Then the API answers 200
    And the answer has:
      """
      {"name": "Network team", "permissions": ["trusted_networks.change"]}
      """

  Scenario: A group can't take the name of another one
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support"}
      """
    And the admin added "sales" at "/api/groups":
      """
      {"name": "Sales"}
      """
    When the admin sends PATCH "/api/groups/${sales.id}" with:
      """
      {"name": "Support"}
      """
    Then the API answers 409

  Scenario: An admin lists groups
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support"}
      """
    When the admin sends GET "/api/groups"
    Then the API answers 200
    And the answer lists "support"

  Scenario: An admin puts a user in a group and gives them a permission
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support"}
      """
    And the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends PATCH "/api/users/${ann.id}" with:
      """
      {"email": "ann.lee@example.com", "surname": "Smith", "groupIds": [${support.id}], "permissions": ["traffic.view"]}
      """
    Then the API answers 200
    And the answer has:
      """
      {
        "email": "ann.lee@example.com",
        "surname": "Smith",
        "groupIds": [${support.id}],
        "permissions": ["traffic.view"]
      }
      """
    When the admin sends GET "/api/users/${ann.id}"
    Then the answer has:
      """
      {"groupIds": [${support.id}], "permissions": ["traffic.view"]}
      """

  Scenario: An email can't be taken from another user
    Given the admin added "ann" at "/api/users":
      """
      {"email": "ann@example.com", "name": "Ann", "surname": "Lee", "password": "correct horse battery"}
      """
    When the admin sends PATCH "/api/users/${ann.id}" with:
      """
      {"email": ${admin.email}}
      """
    Then the API answers 409

  Scenario: An admin can't stop being a superuser themselves
    When the admin sends PATCH "/api/users/${admin.id}" with:
      """
      {"isSuperuser": false}
      """
    Then the API answers 409

  Scenario: An admin deletes a group
    Given the admin added "support" at "/api/groups":
      """
      {"name": "Support"}
      """
    When the admin sends DELETE "/api/groups/${support.id}"
    Then the API answers 204
    When the admin sends GET "/api/groups/${support.id}"
    Then the API answers 404
