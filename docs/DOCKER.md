# Docker deployment

One Compose file runs the whole product:

| Service   | Image            | What it does                                              | Port (host)      |
|-----------|------------------|-----------------------------------------------------------|------------------|
| `db`      | postgres:16      | WardX database (`pg-data` volume)                         | internal only    |
| `api`     | `Backend/`       | FastAPI + scheduler (`WARDX_APP_ROLE=api`); runs migrations and creates the first admin on start | internal only |
| `gateway` | `Backend/`       | SSH session gateway (`WARDX_APP_ROLE=gateway`)            | `2222`           |
| `web`     | `Frontend/`      | nginx serving the console, proxying `/api/` to `api`      | `3741`           |

`api` and `gateway` share the `wardx-data` volume (`/data`): recordings the gateway writes are
replayed by the API, and the gateway's SSH host key is kept in `/data/keys`.

## First start

```bash
sh scripts/docker-init-env.sh      # writes .env with fresh secrets, prints the admin password
docker compose up -d --build
docker compose ps                  # all four should become "healthy"
```

Open `http://<host>:3741` and sign in as `admin`. Prefer to fill secrets yourself? Copy
`.env.docker.example` to `.env` and set `POSTGRES_PASSWORD`, `WARDX_JWT_SECRET`,
`WARDX_VAULT_KEK` and `WARDX_BOOTSTRAP_ADMIN_PASSWORD`. Containers run with
`WARDX_ENVIRONMENT=production`, so the API refuses to start without them.

**Back up `WARDX_VAULT_KEK` offline.** Without it no vaulted secret can be decrypted.

## Before going live

- Put TLS in front of `web` (a load balancer or a reverse proxy terminating HTTPS) and set
  `WARDX_CORS_ORIGINS` / `WARDX_GATEWAY_PUBLIC_HOST` to the real names.
- Narrow `WARDX_TRUSTED_PROXIES` to the actual proxy network.
- Keep `MFA_REQUIRED_ROLES` at least `["admin"]`.
- To bring your own gateway host key, mount it read-only and set
  `WARDX_GATEWAY_HOST_KEY_FILE`; otherwise one is generated once on the volume.
- Back up `pg-data` and `wardx-data` (see `docs/` backup runbooks); for HA/DR follow
  `Backend/docs/phase1/HA_DR.md`.

## Day-2

```bash
docker compose logs -f api gateway     # structured logs
docker compose pull && docker compose up -d --build   # upgrade; migrations run on api start
docker compose down                    # stop (volumes kept); add -v only to wipe all data
```

To run the scheduler separately, set the `api` service to `WARDX_APP_ROLE=api_only` and add a
service from the same image with `WARDX_APP_ROLE=scheduler` (leader election keeps one active).
