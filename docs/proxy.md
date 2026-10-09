# Proxy

## Protocols

Every port speaks HTTP and SOCKS5, the protocol is detected by the first byte of the connection.
Clients authenticate with proxy accounts from the database, inactive and expired ones are refused:

```bash
curl -x http://username:password@127.0.0.1:8080 https://example.com                  # basic account
curl -x http://127.0.0.1:8080 --proxy-header "Proxy-Authorization: Bearer <token>" https://example.com  # token account
curl -x socks5h://username:password@127.0.0.1:8080 https://example.com                # basic account over SOCKS5
```

HTTP supports CONNECT tunnels and plain HTTP forwarding. SOCKS5 supports only CONNECT, with IPv4, IPv6 and domain
targets, and only basic accounts: the protocol has username/password authentication but no tokens.
Use `socks5h://` so the proxy resolves domains, with `socks5://` curl resolves them itself.

## TLS

Clients may encrypt the connection to the proxy, on the same ports: a connection starting with a TLS handshake is
decrypted, and HTTP or SOCKS5 is detected inside. Credentials then don't travel in the clear. TLS is on while a
certificate is active: add one under TLS certificates in the admin UI, the first one is activated right away.
Without one, TLS clients get a handshake failure, plain HTTP and SOCKS5 keep working.

```bash
curl -x https://username:password@proxy.example.com:8080 https://example.com
```

The certificate must be for the host name clients connect to. One certificate is active at a time and serves all
ports, for several names use one with all of them in it. Activating another one, on adding it or later on its
page, turns the active one off: new connections get it within the certificate cache TTL ([settings](#settings)), open
ones keep theirs, no restart needed. The proxy looks the certificate up once per that TTL, not on every connection: TLS
clients can't load the database before they authenticate. The admin UI names the one turned off, and if another admin has activated one meanwhile, it refuses and shows the new state
instead of turning off a certificate you haven't seen. The active one can't be deleted, deactivate it first.

A self-signed certificate works too, the admin UI generates one for given names. Clients trust it only if told
to: download the certificate from its page for curl's `--proxy-cacert`, or skip the check with `--proxy-insecure`.

```bash
curl -x https://username:password@proxy.example.com:8080 --proxy-cacert proxium-1.pem https://example.com
```

Private keys are stored encrypted with `ENCRYPTION_KEY`, the API never returns them. Generate the key once and give
the same one to the proxy, the API and the management commands:

```bash
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Losing or changing it makes the stored keys unreadable: TLS clients are refused with "can't be decrypted" in the
log until the certificate is uploaded again.

To replace the key without downtime, e.g. after a leak:

1. Generate a new key. Set it as `ENCRYPTION_KEY` and the current one as `ENCRYPTION_OLD_KEYS` for the proxy, the
   API and the management commands, then restart them. Both keys now decrypt, new secrets get the new one.
2. Re-encrypt the stored secrets with the new key. Stopped halfway, it's just run again:

   ```bash
   uv run --env-file .env proxium-manage rotateencryptionkey
   ```

3. Remove `ENCRYPTION_OLD_KEYS` everywhere and restart again.

The proxy needs a writable temporary directory: Python's `ssl` loads a key only from a file, not from memory
([python/cpython#60691](https://github.com/python/cpython/issues/60691)), so the decrypted key goes to a file
readable by the proxy's user alone and is removed right after loading. In a container with a read-only root, point
`TMPDIR` to a tmpfs, e.g. an `emptyDir` with `medium: Memory` in Kubernetes: the key then never reaches a disk.
Without it, TLS clients are refused with "Can't write the certificate to a temporary file" in the log.

A renewed certificate, e.g. from Let's Encrypt, goes in with `importcert`, see
[Management commands](management.md). certbot can run it after every renewal, with the same environment as
the proxy:

```bash
certbot renew --deploy-hook 'cd /opt/proxium && uv run --env-file .env proxium-manage importcert --no-input \
  --cert "$RENEWED_LINEAGE/fullchain.pem" --key "$RENEWED_LINEAGE/privkey.pem"'
```

SOCKS5 inside TLS works too, but few clients support it, curl doesn't. HTTP/2 to the proxy isn't supported, clients
fall back to HTTP/1.1.

Don't terminate TLS in front of the proxy, e.g. with nginx `stream`: the proxy would see nginx's connection
instead of the client's, so trusted networks would check nginx's IP, and the `listener` outgoing mode would take
the address nginx connects to.

## Trusted networks

Clients from trusted networks use the proxy without credentials, over HTTP and SOCKS5 alike. There are none by
default, so everyone needs an account. Add them in the admin UI or with the API (`/api/trusted-networks`), e.g.
`192.168.0.0/16` for a local network or `10.0.0.5` for a single address. Add only networks you control: anyone in
them gets in.

```bash
curl -x http://127.0.0.1:8080 https://example.com         # from a trusted network
curl -x socks5h://127.0.0.1:8080 https://example.com
```

New connections follow changes within the trusted network cache TTLs ([settings](#settings)). Clients connected right now keep
their open connections until they close: removing a network doesn't cut them off at once.

A client that sends credentials is checked as an account even from a trusted network. The trusted network
authenticator itself refuses any credentials, since it can't check them: registered for a credentials kind by
mistake, it doesn't let in any password.

Networks may nest, e.g. `10.0.0.0/8` for the office and `10.1.2.3` for a CI server inside it. The narrowest
active one names the client in logs, e.g. `network:10.1.2.3/32`, and turning off one keeps the other working.
The admin UI lists the networks containing the one being edited and the ones inside it, page by page, and
tells how many keep trusting the addresses of a network being deleted. `/0` trusts the whole internet: the admin UI
asks to confirm saving it and warns while one is active.

`/api/trusted-networks` filters: `contains=<network>` for networks that contain it, `within=<network>` for ones
inside it, `isActive=true|false`, `prefixLength=<n>`, e.g. `?isActive=true&prefixLength=0` for ones open to everyone.

## Outgoing IPs

On a server with several IPs, each account and trusted network picks the one sites see, its outgoing mode:

- `system`, the default: the OS picks, usually the main IP of the server.
- `listener`: the IP the client connected to. A client of `203.0.113.11:8080` goes out from `203.0.113.11`, so
  listen on every IP, e.g. `PROXY_LISTEN=203.0.113.8/29:8080`. It works on `0.0.0.0` too.
- `pool`: a random IP of the account's pool, picked anew for every connection. A pool of one IP is a dedicated IP.

First add the server's IPs under Outgoing IPs in the admin UI. Then pick the mode on the account or trusted
network form: for `pool`, the IPs of the pool go right under it, on creating too. Later the pool is edited on the
account's page or the network's form, and changes apply to new connections within the cache TTL of passed checks.

A pool takes IPs of one family, IPv4 or IPv6: an IPv4 IP can't reach IPv6-only sites and back, so a mixed pool
would fail at random. The admin offers only the IPs a pool can take. A pool in use keeps at least one IP, switch
the mode first to empty it. An IP in a pool can't be deleted, and an IP's address can change only within its
family. A pool holds up to `API_OUTGOING_POOL_MAX_SIZE` IPs.

The proxy binds the outgoing socket to the IP before connecting, so the IP must be on the server's interfaces,
e.g. `ip addr add 203.0.113.11/32 dev eth0`, and routed to it. Nothing checks that on saving, the API may run on
another host: a connection from an IP that isn't there fails with "not on this host or loopback" in the log, and
so does one from loopback, e.g. `listener` on `127.0.0.1`. Nothing falls back to another IP. Behind cloud NAT,
use the private IPs the public ones map to. IPs of different providers need policy routing (`ip rule`) in the OS.

## Policies

A policy limits how clients use the proxy: how many connections they open at once, how fast data goes and how much
of it they may move. Create
policies under Policies in the admin UI. A global one applies to every client, any other to the accounts and
trusted networks it's assigned to, on their pages. A client gets the limits of all its policies at once: a policy
only adds limits, the strictest one wins. To give some clients more than a global policy allows, raise its limit
and set the lower one in a policy assigned to the rest.

Each limit is counted over a scope: one connection, an account or network with all its connections, a client IP,
a target host or the whole proxy. E.g. 10 connections per account, or 100 Mbit/s for the whole proxy that all
clients share. Past a connection limit new connections are refused, HTTP clients get `429 Too Many Connections`.
A speed limit never cuts a connection, it slows it down. It's set per direction: download, upload or each way on
its own. After a pause up to the burst goes at once, one second of the rate unless set.

A traffic quota caps the gigabytes of one account or network per period: every N days or months, or in total
without reset. It counts downloads, uploads or both together. Past it new connections are refused, HTTP clients
get `429 Quota Exceeded`, and open ones are cut within a second. Periods follow one another from a UTC day: for a
global policy it's set on the policy, for an assigned one on the account or network page, next to the policy,
e.g. the day the client paid. Assigning sets it to that day. Monthly periods from the 31st start on the last day
of shorter months. Usage is the traffic in the database plus what the proxy hasn't written yet: traffic of other
proxy processes counts within a minute.

The limits of a policy sit in rules, each with a condition. In each policy the first rule whose condition matches
applies, so put the narrow rules first and a rule without conditions last for everything else: e.g. 10 Mbit/s on
weekdays from 9:00 till 18:00 in your time zone, 100 Mbit/s otherwise. A rule without a match leaves the client
free of that policy. A condition checks the time (days of the week and hours, past midnight too), the target host
with its subdomains, the target IP, the target port, the protocol (HTTP, HTTP CONNECT tunnels, SOCKS5), the client
IP or TLS to the proxy. Conditions of a rule must all match or any one of them, each can be turned into its
opposite. Open connections switch rules on their next data, checked once a second, e.g. when the night starts: the
old limits let go, the new ones apply, and if those refuse, e.g. no connection is free, the connection is cut.
Hosts compare by the name the client asked for: a target IP is matched by networks, not names.

E.g. to slow everything down in working hours except work sites, one rule is enough: all conditions match, Time
Mon–Fri 09:00–18:00, Target domain `company.com, github.com` with Not, speed 5 Mbit/s per account. Off hours or to
work sites the rule doesn't match and the policy limits nothing. SOCKS5 clients must leave DNS to the proxy, e.g.
`socks5h://` in curl: a client that resolves names itself sends an IP, which no domain matches.

The proxy looks policies up every `PROXY_SETTINGS_POLL_INTERVAL` seconds. A change reaches new connections, open
ones keep the limits they started with, though a connection limit changed in place keeps counting them.
Assigning a policy reaches a client within the cache TTL of passed checks. Limits are counted in the proxy's memory: with several
proxy processes each counts its own. An account or network takes up to `API_POLICIES_MAX_PER_OWNER` policies.

## Settings

The Settings page of the admin UI holds what the proxy does with connections. The proxy looks the settings up
every `PROXY_SETTINGS_POLL_INTERVAL` seconds and applies them without a restart: new connections get them, open
ones keep the old.

- Allowed networks: the proxy reaches only the public internet, loopback, private networks and cloud metadata
  (`169.254.169.254`) are blocked. List the private networks clients may reach anyway, e.g. `10.0.0.0/8`. Every
  client gets them, accounts and trusted networks alike.
- Timeouts, seconds: handshake, for a client to authenticate and send its request, `10` by default; idle, after
  which a silent tunnel is closed, `300`; connect, to resolve and reach a target, `10`.
- Cache TTLs, seconds, `10` by default each: how long the proxy reuses checks instead of looking them up and
  hashing secrets on every connection. Basic accounts, token accounts and trusted networks have two each: passed,
  within which a revoked or expired account keeps connecting and a removed trusted network stays trusted, and
  refused, within which a new or re-enabled one isn't let in yet. The TLS certificate has one: how soon activating
  another one applies. Lowering a TTL drops what it cached, so it applies at once. If the database is down,
  clients without a cached check are refused.

Check an account with a site that shows the caller's IP:

```bash
curl -x http://USERNAME:PASSWORD@127.0.0.1:8080 https://ifconfig.me
```

`Ctrl+C` (SIGINT) or SIGTERM stops accepting and waits up to `PROXY_GRACEFUL_TIMEOUT` for open connections.
A second signal stops immediately.
