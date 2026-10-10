# Roadmap

Where Proxium is heading. No dates, priorities may change. Ideas and use cases are welcome in
[issues](https://github.com/koldakov/proxium/issues).

## Planned

**Scaling**

- Redis: several proxy instances share the cache, connection and speed limits
- The admin UI warns about outgoing IPs that no proxy instance has

**Access control**

- Allow and deny target domains per account and network, e.g. "this agent reaches only these sites"
- API for merchants: manage accounts, policies and traffic from your own systems, without the admin UI
- External authentication: an HTTP hook in nginx `auth_request` style, then JWTs from your identity provider
- SSO for the admin UI over OIDC

**Policies**

- Edited policies apply to open connections at once, not only to new ones
- More conditions: expressions (CEL), proxy load, traffic used, flags
- Current usage against quotas in the admin UI
- Throttling as a rule action, connection rate limits, fair share of bandwidth between clients

**Outgoing IPs**

- Sticky sessions: one outgoing IP for a session ID passed in the username
- Outgoing IP mode per listening port
- Outgoing IP in the connection log

**TLS**

- Certificate per host name (SNI) or per listener
- HTTP/2 to the proxy

**Operations**

- Metrics
- Documentation site
- Upgrades of the bundled PostgreSQL to a new major version

## Exploring

- SOCKS5 UDP
- Upstream proxies and rotation
- HTTP/3 to the proxy
- Billing
