# Deployment

Stillroom runs as four containers: PostgreSQL with pgvector, the API, one
worker, and the Next.js web app. Caddy is optional and only needed when you
want a real TLS certificate instead of Tailscale.

```text
browser -> Caddy (optional TLS) -> web (Next.js)
                              -> api (FastAPI) -> db (PostgreSQL)
                                                    ^
                                      worker ---------+
```

> **Verification status:** the Compose file and Dockerfiles are written for
> this repository, but Docker is not installed on the machine where Phase 8
> was built. They have not been started here. The database and application
> workflows they wrap are tested locally; treat the first `docker compose up`
> as a deployment acceptance step and read the logs.

## What you need

- Docker Engine with Compose v2 (Docker Desktop on Windows or macOS)
- Ollama on the host if you want local AI (optional; the app starts without it)
- A hostname and, for access outside your tailnet, a DNS record pointed at the
  server

## First start

```bash
cp deploy/env.example .env
# Fill in JWT_SECRET, POSTGRES_PASSWORD, PUBLIC_URL, and PUBLIC_HOST.
# Generate the two secrets with:
#   python -c "import secrets; print(secrets.token_hex(32))"

docker compose build
docker compose up -d db api worker web
docker compose ps
curl http://127.0.0.1:3000/api/py/health
```

Open <http://127.0.0.1:3000>. The web container is published on loopback
only. The API and database are not published at all; everything reaches them
through the Compose network.

The API container runs `alembic upgrade head` before it starts. If the
migration fails, the API stays down and `docker compose logs api` shows the
error. Do not start a second API replica: one process owns the migration step.

### Why `APP_ENV=production` and `COOKIE_SECURE=true`

The session cookie is sent only over HTTPS in this mode. A plain
`http://127.0.0.1:3000` request over loopback is a development convenience,
not a signed-in deployment: use Caddy or Tailscale before you rely on it from
another device.

## Ollama on the host

Compose points at `http://host.docker.internal:11434` and adds the Linux host
gateway entry. Linux Ollama listens on `127.0.0.1` by default, so expose it to
the Docker bridge deliberately:

```bash
# systemd drop-in or shell profile; restart Ollama afterwards.
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

If the host is not reachable at `host.docker.internal`, set
`OLLAMA_BASE_URL` in `.env` to the address the containers can reach. Never
publish port 11434 to the internet.

## Caddy and automatic TLS

Caddy is behind the `caddy` profile. With a public DNS name pointed at the
server:

```bash
# .env
PUBLIC_HOST=stillroom.example.com
PUBLIC_URL=https://stillroom.example.com

docker compose --profile caddy up -d
```

Caddy obtains and renews the certificate, redirects HTTP to HTTPS, adds HSTS
to web responses, and proxies `/api/py/*` straight to the API. The Next.js
rewrite is still used when you reach port 3000 directly.

For a name that only resolves on your LAN, add the DNS record or `/etc/hosts`
entry on each client. Caddy falls back to its local CA for `.localhost` and
other internal names. Export that root certificate and trust it on the
clients, otherwise browsers warn:

```bash
docker compose cp caddy:/data/caddy/pki/authorities/local/root.crt ./caddy-root.crt
```

Only ports 80 and 443 are published by Caddy. Keep the host firewall closed to
everything else except the ports you actually use.

## Tailscale instead of opening ports

Tailscale gives each device a private HTTPS name and needs no inbound port
forwarding. This is the recommended remote-access route for a home server.

1. Install Tailscale on the server and the client, then `tailscale up` on both.
2. Set `PUBLIC_HOST` to the machine name and `PUBLIC_URL` to its HTTPS URL:

   ```bash
   PUBLIC_HOST=stillroom.tailnet-name.ts.net
   PUBLIC_URL=https://stillroom.tailnet-name.ts.net
   ```

3. Start everything except Caddy:

   ```bash
   docker compose up -d db api worker web
   tailscale serve --bg 3000
   ```

4. Open the `PUBLIC_URL` from another device on the tailnet.

`tailscale serve` terminates TLS and forwards to the web container on
loopback. Do not also enable Tailscale Funnel unless you intentionally want the
app on the public internet. Tailscale ACLs decide who can reach it.

## Operations

```bash
docker compose logs -f api worker    # follow logs
docker compose restart api worker    # after changing .env
docker compose down                  # stop, keep volumes
docker compose down -v               # DELETE the database volume
```

The owner can open `/diagnostics` for database size, queue counts, model
status, AI usage for 30 days, and the newest host backup file. Slow SQL is
logged at `WARNING` on the `stillroom.slow_query` logger; lower
`SLOW_QUERY_MS` while investigating.

### Updating

```bash
docker compose exec -T db pg_dump -U stillroom -Fc stillroom > backups/before-update.dump
git pull
docker compose build
docker compose up -d
docker compose logs -f api
```

The API runs additive migrations on boot. Read the release notes before a
major version, and keep the pre-update dump until the new version has served a
real request.

## Backups with Compose

The host scripts (`scripts/backup.sh`) expect a PostgreSQL client on the host.
With Compose, use the database container:

```bash
mkdir -p backups
docker compose exec -T db pg_dump -U stillroom -Fc stillroom \
  > "backups/stillroom-$(date +%Y-%m-%d-%H%M).dump"
```

Verify without touching the live database:

```bash
DUMP=backups/stillroom-2026-11-25-1200.dump
docker compose exec -T db createdb -U stillroom stillroom_verify
# Copy the dump into the container or pipe it through stdin:
docker compose exec -T db pg_restore -U stillroom -d stillroom_verify \
  --no-owner --no-privileges < "$DUMP"
docker compose exec -T db psql -U stillroom -d stillroom_verify -Atc \
  "select count(*) from stories; select version_num from alembic_version"
docker compose exec -T db dropdb -U stillroom stillroom_verify
```

The full restore drill, including the destructive path and the write test, is
in [backups.md](backups.md). Run it before trusting any backup rotation.

## Hardening checklist

- [ ] `.env` is not committed; `git status` is clean of secrets.
- [ ] `JWT_SECRET` and `POSTGRES_PASSWORD` are random and unique to this host.
- [ ] Only Caddy (80/443) or Tailscale is reachable from other devices.
- [ ] PostgreSQL has no published port.
- [ ] `AI_SETTINGS_ENCRYPTION_KEY` is set before users add cloud provider keys.
- [ ] SMTP is configured, or you accept reset links appearing in API logs.
- [ ] A backup exists **and** `verify-backup.sh` or the Compose drill passed.
- [ ] `/diagnostics` shows the expected schema revision and no dead jobs.