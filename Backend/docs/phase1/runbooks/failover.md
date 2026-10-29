# Runbook: in-site failover (HA_DR.md §2 to §5)

Scope: a single-tenant install with the recommended topology (two or more API nodes, two
gateway nodes, two scheduler nodes, PostgreSQL primary plus a synchronous standby in the same
site). Site loss is a different runbook: [dr-activation.md](dr-activation.md).

## 1. Configuration every node needs

| Setting | Value |
|---|---|
| `WARDX_DATABASE_URL` | multi-host with `target_session_attrs=read-write`, e.g. `postgresql+asyncpg://wardx:…@/wardx?host=db1:5432&host=db2:5432&target_session_attrs=read-write`, or a VIP / DNS name that follows the primary |
| `WARDX_VAULT_KEK` (+ `WARDX_VAULT_KEK_RETIRED`), `WARDX_JWT_SECRET` | identical on every node (deployment tooling, root-only files; never in the database or images). A node whose KEK cannot open the install's canary refuses to start (`KEK canary check failed`). |
| `WARDX_NODE_NAME` | unique per node (shown in `/health/cluster` and audit) |
| `WARDX_HA_EXPECT_SYNC_STANDBY=true` | raises the degraded-sync alert while no synchronous standby is attached |
| `WARDX_RECORDING_STORE=s3`, `WARDX_S3_*` | the shared object store (gateways write, API nodes replay) |
| Roles | API nodes `WARDX_APP_ROLE=api_only`; schedulers `scheduler`; gateways `gateway`. Never run two `api` (in-process scheduler) nodes in an HA profile. |

### The shared gateway host key

Users' SSH clients must see one host key whatever node they land on (§5):

```bash
ssh-keygen -t ed25519 -N '' -C wardx-gateway -f gateway_host_key   # once, on a secure host
ssh-keygen -lf gateway_host_key -E sha256                           # note SHA256:...
# Deploy the SAME private key file to every gateway node (root-only, 0600) and set:
#   WARDX_GATEWAY_HOST_KEY_FILE=/etc/wardx/gateway_host_key
#   WARDX_GATEWAY_HOST_KEY_FINGERPRINT=SHA256:...     (optional but recommended)
```

A gateway refuses to start when its key differs from the expected fingerprint or from any live
gateway node, and `/health/cluster` flags `gateway_host_keys_consistent: false`.

## 2. Database replication

**Patroni (recommended on-prem):**

```yaml
bootstrap:
  dcs:
    synchronous_mode: true
    synchronous_mode_strict: false      # never true: it blocks writes when the standby is gone
    maximum_lag_on_failover: 1048576    # do not promote a standby more than 1 MB behind
    postgresql:
      parameters:
        synchronous_commit: "on"
        wal_level: replica
```

Patroni keeps one synchronous standby while one is healthy and clears
`synchronous_standby_names` when none is, so writes continue asynchronously and WardX raises
the high **cluster.sync_degraded** alert until a synchronous standby is back (then the alert is
acknowledged by the system and the recovery audited). Do **not** run `lab/ha/sync-watchdog.sh`
with Patroni.

**Plain PostgreSQL without Patroni:** `synchronous_standby_names = 'ANY 1 (standby1)'` blocks
commits while the standby is down. Either run asynchronous (and accept the RPO), or use the
watchdog pattern of `lab/ha/sync-watchdog.sh` (it is lab tooling: review it before any use).

## 3. When the primary fails

Patroni promotes automatically. Manual installs:

1. Confirm the primary is really down (no split brain): it does not answer, and its host is
   fenced or powered off.
2. Promote the standby: `SELECT pg_promote(true, 60);` (or `pg_ctl promote -D $PGDATA`).
3. Point the VIP / DNS at it if you use one; multi-host URLs need nothing.
4. Watch `/api/v1/health/cluster` (admin): `replication.in_recovery: false`, the scheduler
   **leader** re-elected (new `term`, `fresh: true`), gateways fresh.
5. Expect the **cluster.sync_degraded** alert until a new standby streams: rebuild one from the
   new primary (`pg_basebackup -R -C -S <slot>`), then the alert clears.
6. Run `POST /api/v1/audit/verify`: the chain must verify.

What the application does: in-flight requests fail with 503 and clients retry; the pool
reconnects (`pool_pre_ping`) to the new primary; rotation jobs resume from their committed
state after their lease (no double rotation: the per-account lock and the recovery rules of
ROTATION.md §5); scheduled work resumes on the new leader.

## 4. When an application node fails

- **API node:** the load balancer's `/api/v1/health/ready` check drops it; tokens validate on
  every node. Nothing to do but replace the node.
- **Scheduler leader:** the standby takes the advisory lock within about 5 s (process death) or
  about 15 s plus 5 s (host or network loss; TCP keepalive). Leadership changes are audited
  (`scheduler.leader_elected`).
- **Gateway node:** live SSH sessions on it end (they cannot move). Within
  `WARDX_GATEWAY_LOST_SECONDS` (default 30 s) the leader marks them `terminated` /
  "Gateway node lost", closes the check-outs they opened (after-use rotation follows), and keeps
  the partial recording, encrypted and marked **incomplete**. Users reconnect and land on a
  healthy node, which presents the same host key. When the node comes back, it uploads any
  finished recordings left in its spool.

## 5. Checks after any failover

- `/api/v1/health/cluster`: leader fresh, sync state, gateways, no host key inconsistency.
- `POST /api/v1/audit/verify`: `ok: true`.
- Open high alerts on the dashboard: acknowledge the ones you have handled.
