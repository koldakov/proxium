Feature: Policies, limits and quotas
  A policy limits how clients use the proxy: how many connections they keep open, how fast and how much
  they move. It applies to the accounts and trusted networks it's assigned to, a global one to every
  client. A policy turned off limits no one, a rule limits only while its condition matches.

  Every policy here has one rule, counted per account or network.

  Scenario: A connection limit refuses connections over it
    Given a website
    And a proxy account
    And the account has a policy with a connection limit of 1
    And the proxy is running
    And the client holds a tunnel to the website with the account credentials
    When the client requests the website over HTTP with the account credentials
    Then the proxy refuses with too many connections

  Scenario: The SOCKS5 proxy refuses connections over the limit
    Given a website
    And a proxy account
    And the account has a policy with a connection limit of 1
    And the proxy is running
    And the client holds a tunnel to the website with the account credentials
    When the client requests the website over SOCKS5 with the account credentials
    Then the proxy refuses the connection

  Scenario: A connection limit lets connections up to it through
    Given a website
    And a proxy account
    And the account has a policy with a connection limit of 2
    And the proxy is running
    And the client holds a tunnel to the website with the account credentials
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website

  Scenario: A traffic quota refuses the client once used up
    Given a website
    And a proxy account
    And the account has a policy with a traffic quota of 1 byte
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    When the client requests the website over HTTP with the account credentials
    Then the proxy refuses with the quota exceeded

  Scenario: A speed limit slows the download down
    Given a website of 3072 bytes
    And a proxy account
    And the account has a policy with a speed limit of 1024 bytes per second
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    And the download takes at least 2 seconds

  Scenario: A global policy limits every client
    Given a website
    And a proxy account
    And a global policy with a traffic quota of 1 byte
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    When the client requests the website over HTTP with the account credentials
    Then the proxy refuses with the quota exceeded

  Scenario: A policy turned off limits no one
    Given a website
    And a proxy account
    And the account has a policy with a traffic quota of 1 byte
    And the policy is turned off
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website

  Scenario: A rule limits only while its condition matches
    Given a website
    And a proxy account
    And the account has a policy with a traffic quota of 1 byte
    And the policy applies over SOCKS5 only
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    When the client requests the website over SOCKS5 with the account credentials
    Then the proxy refuses the connection

  Scenario: A trusted network gets the limits of its policy
    Given a website
    And the client's network is trusted
    And the network has a policy with a traffic quota of 1 byte
    And the proxy is running
    When the client requests the website over HTTP without credentials
    Then the client gets the website
    When the client requests the website over HTTP without credentials
    Then the proxy refuses with the quota exceeded
