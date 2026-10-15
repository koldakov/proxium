Feature: Migrations with a lock
  Several instances starting at once migrate one at a time: `migrate` takes a lock in Redis,
  the others wait for it.

  Background:
    Given the database is migrated

  Scenario: An instance waits for another one to migrate
    Given another instance holds the migration lock
    When an instance migrates
    Then the migration waits
    When the other instance releases the migration lock
    Then the migration finishes

  Scenario: The lock is released after migrating
    When an instance migrates
    Then the migration finishes
    And the migration lock is free
