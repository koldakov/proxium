Feature: Trusted networks
  Clients of a trusted network use the proxy without credentials, over HTTP and SOCKS5 on the same port.
  Clients from anywhere else, or of a network turned off, need credentials as before. Credentials sent
  from a trusted network are checked all the same: a wrong password isn't let through.

  Background:
    Given a website

  Scenario Outline: A client of a trusted network reaches the website over <protocol> without credentials
    Given the client's network is trusted
    And the proxy is running
    When the client requests the website over <protocol> without credentials
    Then the client gets the website

    Examples:
      | protocol |
      | HTTP     |
      | SOCKS5   |

  Scenario: The HTTP proxy asks a client outside the trusted networks for credentials
    Given another network is trusted
    And the proxy is running
    When the client requests the website over HTTP without credentials
    Then the proxy asks for credentials

  Scenario: The SOCKS5 proxy refuses a client outside the trusted networks
    Given another network is trusted
    And the proxy is running
    When the client requests the website over SOCKS5 without credentials
    Then the proxy refuses the connection

  Scenario: A network turned off trusts no one
    Given the client's network is trusted but turned off
    And the proxy is running
    When the client requests the website over HTTP without credentials
    Then the proxy asks for credentials

  Scenario: An account works from a trusted network
    Given the client's network is trusted
    And a proxy account
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website

  Scenario: A trusted network doesn't let a wrong password through
    Given the client's network is trusted
    And a proxy account
    And the proxy is running
    When the client requests the website over HTTP with a wrong password
    Then the proxy asks for credentials
