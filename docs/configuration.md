# Configuration

Settings are read from environment variables. Copy the template and fill it in:

```bash
cp .env.template .env
```

## Common

Read by the proxy, the API and the management commands.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgres://user:password@host/db_name` |
| `ENCRYPTION_KEY` | Fernet key that encrypts private keys of TLS certificates in the database, see [TLS](proxy.md#tls) |
| `ENCRYPTION_OLD_KEYS` | Comma-separated previous keys, they still decrypt during [key rotation](proxy.md#tls) |
| `DATABASE_ECHO` | Log every SQL query, default `false`. Parameters are always hidden |
| `DATABASE_POOL_SIZE` | Connections each process keeps open, default `5` |
| `DATABASE_POOL_MAX_OVERFLOW` | Extra connections under load, default `10` |
| `DATABASE_POOL_TIMEOUT` | Seconds to wait for a free connection, default `30` |
| `DATABASE_POOL_RECYCLE` | Seconds after which a connection is replaced, default `-1` (never) |
| `REDIS_URL` | Redis URL, e.g. `redis://host:6379/0`, `rediss://` for TLS or `unix:///path/redis.sock`. See below |
| `REDIS_PASSWORD` | Redis password, if it's not in `REDIS_URL` |
| `REDIS_KEY_PREFIX` | Starts every key, default `proxium:`. Different ones let several installations share one Redis |
| `REDIS_POOL_MAX_CONNECTIONS` | Connections each process opens at most, default `100`. A command beyond them fails |
| `REDIS_SOCKET_CONNECT_TIMEOUT` | Seconds to connect to Redis, default `2` |
| `REDIS_SOCKET_TIMEOUT` | Seconds to wait for an answer of Redis, default `2` |

### Redis

Required, like PostgreSQL: instances on one database share their state in it, e.g. the migration lock, see
[Management commands](management.md). The Docker image runs its own Redis when `REDIS_URL` isn't set.

- The password goes either in the URL or in `REDIS_PASSWORD`, both is an error. Separate, it's easier to pass from a
  secret, e.g. in Kubernetes.
- If Redis doesn't answer within `REDIS_SOCKET_CONNECT_TIMEOUT` and `REDIS_SOCKET_TIMEOUT`, what needs it fails.
  Connection limits of the proxy hold on for a while, see below.
- Keep `maxmemory-policy noeviction`, the Redis default: a full Redis then refuses writes, and the proxy handles it
  as an outage. Other policies may drop keys of connection limits silently.

#### Connection limits

Every proxy instance keeps its open connections in Redis, so a limit of 10 connections is 10 across all instances.
A new connection is checked against the limit in one atomic round trip. Each connection is leased for
`PROXY_CONNECTION_LEASE` seconds and renewed every third of it: if an instance dies, its connections stop counting
on their own. Leases run on the clock of Redis, clocks of the instances don't matter.

If Redis goes down:

1. For `PROXY_REDIS_OUTAGE_TIMEOUT` seconds clients go on as usual. Each instance counts only its own connections,
   so with N instances up to N × limit may open.
2. Longer, new connections under connection limits are refused until Redis is back: HTTP clients get
   `503 Service Unavailable`, SOCKS5 ones a general failure. Open connections go on, and clients without
   connection limits aren't affected.
3. The proxy checks Redis every second. Once it answers, each instance writes all its open connections there, those
   opened during the outage too, and limits are shared again. Connections over the limit stay until they close, new
   ones are refused until there are fewer than the limit.

The log shows an error when Redis fails and a message when it's back.

Nothing is lost for good: Redis keeps only the connections open right now, and each instance knows all of its own.
An instance may be stopped or restarted anytime, during an outage too. Where counts may be off for a while:

| Case | Effect | For how long |
|---|---|---|
| Redis is down within the outage timeout | Up to N × limit connections | Until the extra ones close |
| An instance crashed, or stopped while Redis was down | Its connections still take places of the limit | Up to `PROXY_CONNECTION_LEASE` after their last renewal |
| Redis restarted empty, or failed over to a replica that missed the latest writes | Limits let up to the limit more in | Up to a third of `PROXY_CONNECTION_LEASE` |
| Redis restored from an older snapshot | Connections closed since still take places | Up to `PROXY_CONNECTION_LEASE` |

E.g. the proxy is stopped while Redis is down, then Redis and the proxy are started again: Redis either starts empty
or has the old connections, which have expired or expire within `PROXY_CONNECTION_LEASE`. The proxy starts with none
and counts as usual. A proxy started while Redis is down counts its own for `PROXY_REDIS_OUTAGE_TIMEOUT` from the
first failure, though in the Docker image it doesn't start then: migrations wait for Redis first.

`PROXY_REDIS_OUTAGE_TIMEOUT` must be at least `REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT`, as long as one
command may take. Otherwise no process starts.

## Proxy

| Variable | Description |
|---|---|
| `PROXY_LISTEN` | Addresses to listen on, default `127.0.0.1:8080`, see below |
| `PROXY_GRACEFUL_TIMEOUT` | Seconds open connections get to finish on shutdown, default `30` |
| `PROXY_REUSE_PORT` | Let another proxy listen on the same ports, default `true`, see [Restart without downtime](proxy.md#restart-without-downtime) |
| `PROXY_BACKLOG` | Connections waiting to be accepted per listening socket, default `1024`. Raise it if bursts of new connections stall. Takes effect on restart, see below |
| `PROXY_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, default `INFO` |
| `PROXY_SETTINGS_POLL_INTERVAL` | Seconds between lookups of the [settings](proxy.md#settings) from the admin UI, default `5` |
| `PROXY_CONNECTION_LEASE` | Seconds a crashed instance's connections keep counting toward connection limits, default `30`, see [Connection limits](#connection-limits) |
| `PROXY_REDIS_OUTAGE_TIMEOUT` | Seconds connection limits are counted in each instance alone while Redis is down, default `30`. At least the two Redis timeouts together, see [Connection limits](#connection-limits) |

`PROXY_LISTEN` is a comma-separated list of `host:port` pairs. A host is an IP address, a network or a host name,
IPv6 goes in brackets. A port may be an inclusive range. Every host listens on every port of its pair:

```bash
PROXY_LISTEN=127.0.0.1:8080                          # one socket
PROXY_LISTEN=localhost:8080                          # every address localhost resolves to
PROXY_LISTEN=0.0.0.0:8080,[::]:8080                  # all IPv4 and IPv6 interfaces
PROXY_LISTEN=10.0.0.0/29:10000-10999                 # 6 host addresses x 1000 ports
```

Host names are resolved once, on start.

Linux caps `PROXY_BACKLOG` at `net.core.somaxconn`, `4096` on recent kernels. To go higher, raise it too.
In Docker it belongs to the container's network, so set it on the container:

```bash
docker run --sysctl net.core.somaxconn=16384 -e PROXY_BACKLOG=16384 ...
```

With `--network host` the container shares the host's network: set it on the host, e.g. in `/etc/sysctl.d/`.

## API

| Variable | Description |
|---|---|
| `API_SECRET_KEY` | Secret that signs API user tokens, at least 32 characters. Changing it logs everyone out |
| `API_CORS_ORIGINS` | Comma-separated browser origins allowed to call the API, e.g. the admin dev server. Empty blocks all |
| `API_OUTGOING_POOL_MAX_SIZE` | IPs in one outgoing IP pool at most, default `256` |
| `API_POLICIES_MAX_PER_OWNER` | Policies assigned to one account or trusted network at most, up to `100`, default `32` |

## Management commands

| Variable | Description |
|---|---|
| `SUPERUSER_EMAIL` | `createsuperuser --no-input`: email, if `--email` isn't passed |
| `SUPERUSER_PASSWORD` | `createsuperuser --no-input`: password, there is no flag for it |
| `SUPERUSER_NAME` | `createsuperuser --no-input`: name, if `--name` isn't passed, default blank |
| `SUPERUSER_SURNAME` | `createsuperuser --no-input`: surname, if `--surname` isn't passed, default blank |

Without `--no-input` these are ignored: `createsuperuser` always prompts.

## Docker

Read only by the [image](installation.md#docker). There `DATABASE_URL`, `REDIS_URL`, `ENCRYPTION_KEY` and
`API_SECRET_KEY` are optional: unset, the bundled PostgreSQL and Redis run and the keys are generated once, all kept
in the volume. Redis keeps nothing: it starts empty each time.

| Variable | Description |
|---|---|
| `PROXIUM_SERVICES` | Services to run, comma-separated: `proxy`, `api`, `admin`. Default all |
| `SUPERUSER_CREATE` | `true` creates the superuser from `SUPERUSER_*` on start, an existing one is skipped. Default `false` |
| `ADMIN_TLS` | How the admin UI is served: `off`, `auto`, `files` or `internal`, see [Installation](installation.md#domain-and-https-for-the-admin-ui). Default `off` |
| `ADMIN_HOST` | Admin host name, e.g. `admin.example.com`. Needed by `auto` and `files`, `internal` defaults to `localhost` |
| `ADMIN_ACME_CA` | Own ACME server for `auto` instead of Let's Encrypt |
| `ADMIN_HTTP_PORT` | Admin HTTP port, default `80` |
| `ADMIN_HTTPS_PORT` | Admin HTTPS port, default `443` |
| `API_BIND` | Where the API listens, default the socket `unix:/run/proxium/api.sock` |
| `ADMIN_API_UPSTREAM` | Where the admin UI finds the API, default the same socket. `host:port` when the API runs in another container |
