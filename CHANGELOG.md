# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-10-10

Your own proxy service in one `docker run`: accounts, policies, outgoing IPs and an admin panel, no config files.

### Added

#### Proxy

- HTTP (CONNECT tunnels and plain forwarding) and SOCKS5 (CONNECT to IPv4, IPv6 and domain targets) on the same
  port, detected by the first byte.
- TLS to the proxy on the same ports, with HTTP or SOCKS5 inside. One active certificate serves all ports and is
  switched without a restart.
- Listening on many IPs and port ranges at once, e.g. `10.0.0.0/29:10000-10999`.
- Outbound ACL: loopback, private networks and cloud metadata are blocked unless allowed in the settings.
- Handshake, idle and connect timeouts.
- Graceful shutdown: open connections get `PROXY_GRACEFUL_TIMEOUT` to finish, a second signal stops at once.

#### Identity and access

- Basic (username/password) and bearer token accounts with expiry and revocation. Secrets are stored as salted
  PBKDF2-SHA256 hashes and shown once on creation.
- Trusted networks: clients from them connect without credentials. Networks may nest, the narrowest one names
  the client.
- Cached checks: accounts, networks and the TLS certificate are looked up once per TTL set in the settings,
  separately for passed and refused checks. If the database is down, clients without a cached check are refused.

#### Outgoing IPs

- `system`, `listener` or `pool` mode per account and trusted network. A pool picks a random IP for every
  connection, a pool of one IP is a dedicated IP.

#### Policies

- Connection limits, speed limits per direction with a burst, traffic quotas per N days, N months or in total.
- Limits counted per connection, account or network, client IP, target host or the whole proxy.
- Rules with conditions: time of day and week, target domain, IP and port, protocol, client IP, TLS. Conditions
  combine with all or any and can be negated, the first matching rule of a policy applies.
- Global policies for everyone and assigned ones for chosen accounts and trusted networks, with quota periods
  from a chosen day, e.g. the day the client paid. All policies apply at once, the strictest wins.
- Past a connection limit or quota new connections are refused, HTTP clients get `429`. Past a quota open
  tunnels are cut, and open tunnels switch rules when conditions change.

#### Traffic

- Traffic per account and trusted network per day.

#### Administration

- Web admin UI and a REST API. Accounts, networks, policies, settings and certificates reach the proxy within
  seconds, without a restart.
- Admin users, groups and per-action permissions. A user grants only what they have, only superusers manage
  superusers, a new password logs the user out everywhere.
- TLS certificates: upload, generate self-signed, download, activate. Private keys are protected with field-level
  encryption and never returned by the API.
- Settings page: allowed networks, timeouts, cache TTLs.
- Management commands: `createsuperuser`, `changepassword`, `migrate`, `importcert` (e.g. as a certbot deploy
  hook) and `rotateencryptionkey` (encryption key rotation without downtime).

#### Deployment

- All-in-one Docker image `ikoldakov/proxium`, mirrored to `ghcr.io/koldakov/proxium`, for amd64 and arm64: the
  proxy, the API, the admin UI behind Caddy and PostgreSQL. Secrets are generated into the volume unless passed.
- `PROXIUM_SERVICES` picks the services to run, `DATABASE_URL` points to your own database, a compose example runs
  the same image as separate containers.
- Admin UI over HTTP or HTTPS with `ADMIN_TLS`: Let's Encrypt, own certificate files or an internal CA.
- Optional superuser on first start with `SUPERUSER_CREATE`.

[Unreleased]: https://github.com/koldakov/proxium/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/koldakov/proxium/releases/tag/v0.1.0
