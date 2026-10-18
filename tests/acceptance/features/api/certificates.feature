Feature: Certificates in the API
  An admin uploads a certificate with its key, or has a self-signed one made, and activates it: TLS clients
  of the proxy get the active one. One at most is active, activating another turns it off. The active
  certificate can't be deleted, deactivate it first.

  Background:
    Given an admin logged in to the API

  Scenario: An admin has a self-signed certificate made
    When the admin sends POST "/api/certificates" with:
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30}
      """
    Then the API answers 201
    And the answer has:
      """
      {"names": ["proxy.example.com"], "isSelfSigned": true, "isActive": false}
      """

  Scenario: An admin uploads a certificate
    Given a self-signed certificate "own" for "proxy.example.com"
    When the admin sends POST "/api/certificates" with:
      """
      {"source": "upload", "certificate": ${own.certificate}, "privateKey": ${own.privateKey}}
      """
    Then the API answers 201
    And the answer has:
      """
      {"names": ["proxy.example.com"], "isActive": false}
      """
    And the answer has no "privateKey"

  Scenario: A certificate can't be uploaded twice
    Given a self-signed certificate "own" for "proxy.example.com"
    And the admin added "first" at "/api/certificates":
      """
      {"source": "upload", "certificate": ${own.certificate}, "privateKey": ${own.privateKey}}
      """
    When the admin sends POST "/api/certificates" with:
      """
      {"source": "upload", "certificate": ${own.certificate}, "privateKey": ${own.privateKey}}
      """
    Then the API answers 409

  Scenario: A certificate that isn't PEM is refused
    When the admin sends POST "/api/certificates" with:
      """
      {"source": "upload", "certificate": "not a certificate", "privateKey": "not a key"}
      """
    Then the API answers 422

  Scenario: Activating a certificate turns the active one off
    Given the admin added "old" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30, "activate": true}
      """
    And the admin added "new" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30}
      """
    When the admin sends POST "/api/certificates/${new.id}/activate" with:
      """
      {"replaces": ${old.id}}
      """
    Then the API answers 204
    When the admin sends GET "/api/certificates?isActive=true"
    Then the answer lists "new"
    And the answer doesn't list "old"

  Scenario: Activating over a certificate the admin didn't see is refused
    Given the admin added "old" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30, "activate": true}
      """
    And the admin added "new" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30}
      """
    When the admin sends POST "/api/certificates/${new.id}/activate" with:
      """
      {"replaces": null}
      """
    Then the API answers 409

  Scenario: The active certificate can't be deleted
    Given the admin added "tls" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30, "activate": true}
      """
    When the admin sends DELETE "/api/certificates/${tls.id}"
    Then the API answers 409

  Scenario: A deactivated certificate can be deleted
    Given the admin added "tls" at "/api/certificates":
      """
      {"source": "generate", "names": ["proxy.example.com"], "days": 30, "activate": true}
      """
    And the admin sent POST "/api/certificates/${tls.id}/deactivate"
    When the admin sends DELETE "/api/certificates/${tls.id}"
    Then the API answers 204

  Scenario: TLS clients get the certificate activated in the API
    Given a website
    And a proxy account
    And the admin added "tls" at "/api/certificates":
      """
      {"source": "generate", "names": ["127.0.0.1"], "days": 1, "activate": true}
      """
    And the client trusts the certificate "tls"
    And the proxy is running
    When the client requests the website over HTTPS with the account credentials
    Then the client gets the website
