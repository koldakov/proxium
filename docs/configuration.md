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
  Connection limits, speed limits and traffic quotas of the proxy hold on, see below.
- Keep `maxmemory-policy noeviction`, the Redis default: a full Redis then refuses writes, and the proxy handles it
  as an outage. Other policies may drop keys of connection limits and quotas silently.

#### Connection limits

Every proxy instance keeps its open connections in Redis, so a limit of 10 connections is 10 across all instances.
A new connection is checked against the limit in one atomic round trip. Each connection is leased for
`PROXY_CONNECTION_LEASE` seconds and renewed every third of it: if an instance dies, its connections stop counting
on their own. Leases run on the clock of Redis, clocks of the instances don't matter.

If Redis goes down:

1. For `PROXY_REDIS_OUTAGE_TIMEOUT` seconds clients go on as usual. Each instance counts only its own connections,
   so with N instances up to N × limit may open.
2. Longer, new connections under connection limits are refused until Redis is back: HTTP clients get
   `503 Limits Unavailable`, SOCKS5 ones a general failure. Open connections go on, and clients without
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

#### Speed limits

Every limited client has a bucket in Redis per direction, so 1 MB/s is 1 MB/s across all instances. Each instance
takes `PROXY_SPEED_BATCH` seconds of the rate at once, 100 KB of 1 MB/s by default, and spends it on its
connections: one round trip per batch while bytes flow, none while they don't. So each instance may go over the
limit by one batch: smaller batches are more precise, larger ones take fewer round trips. Buckets refill on the clock
of Redis, clocks of the instances don't matter. The connection scope is counted in memory: one connection has
nothing to share.

A batch is taken at once, in debt if the bucket hasn't got it yet: the instance waits until the bucket pays it,
then spends it. Instances wait in the order their requests reach Redis, so one far from Redis gets its share too.
A batch is at most the burst. With a burst under what the rate moves in a round trip to Redis, a client gets less
than its rate: e.g. a burst of 32 KB at 100 Mbit/s, 3 ms away from Redis. The default burst, a second of the rate,
is far from that.

Other errors of Redis than an outage, e.g. of the script for one key or a permission taken away in the ACL, leave
that key to the instance alone for a second, then it tries Redis again. The other keys stay in Redis. Such errors
are logged at most once a second.

If Redis goes down, each instance limits its own connections until Redis is back, with no timeout: with N instances
a client may get up to N × the rate meanwhile. Until a hanging Redis counts as down, up to
`REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT`, the data of limited clients waits. Then each of them starts
with a full burst in the instance, once. A speed limit only slows connections down, so going over it ends
with the outage, while refusing would stall the traffic of every limited client. The proxy checks Redis every
second with a write, so a full Redis that still answers stays down until it takes writes again. The log shows an
error when Redis fails and a message when it's back.

#### Traffic quotas

Every proxy instance writes its traffic to the database about once a minute, and every second it puts what it
hasn't written yet in Redis. A quota counts the traffic in the database plus what every instance has in Redis, so
10 GB is 10 GB across all instances. Each instance sees the others' traffic within about two seconds: a client may
go over a quota by about two seconds of its traffic per instance, plus the second between checks of an open
connection. Each instance makes one write per client with traffic not in the database yet and one read per client
under a quota every second, in batches of 1000: with tens of thousands of active clients, size Redis for it. Every
write of an instance makes the others read that client's sums from the database again: with N instances, about N
reads a minute per client under a quota, in batches too.

What an instance has in Redis is leased for `PROXY_CONNECTION_LEASE` seconds and renewed every second. Right after
an instance writes traffic to the database, it takes the same bytes out of Redis in one step, and the others read
the database again. Until then, or until its lease expires if it crashes in between, they may count those bytes
twice: the quota ends a bit sooner, never later. Traffic of a crashed instance not yet in the database is lost, as
before, and stops counting with its lease.

If Redis goes down:

1. For `PROXY_REDIS_OUTAGE_TIMEOUT` seconds clients go on as usual. Each instance counts the database, its own
   traffic and the others' as last read from Redis: a short blip loses nothing. Once a minute it reads the database
   again, where the others have written their traffic by then, and counts alone from there: with N instances a
   client may go over a quota by up to what N − 1 of them haven't written.
2. Longer, connections under quotas are refused until Redis is back: new ones get `503 Limits Unavailable` over HTTP,
   a general failure over SOCKS5, open ones are cut on their next check. Clients without quotas aren't affected.
   Open connections are cut, unlike under connection limits, on purpose. An open connection can't raise the number
   of connections, and going over a speed limit ends with the outage. Over a quota an open download goes on adding
   gigabytes, and nothing takes them back: with N instances each counting alone, a long outage would let a client
   through as much as it can download. A quota sold to a client is a promise to stop at it, so the proxy stops
   rather than guesses. If Redis may stay down for long, e.g. during maintenance, raise `PROXY_REDIS_OUTAGE_TIMEOUT`
   for that time.
3. The proxy checks Redis every second. Once it answers, each instance puts its unwritten traffic there again,
   reads the others' and reads the database again, quotas are shared again.

If only one instance loses Redis while the others still reach it, its unwritten traffic expires there within
`PROXY_CONNECTION_LEASE`, and its writes reach the others only once it's back: they count without it. It refuses
quotas itself after `PROXY_REDIS_OUTAGE_TIMEOUT`, so a client may go over a quota by up to what it hasn't written,
as above. If it stops before Redis is back, what it wrote meanwhile reaches the others once any instance writes
traffic of the same client: within about a minute where the client still connects.

Nothing is lost for good: the traffic itself is in the database, Redis keeps only what isn't there yet, and each
instance knows its own.

## Proxy

| Variable | Description |
|---|---|
| `PROXY_LISTEN` | Addresses to listen on, default `127.0.0.1:8080`, see below |
| `PROXY_GRACEFUL_TIMEOUT` | Seconds open connections get to finish on shutdown, default `30` |
| `PROXY_REUSE_PORT` | Let another proxy listen on the same ports, default `true`, see [Restart without downtime](proxy.md#restart-without-downtime) |
| `PROXY_WORKERS` | Proxy processes on the same ports, default `1`, one per CPU core to use them all. Needs `PROXY_REUSE_PORT=true`, see [Workers](proxy.md#workers) |
| `PROXY_BACKLOG` | Connections waiting to be accepted per listening socket, default `1024`. Raise it if bursts of new connections stall. Takes effect on restart, see below |
| `PROXY_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, default `INFO` |
| `PROXY_SETTINGS_POLL_INTERVAL` | Seconds between lookups of the [settings](proxy.md#settings) from the admin UI, default `5` |
| `PROXY_HEARTBEAT_INTERVAL` | Seconds between reports of each instance to the database, default `30`. An instance that misses three in a row shows as unknown, see [Instances](proxy.md#instances) |
| `PROXY_CONNECTION_LEASE` | Seconds a crashed instance's connections keep counting toward connection limits, and its unwritten traffic toward quotas, default `30`, at least `3 + REDIS_SOCKET_CONNECT_TIMEOUT + REDIS_SOCKET_TIMEOUT`, `7` by default, see [Connection limits](#connection-limits) and [Traffic quotas](#traffic-quotas) |
| `PROXY_REDIS_OUTAGE_TIMEOUT` | Seconds connection limits and quotas are counted in each instance alone while Redis is down, default `30`. At least the two Redis timeouts together, see [Connection limits](#connection-limits) and [Traffic quotas](#traffic-quotas) |
| `PROXY_SPEED_BATCH` | Seconds of a speed limit's rate an instance takes from Redis at once, default `0.1`. Each instance may go over a limit by one batch, see [Speed limits](#speed-limits) |
| `PROXY_NAME` | Names the instance in `Proxy-Status` of HTTP responses, default `proxium`, e.g. its host name. Printable ASCII, an IP or a name with spaces is sent in quotes, see [Proxy](proxy.md) |

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
| `API_GLOBAL_POLICIES_MAX` | Global policies at most, turned off ones too, up to `100`, default `32`. Lowering it keeps the ones past it working |

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
