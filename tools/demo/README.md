# MonetX fetch demo

`monetx_fetch_demo.py` behaves like a MonetX collector against the WardX credential provider
(contract: `docs/integrations/monetx-credential-provider-api.md`): it gets an application token,
fetches a device credential by `external_ref`, caches it in memory by `version_id`, logs in to
the Linux lab container with it, and, after WardX rotates the password, shows the client rule
"device rejected the cached credential → re-fetch once → retry once".
`seed_demo.py` prepares a scratch WardX through its admin API.

Lab only: a scratch database and a throwaway `wardx-lab-linux-demo` container. Every secret
lives in a file (mode 0600) and is never printed or passed on a command line.

Run from the repository root. Needs `Backend/.venv`, Docker and the lab image
(`sh lab/lab.sh build`). The API port is 8011; if it is taken, use another and change `--url`.

```bash
export DEMO=/tmp/wardx-demo && mkdir -p -m 700 $DEMO && umask 077

# 1. A scratch database (embedded PostgreSQL from the Backend venv); prints its socket dir.
PGHOST=$(Backend/.venv/bin/python -c "
import pgserver; s = pgserver.get_server('$DEMO/pg', cleanup_mode=None)
s.psql('CREATE DATABASE wardx_demo;'); print(s.get_uri('wardx_demo').split('host=')[1])")

# 2. Secrets, in files only.
python3 -c 'import secrets; print("Adm-" + secrets.token_urlsafe(18))' > $DEMO/admin-password
python3 -c 'import secrets; print("Lab-" + secrets.token_urlsafe(18))' > lab/.secrets/linux-demo
python3 -c 'import base64, secrets; print(base64.b64encode(secrets.token_bytes(32)).decode())' > $DEMO/kek
python3 -c 'import secrets; print(secrets.token_urlsafe(48))' > $DEMO/jwt

# 3. The Linux lab device (the password reaches docker through its environment).
LAB_USERS="wardx_rot_demo:$(cat lab/.secrets/linux-demo)" docker run -d --name wardx-lab-linux-demo \
  --network wardx-lab -p 127.0.0.1:2242:22 -e LAB_USERS wardx-lab/linux-ssh:1

# 4. WardX API on 8011 with rotation on (second terminal, or append & to background it).
(cd Backend && WARDX_ENVIRONMENT=test WARDX_APP_ROLE=api \
  WARDX_DATABASE_URL="postgresql+asyncpg://postgres:@/wardx_demo?host=$PGHOST" \
  WARDX_JWT_SECRET="$(cat $DEMO/jwt)" WARDX_VAULT_KEK="$(cat $DEMO/kek)" \
  WARDX_BOOTSTRAP_ADMIN_PASSWORD="$(cat $DEMO/admin-password)" WARDX_RECORDING_DIR=$DEMO/rec \
  WARDX_ROTATION_ENABLED=true WARDX_ROTATION_TICK_SECONDS=5 WARDX_ROTATION_JITTER_SECONDS=0 \
  .venv/bin/uvicorn main:app --host 127.0.0.1 --port 8011)

# 5. Seed: target (external_ref monetx-demo-device-1, host key pinned), account, application
#    identity allowed from 127.0.0.1 with 'fetch'. Note the client_id it prints.
WARDX_ADMIN_PASSWORD_FILE=$DEMO/admin-password Backend/.venv/bin/python tools/demo/seed_demo.py seed \
  --url http://127.0.0.1:8011 --secret-out $DEMO/client-secret
CLIENT_ID=wxa_...   # from the line "application monetx-demo-collector client_id=..."

# 6. Pin the device's SSH host key for the collector.
ssh-keyscan -p 2242 -t ed25519 127.0.0.1 > $DEMO/known_hosts 2>/dev/null

# 7. The collector: poll 1 fetches and logs in; poll 2 (40 s later) uses its cache.
WARDX_CLIENT_SECRET_FILE=$DEMO/client-secret Backend/.venv/bin/python tools/demo/monetx_fetch_demo.py \
  --url http://127.0.0.1:8011 --client-id $CLIENT_ID --external-ref monetx-demo-device-1 \
  --login 127.0.0.1:2242 --known-hosts $DEMO/known_hosts --polls 2 --interval 40 &

# 8. Meanwhile WardX rotates the device password (its own engine, a real password change).
sleep 5; WARDX_ADMIN_PASSWORD_FILE=$DEMO/admin-password Backend/.venv/bin/python tools/demo/seed_demo.py rotate \
  --url http://127.0.0.1:8011
wait
```

Expected output of step 7 (abridged):

```
[collector] ── poll 1 ──
[collector] got an application token (valid 300s)
[collector] fetched ssh credential for wardx_rot_demo@monetx-demo-device version_id=cv_4424… max_cache_seconds=300
[collector] device login OK as wardx_rot_demo with version_id=cv_4424…
[collector] ── poll 2 ──
[collector] cache hit: version_id=cv_4424… (still valid 259s)
[collector] device REJECTED cached version_id=cv_4424…: re-fetching once
[collector] fetched ssh credential … version_id=cv_f05f…
[collector] device login OK as wardx_rot_demo after re-fetch, version_id=cv_f05f…
```

Options: `--reveal` prints the credential masked (`--reveal --unmask` in full), `--stale-cache-once`
shows the re-fetch rule without a rotation, `--kind snmp|api|enable`, `--username`. Plain HTTP is
accepted only to a loopback address; otherwise use `https://` with `--ca-file`. The Application
identities page and each safe's "Application access" tab show the app and its fetches.

Clean up:

```bash
# stop the API (Ctrl+C), then:
docker rm -f wardx-lab-linux-demo && rm -f lab/.secrets/linux-demo
Backend/.venv/bin/python -c "import pgserver; pgserver.get_server('$DEMO/pg', cleanup_mode='stop')"
rm -rf $DEMO
```
