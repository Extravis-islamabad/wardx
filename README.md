# WardX — Privileged Access Management

Working name (trademark check pending). Stands alone, or plugs into MonetX.
Same stack as MonetX so engineers move between them freely.

| Part | Stack | Folder |
|---|---|---|
| API, vault, workers | FastAPI · async SQLAlchemy 2 · Pydantic v2 · PostgreSQL · raw SQL migrations · APScheduler | `Backend/` |
| Web console | React 18 · Vite · TypeScript strict · antd 6 · TanStack Query · RHF + zod · Tailwind | `Frontend/` |

## What works today (Phase 0 → start of Phase 1)

- **Identity:** local users, argon2id passwords, JWT access + refresh, lockout after 5 failures,
  sign-out-everywhere (token version), roles `admin` / `approver` / `auditor` / `user`.
- **Vault:** envelope encryption — AES-256-GCM per secret version with its own data key, wrapped by
  a key-encryption key (KEK). Owner + version bound as associated data, so a ciphertext moved to
  another account fails to open. KEK rotation via retired keys. HSM / KMS slot in behind `Keyring`.
- **Inventory:** targets (Cisco, Huawei, H3C, Juniper, MikroTik, Fortinet, Palo Alto, Linux,
  Windows, databases) and privileged accounts with per-account policy: needs approval, exclusive,
  max minutes.
- **Access:** request → approve/deny (never your own) → check out → reveal (audited, no-store) →
  check in / admin revoke; exclusive check-out is race-safe (row lock); expiry sweeper closes
  overdue check-outs and stale requests.
- **Audit:** every action, success or failure, in a SHA-256 hash chain; table is append-only by
  trigger; `POST /audit/verify` pinpoints the first tampered event.
- **SSH session gateway** (`WARDX_APP_ROLE=gateway`): `ssh -p 2222 you%account%target@wardx`.
  Signs in with the WardX password (same lockout), checks the account out for the session (or uses
  your approved request / existing check-out), injects the vaulted password or key — the user never
  sees it — and hands the account back on disconnect. Records every session (asciicast, SHA-256
  stored in the audit chain), logs each command *before* it runs, erases commands that match deny
  rules on the device before Enter reaches it, pins target host keys on first use and refuses to
  send the credential to a changed key, and lets an admin kill a live session from the console.
  SFTP, port and agent forwarding are off.
- **Console:** dashboard, accounts (check out / request / reveal with 30 s auto-hide / SSH connect
  hint), check-outs, approval queue, live sessions with replay and command log, command policy with
  a rule tester, targets with host-key status, audit with integrity check, users; dark and light themes.

## Run it locally

```bash
# Backend (Python 3.11+)
cd Backend
uv venv --python 3.11 .venv && uv pip install --python .venv/bin/python -r requirements-dev.txt
cp .env.example .env                       # point WARDX_DATABASE_URL at an empty PostgreSQL 14+
.venv/bin/uvicorn main:app --port 8000     # runs migrations, creates the first admin
cat .wardx/initial-admin-password          # development only; set WARDX_BOOTSTRAP_ADMIN_PASSWORD otherwise

# Session gateway (second process, same .env)
WARDX_APP_ROLE=gateway .venv/bin/python main.py   # listens on :2222

# Frontend (Node 20+)
cd Frontend
npm install && npm run dev                 # http://localhost:5173, proxies /api to :8000
```

No PostgreSQL handy? `pip install pgserver` gives an embedded one; the integration tests use it
automatically.

## Tests

```bash
cd Backend && .venv/bin/python -m pytest -q   # unit + integration (embedded PostgreSQL)
cd Frontend && npm run build                  # tsc strict + vite build
```

### Gateway: known limits

- Commands are rebuilt from keystrokes. With deny rules active, keys the gateway cannot follow
  (arrows, history, Tab) are disabled; without rules they pass and the logged line is marked
  `edited`. Typed passwords at device prompts (e.g. `su`) are logged as commands.
- Recordings are files under `WARDX_RECORDING_DIR`; object storage (S3/MinIO, WORM) comes with HA.
- Rule changes apply to sessions that start after the change.

## Next (Phase 1 MVP, see the PAM Product Plan)

1. Telnet through the gateway; vendor-aware prompts for enable/privilege levels (Cisco, Huawei).
2. Password rotation drivers (network devices via Netmiko, Linux, Windows/AD) with verify + rollback.
3. Discovery (subnets, AD, MonetX device registry sync via `targets.external_ref`).
4. MFA (TOTP, WebAuthn), LDAP / SAML / OIDC sign-in.
5. RDP gateway (guacd), break-glass, SIEM export.
