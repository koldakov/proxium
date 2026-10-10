# Proxium

[![Test](https://github.com/koldakov/proxium/actions/workflows/test.yml/badge.svg)](https://github.com/koldakov/proxium/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE.md)
[![Docker](https://img.shields.io/badge/docker-ikoldakov%2Fproxium-2496ED?logo=docker&logoColor=white)](https://hub.docker.com/r/ikoldakov/proxium)

**Your own proxy service in one `docker run`.**

HTTP and SOCKS5 proxy with accounts, quotas, speed limits, outgoing IP pools and a web admin panel. Self-hosted.
Open source. No config files.

![Policy rule: 1 Mbit/s in working hours, except work sites](docs/images/policy-rules.png)

<sub>A policy rule: 1 Mbit/s in working hours, except GitHub and Atlassian. Applies in seconds, no restart.</sub>

## Built for

- **AI agents.** Give each agent its own token, cap its connections, speed and traffic, see what it used per day.
  An agent browsing the web can't reach your internal network or cloud metadata, even if a prompt injection tells
  it to.
- **Company gateways.** The office network connects without passwords, everyone else with an account. Throttle
  everything but work sites in working hours. Internal networks and cloud metadata stay unreachable.
- **Selling proxies.** Accounts with expiry, monthly traffic quotas counted from the day the client paid, speed
  tiers, dedicated IPs, traffic per day. Revoke a client in one click.
- **Scraping and automation.** Listen on many IPs and port ranges at once, go out from a random IP of a pool on
  every connection, cap connections per target host.
- **A personal proxy.** A TLS-encrypted proxy on your VPS with an HTTPS admin panel, set up in minutes.

## Try it in 30 seconds

```bash
docker run -d --name proxium -p 80:80 -p 8080:8080 -v proxium:/var/lib/proxium \
  -e SUPERUSER_CREATE=true -e SUPERUSER_EMAIL=admin@example.com -e SUPERUSER_PASSWORD=change-me \
  ikoldakov/proxium
```

1. Open the admin UI at http://localhost and log in.
2. Add an account under Proxy accounts → Basic, copy its password: it's shown once.
3. Use it:

```bash
curl -x http://username:password@localhost:8080 https://ifconfig.me
curl -x socks5h://username:password@localhost:8080 https://ifconfig.me
```

One image runs the proxy, the API, the admin UI and PostgreSQL, for amd64 and arm64. Own certificates, own
database, separate containers and running from source: see [Installation](docs/installation.md).

## Admin panel

Everything is managed in the browser: accounts, networks, policies, certificates, admins.

| An account: outgoing IP, policies, daily traffic | A read-only group: permissions per section and action |
|---|---|
| ![Proxy account page](docs/images/account-page.png) | ![Group permissions](docs/images/group-permissions.png) |

## Own domains and HTTPS

The admin UI and the proxy each get their own domain and certificate, e.g. `admin.example.com` and
`proxy.example.com`, on one server or on different ones. Recreate the container, the volume keeps the data:

```bash
docker rm -f proxium
docker run -d --name proxium -p 80:80 -p 443:443 -p 8080:8080 -v proxium:/var/lib/proxium \
  -e ADMIN_HOST=admin.example.com -e ADMIN_TLS=auto \
  ikoldakov/proxium
```

Point both domains to the server with DNS A or AAAA records. The admin UI gets a Let's Encrypt certificate on
start. Add a certificate for `proxy.example.com` in the admin UI under TLS certificates, then clients connect
over TLS:

```bash
curl -x https://username:password@proxy.example.com:8080 https://ifconfig.me
```

## Why Proxium?

Squid, Dante and 3proxy are solid engines, but users, ACLs and limits live in their config files: every change is
an edit and a reload, every admin needs shell access. Proxium keeps all of it in a database behind an admin panel
and an API:

- **Change anything live.** Accounts, networks, policies and certificates reach the proxy within seconds, open
  connections keep working.
- **Give access, not root.** Admins get per-section permissions through groups: a support engineer revokes
  accounts, an accountant sees traffic, neither touches TLS.
- **One port for everything.** HTTP, SOCKS5 and TLS on the same port, detected automatically.

## Features

**Proxy**

- HTTP (CONNECT tunnels and plain forwarding) and SOCKS5 on the same port, detected by the first byte
- TLS to the proxy on the same ports, credentials never travel in the clear
- Listen on many IPs and port ranges at once, e.g. `10.0.0.0/29:10000-10999`
- Graceful shutdown: open connections get time to finish

**Identity and access**

- Basic (username/password) and bearer token accounts, with expiry and revocation
- Trusted networks: clients from your networks connect without credentials, nested networks supported
- Outbound ACL: loopback, private networks and cloud metadata are blocked unless you allow them

**Policies**

- Connection limits, speed limits per direction, traffic quotas per day, month or in total
- Counted per connection, account, client IP, target host or the whole proxy
- Rules with conditions: time of day and week, target domain, IP and port, protocol, client IP, TLS
- Global policies for everyone, assigned ones for chosen accounts and networks

**Outgoing IPs**

- `system`, `listener` or `pool` mode per account and trusted network
- A pool of one IP is a dedicated IP

**Administration**

- Web admin UI and a REST API
- Users, groups and per-action permissions, no privilege escalation
- TLS certificates: upload, generate self-signed, import from certbot, encryption key rotation
- Traffic per account and network

## How it works

```
                 ┌──────────────────────────────┐
  Clients ──────→│           Proxium            │──────→ Internet
  HTTP           │                              │        from the outgoing IP
  SOCKS5         │  Authentication              │        you pick
  over TLS       │  Network ACL                 │
                 │  Policies and quotas         │
                 │  Outgoing IP selection       │
                 │  Traffic accounting          │
                 └──────┬───────────────┬───────┘
                        │               │ polls settings and policies,
                 ┌──────┴──────┐        │ writes traffic
                 │    Cache    │        │
                 └──────┬──────┘        │
                        │ on a miss     │
                 ┌──────┴───────────────┴───────┐
  Admins ───────→│  Admin UI → API → PostgreSQL │
                 └──────────────────────────────┘
```

### Components

| | What it does | Runs as |
|---|---|---|
| **Proxy** | Accepts clients, authenticates, applies policies, forwards traffic, counts it | `proxium` |
| **Cache** | Keeps account, network and TLS certificate lookups for a TTL, connections skip the database | pluggable, in the proxy's memory now |
| **API** | REST API over the database for the admin UI and your scripts | `proxium-api` |
| **Admin UI** | Web interface for admins, talks only to the API | static files behind Caddy |
| **PostgreSQL** | Single source of truth: accounts, policies, certificates, traffic | bundled or your own |

Connections don't query the database each time: authentication and the TLS certificate come from the cache,
settings and policies from memory refreshed every few seconds, traffic is written in batches about once a minute.

The proxy never takes commands from the API: it reads the database on its own, so the API and the admin UI can run
on another host or be stopped without touching client traffic.

## Security model

- **No anonymous access.** Every client authenticates or comes from a trusted network you added. There are none by
  default.
- **Secrets are hashed.** Passwords and tokens are stored as salted PBKDF2-SHA256 hashes.
- **Private keys are encrypted.** TLS keys are protected with field-level encryption, the API never returns them,
  the encryption key rotates without downtime.
- **No SSRF by default.** The proxy reaches only the public internet: loopback, private networks and
  `169.254.169.254` are blocked unless allowed in the settings.
- **Least privilege for admins.** A user grants only the permissions they have, only superusers manage superusers,
  a new password logs the user out everywhere.

### Threat model

Proxium protects your proxy from unauthorized use and your network from being reached through it. It doesn't:

- **Inspect traffic.** HTTPS goes through as an end-to-end tunnel, the proxy sees only the target host and port.
- **Hide credentials without TLS.** Plain HTTP and SOCKS5 send passwords and tokens in the clear: enable TLS for clients outside
  your network.
- **Revoke instantly.** A revoked account keeps connecting for the cache TTL, 10 seconds by default, configurable.
- **Vouch for trusted networks.** Anyone inside one gets in, add only networks you control.

Report vulnerabilities privately, see [SECURITY.md](SECURITY.md).

## Documentation

- [Installation](docs/installation.md): Docker, HTTPS for the admin UI, ports and IPs, compose, from source
- [Configuration](docs/configuration.md): environment variables
- [Proxy](docs/proxy.md): protocols, TLS, trusted networks, outgoing IPs, policies, settings
- [Admin UI](docs/admin.md): users, groups and permissions
- [Management commands](docs/management.md): superusers, migrations, certificates, key rotation
- [Changelog](CHANGELOG.md) and [Roadmap](ROADMAP.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE.md)
