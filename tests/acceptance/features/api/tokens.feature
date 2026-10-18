Feature: Logging in to the API
  A user logs in with their email and password and gets a pair of tokens: the access token opens the API,
  the refresh token swaps for a new pair. A wrong password, an unknown email and a user turned off all get
  the same refusal: it doesn't tell which.

  Background:
    Given a user

  Scenario: A user logs in with their email and password
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": ${user.password}}
      """
    Then the API answers 200
    And the answer has "access"
    And the answer has "refresh"

  Scenario: The access token opens the API
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": ${user.password}}
      """
    And the answer is kept as "session"
    And the client uses the access token of "session"
    And the user sends GET "/api/users/me"
    Then the API answers 200
    And the answer has:
      """
      {"id": ${user.id}, "email": ${user.email}}
      """

  Scenario: A wrong password is refused
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": "not the password"}
      """
    Then the API answers 401

  Scenario: An unknown email is refused
    When the user sends POST "/api/tokens" with:
      """
      {"email": "nobody@example.com", "password": ${user.password}}
      """
    Then the API answers 401

  Scenario: A user turned off can't log in
    Given the user is turned off
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": ${user.password}}
      """
    Then the API answers 401

  Scenario: A malformed email is refused before checking anything
    When the user sends POST "/api/tokens" with:
      """
      {"email": "not an email", "password": ${user.password}}
      """
    Then the API answers 422

  Scenario: The refresh token swaps for a new pair
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": ${user.password}}
      """
    And the answer is kept as "session"
    And the user sends POST "/api/tokens/refresh" with:
      """
      {"refresh": ${session.refresh}}
      """
    Then the API answers 200
    And the answer has "access"
    And the answer has "refresh"

  Scenario: The access token doesn't swap for a new pair
    When the user sends POST "/api/tokens" with:
      """
      {"email": ${user.email}, "password": ${user.password}}
      """
    And the answer is kept as "session"
    And the user sends POST "/api/tokens/refresh" with:
      """
      {"refresh": ${session.access}}
      """
    Then the API answers 401
