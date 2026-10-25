Feature: Outgoing IPs
  The proxy connects to targets from the IP its account or trusted network says: the one the OS picks,
  the one the client came in through, or one of its pool. A pool IP that isn't on this host fails
  the connection rather than going out from another IP.

  The proxy and the website run on loopback: the main address is 127.0.0.1, the second one 127.0.0.2.
  Only Linux has the second one, scenarios that need it are skipped elsewhere.

  Background:
    Given a website

  Scenario: The OS picks the outgoing IP by default
    Given a proxy account
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    And the website sees the proxy come from the main address

  Scenario Outline: An account goes out from its pool over <protocol>
    Given a proxy account
    And the account goes out from a pool of the second address
    And the proxy is running
    When the client requests the website over <protocol> with the account credentials
    Then the client gets the website
    And the website sees the proxy come from the second address

    Examples:
      | protocol |
      | HTTP     |
      | SOCKS5   |

  Scenario: An account goes out from the address the client came in through
    Given a proxy account
    And the account goes out from the address the client came in through
    And the proxy listens on the second address
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
    And the website sees the proxy come from the second address

  Scenario: A pool IP that isn't on this host fails the connection
    Given a proxy account
    And the account goes out from a pool of an address not on this host
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the proxy reports its own setup at fault

  Scenario: A trusted network goes out from its pool
    Given the client's network is trusted
    And the network goes out from a pool of the second address
    And the proxy is running
    When the client requests the website over HTTP without credentials
    Then the client gets the website
    And the website sees the proxy come from the second address
