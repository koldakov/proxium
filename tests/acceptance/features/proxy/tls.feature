Feature: TLS
  With an active certificate the proxy speaks TLS on the same port as in the clear: a client that starts
  with a TLS handshake gets the certificate, the others are served as before. Without an active one,
  TLS clients get a handshake failure.

  HTTPS here is the HTTP proxy wrapped in TLS, the client trusts the proxy's certificate alone.
  The website itself is plain HTTP.

  Background:
    Given a website
    And a proxy account

  Scenario: A client reaches the website over TLS
    Given an active certificate
    And the proxy is running
    When the client requests the website over HTTPS with the account credentials
    Then the client gets the website

  Scenario Outline: Clear-text clients over <protocol> are served next to TLS ones
    Given an active certificate
    And the proxy is running
    When the client requests the website over <protocol> with the account credentials
    Then the client gets the website

    Examples:
      | protocol |
      | HTTP     |
      | SOCKS5   |

  Scenario: TLS is refused without a certificate
    Given no certificate
    And the proxy is running
    When the client requests the website over HTTPS with the account credentials
    Then the TLS handshake fails

  Scenario: A certificate that isn't active isn't presented
    Given a certificate that isn't active
    And the proxy is running
    When the client requests the website over HTTPS with the account credentials
    Then the TLS handshake fails

  Scenario: Clear-text clients are served without a certificate
    Given no certificate
    And the proxy is running
    When the client requests the website over HTTP with the account credentials
    Then the client gets the website
