Feature: Proxy account authentication
  A proxy account lets a client through the proxy with its username and password,
  over HTTP and SOCKS5 on the same port. Without them, or with a wrong password, the client is refused.

  Background:
    Given a website
    And a proxy account
    And the proxy is running

  Scenario Outline: The account reaches the website over <protocol>
    When the client requests the website over <protocol> with the account credentials
    Then the client gets the website

    Examples:
      | protocol |
      | HTTP     |
      | SOCKS5   |

  Scenario: The HTTP proxy asks for credentials when the password is wrong
    When the client requests the website over HTTP with a wrong password
    Then the proxy asks for credentials

  Scenario: The HTTP proxy asks for credentials when there are none
    When the client requests the website over HTTP without credentials
    Then the proxy asks for credentials

  Scenario: The SOCKS5 proxy refuses a wrong password
    When the client requests the website over SOCKS5 with a wrong password
    Then the proxy refuses the connection
