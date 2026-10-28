# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

A new look for the admin UI: easier on the eyes, clearer to read, errors right where they happen.

### Added

- The Proxy instances page shows every running proxy and its health at a glance: running, pending, stopped or
  unknown, with host, version, uptime and when it last reported. Proxies report themselves, nothing to set up, a
  crashed or hung one turns unknown within a minute and a half. Removed servers are deregistered with one click.
  `PROXY_HEARTBEAT_INTERVAL` sets how often proxies report, `30` seconds by default.
- The admin UI asks before leaving a form with unsaved changes, on reloading or closing the tab too.
- Rules of a policy move up and down: the first matching rule applies, order is in your hands.
- `API_GLOBAL_POLICIES_MAX`: at most this many global policies, `32` by default, turned off ones too. Each global
  policy is checked on every connection, many rules for everyone fit in one. Global policies past it, e.g. after
  lowering it, keep working and can be edited, only making one more global is refused. The admin UI says so at
  the Global switch.

### Changed

- The admin UI has its own light and dark themes, the light one without glaring white. The Inter font comes with
  it, so it looks the same without internet access.
- Policy rules are cards with a summary of when each one applies and what it limits, e.g. "Mon–Fri 09:00–18:00 and
  unless domain github.com: 1 Mbit/s each way per account". A card collapses to its summary, as on the read-only
  page. Conditions start with "If" or "Unless", days are picked from a list with weekdays and weekends at the top.
- Date and time inputs are one picker in every browser, Safari included, in the browser's 12 or 24 hour clock. A
  half-typed date is an error instead of an empty value, e.g. an account that never expires.
- Lists show statuses as chips: an account is Active, Expired or Revoked at a glance. Usernames, keys, networks and
  IPs are monospace.
- Errors show where they happen: a failed save above the form's buttons, a failed action inside its dialog, which
  stays open. Toasts only confirm what's done, at the top of the page.
- The login page has the admin's look. A wrong email or password is said under the inputs, an ended session in the
  page, not in toasts that go away.
- Groups and own permissions of a superuser are locked in the user form: a superuser has every permission. They
  apply again once Superuser is turned off.

### Fixed

- The traffic of an account or network keeps its height when switching the period or between chart and table: the
  page below doesn't jump.

## [0.2.0] - 2026-10-25

Every limit is shared between proxy instances: run several on one database, and they work as one proxy. See
[Upgrading](docs/upgrading.md#from-01-to-02).

### Added

- Redis, `REDIS_URL`, `REDIS_PASSWORD`, `REDIS_KEY_PREFIX` and `REDIS_POOL_MAX_CONNECTIONS`: shared state of the
  instances. The Docker image runs its own without `REDIS_URL`, the compose example runs one next to it.
- `proxium-manage migrate` holds a lock in Redis: instances starting at once migrate one at a time.
- `PROXY_BACKLOG`: the queue of connections waiting to be accepted, `1024` by default instead of a fixed `100`.
  Bursts of new connections no longer stall for seconds.
- Supported versions in the docs: PostgreSQL 17 and 18, Redis 7.4 and 8, each tested in CI.
- Connection limits are shared by the instances through Redis: a limit of 10 is 10 across all of them, during a
  restart without downtime too. `PROXY_CONNECTION_LEASE`: how long a crashed instance's connections keep counting.
  `PROXY_REDIS_OUTAGE_TIMEOUT`: how long each instance counts alone while Redis is down.
- `REDIS_SOCKET_CONNECT_TIMEOUT` and `REDIS_SOCKET_TIMEOUT`: a Redis that hangs fails in seconds instead of never.
- Speed limits are shared by the instances through Redis: 1 MB/s is 1 MB/s across all of them, during a restart
  without downtime too. `PROXY_SPEED_BATCH`: how much of the rate an instance takes at once, each may go over a
  limit by one batch. While Redis is down each instance limits its own connections.
- Traffic quotas are shared by the instances through Redis: each one puts the traffic it hasn't written to the
  database yet there every second, so 10 GB is 10 GB across all of them. While Redis is up, a client may go over a
  quota by about two seconds of its traffic per instance, plus the second between checks of an open connection.
  Before, it was up to a minute.
- `Proxy-Status` (RFC 9209) on every HTTP response, e.g. `proxium; error=http_request_denied` on a 429: a client
  tells a refusal of the proxy from a response of the target with the same status. Forwarded responses get the
  proxy's name added. `PROXY_NAME` sets the name. A 503 over limits that can't be checked also has `Retry-After`.
- A forwarded response whose head breaks off or isn't valid HTTP, e.g. has a line ending with a bare LF or CR,
  folded or malformed fields, a conflicting `Content-Length`, `Transfer-Encoding` on a body in answer to an HTTP/1.0
  request, more than 16 interim `1xx` heads, an unasked `101`, or comes from a TLS server, gets the client a `502`
  with the reason in `Proxy-Status`, `connection_terminated` if the target closed without a byte. A target that sends no head until the idle timeout gets
  the client a `504` with `http_response_timeout`, a client that hasn't sent its whole request by then a `408`, unless
  it waits for `100 Continue`. A request cut before its response, e.g. over a quota, gets the refusal. Before, the
  connection just closed or the bytes went on as is. The proxy reads off what the client still sends for up to 5
  seconds before closing, so the client gets the refusal instead of a reset.
- Forwarded responses say `Connection: close` and lose the target's connection fields, e.g. `Keep-Alive`, as RFC 9110
  and RFC 9112 require: the proxy forwards one request per connection. `Content-Length` next to `Transfer-Encoding`
  is dropped, a repeated one sent once. HTTP/1.0 clients get no interim `1xx` responses.
- HTTP requests whose body end is unclear get `400`, as RFC 9112 requires: `Transfer-Encoding` not ending with
  `chunked`, next to `Content-Length` or in an HTTP/1.0 request, a bad or conflicting `Content-Length`, a malformed
  chunk. Before, they went to the target.
- `TargetNotResolved` error for a target whose name doesn't resolve, `dns_error` in `Proxy-Status`, and
  `ResolveTimeout` for a resolver that doesn't answer in time, `504` with `dns_timeout`.
- `TargetRefused` error for a target that refuses the connection: `connection_refused` in `Proxy-Status`, SOCKS5
  clients get connection refused instead of host unreachable.
- Traffic of an account or network in the admin UI is a chart by day for the last 7, 30 or 90 days, the table is
  one click away.

### Changed

- HTTP clients get `500` instead of `502 Bad Gateway` when there's no outgoing IP to connect from, e.g. an empty IP
  pool, SOCKS5 ones a general failure instead of host unreachable: the proxy's setup is at fault, not the target.
- HTTP clients get `503 Limits Unavailable` instead of `500` when limits can't be checked, e.g. the database or
  Redis is down: worth retrying later.
- Redis is required. Outside the Docker image, set `REDIS_URL` before upgrading.
- An edited speed limit applies to open connections too, a removed one stops slowing them down. Before, they kept
  the old one, and with the new one for new connections a client could get its speed twice. A new scope still
  applies to new connections only: open ones keep the old limit.
- Traffic quotas depend on Redis, a single instance too. If Redis is down longer than `PROXY_REDIS_OUTAGE_TIMEOUT`,
  connections under quotas are refused with 503 and open ones cut until it's back. Before, quotas didn't use Redis.
- Redis 7.4 or newer is required: quotas keep traffic in hash fields that expire. On an older one the proxy doesn't
  start.
- Restarting without downtime from 0.1.1, the old proxy doesn't share its traffic: until it stops, a quota may let
  through what it hasn't written to the database yet, as before.
- `PROXY_CONNECTION_LEASE` must be at least `3 + REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT`, `7` by
  default, or nothing starts: unwritten traffic for quotas is renewed in Redis every second, and three renewals and
  one slow Redis command fit in a lease.

### Fixed

- What an HTTP client sends after a forwarded request, e.g. a pipelined request to another host with its
  `Proxy-Authorization`, doesn't reach the target. Past a request head's size it isn't read until the response ends,
  so a client can't send past its limits meanwhile. Before, it went there as is.
- Deleting an outgoing IP that is in a pool, or a trusted network with traffic, answers 409 instead of 500, on
  PostgreSQL 17 and 18 alike.
- A trusted network with policies can be deleted: its policy assignments go with it, the policies stay.
- The Docker image has no pip: its vendored urllib3, msgpack and setuptools carried known vulnerabilities.

## [0.1.1] - 2026-10-13

### Added

- Restart without downtime: a new proxy listens on the same ports before the old one stops, `PROXY_REUSE_PORT`
  turns it off. Works for upgrades from 0.1.1 on: a 0.1.0 proxy doesn't share its ports.

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

[Unreleased]: https://github.com/koldakov/proxium/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/koldakov/proxium/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/koldakov/proxium/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/koldakov/proxium/releases/tag/v0.1.0
