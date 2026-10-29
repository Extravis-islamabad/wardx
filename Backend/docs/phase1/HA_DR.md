# Phase 1 (e) High availability and disaster recovery: spec (draft for review)

Status: **approved 2026-10-29, built 2026-10-29** (build log in §12; decisions in §9, with the product owner's changes to D3, D5
and D7; new sections §5.1 and §6.1). Scope: a **single-tenant** WardX install (multi-tenancy is deferred; `TENANCY_KEYS.md`
covers the per-tenant backup design for later). Windows and AD work stay out of scope.

## 1. What WardX is made of, and what each part keeps locally

| Role (`WARDX_APP_ROLE`) | State | HA property today |
|---|---|---|
| **API** (`api_only`) | None in process except caches: the user cache, unwrapped key cache, provider auth cache. Sessions are JWTs; rate counters live in Postgres. | Stateless. Any number of nodes behind a load balancer, **if** every node has the same JWT secret and KEK. |
| **Scheduler** (`scheduler`) | APScheduler jobs: expiry sweep, directory sync, rotation tick. | Each job already guards itself in the database: per-tick advisory locks, `FOR UPDATE SKIP LOCKED` job claims with leases, the per-account rotation lock and the directory-sync lock. So two schedulers are *safe* but *wasteful*, and there's no notion of a leader. |
| **Gateway** (`gateway`) | Live SSH sessions (long TCP connections) and recordings written to a **local directory** (`WARDX_RECORDING_DIR`). Kill requests and expiry are polled from the database. | New sessions can land on any node. A live session dies with its node. Recordings on a dead node's disk are unavailable, and the API serves replays from its own local directory. |
| **Database** (PostgreSQL) | Everything durable: inventory, sealed secrets, audit chain, wrapped tenant keys, rotation jobs, app identities. | Single instance today, so it's the single point of failure. |
| **Keys** | KEK (file or env), JWT secret, gateway SSH host key, the audit legacy boundary (dev only). | Per node. Must be **identical** on every node, and available at the DR site. |

## 2. Topology

**Recommended (§9 D1): an active-active application tier over an active-passive
database.**

```
              ┌── API node 1 ─┐          ┌── Gateway node 1 ─┐
 users / ───▶ LB ── API node 2 ─┤          │                   │◀── SSH (L4 LB / VIP)
 MonetX       └── API node N ─┘          └── Gateway node 2 ─┘
                     │   Scheduler A (leader)   Scheduler B (standby)
                     ▼            ▼                    ▼
              PostgreSQL primary ══sync══▶ standby (same site)
                     ╚═════async══════════▶ DR replica (DR site)
              Recordings: shared object store (S3-compatible), replicated to DR
```

- **API:** two or more nodes behind an HTTP load balancer, with no sticky sessions needed.
  Health checks use `/api/v1/health/ready`, which already fails closed when the vault is
  sealed.
- **Scheduler:** two nodes; exactly one is the **leader** and runs jobs (§4).
- **Gateway:** two or more nodes behind an L4 load balancer or VIP, sharing one SSH host key
  (§5).
- **Database:** primary plus a synchronous standby in the same site, plus an asynchronous
  replica at the DR site (§3).

Two simpler supported profiles, chosen at deployment:

| Profile | For | Shape |
|---|---|---|
| **Single node** | Labs and small installs | All roles on one host, one Postgres, backups only (§7). Recovery means restoring from backup. |
| **Single node + warm standby** | Small customers who want HA without a load balancer | Two hosts. Host B runs Postgres as a standby and the app roles stopped. Failover: promote, start the roles, move the VIP. Manual or scripted. |

## 3. Database replication and failover

- **PostgreSQL streaming replication.** Synchronous within the primary site
  (`synchronous_commit = on`, one synchronous standby), so a committed secret write, audit
  event or rotation step is never lost on a site-local failover (RPO 0, §9 D3). Asynchronous to
  the DR site.
- **Why synchronous matters here:** the rotation engine relies on "the candidate is
  committed before the device is touched" (`ROTATION.md` §5). An asynchronous failover could
  lose that commit after the device changed, and with it the only working password. In-site
  synchronous replication keeps the invariant across failover. At the DR site, the recovery
  table in `ROTATION.md` §5 still applies (verify C, then N), and the rotation runbook covers a
  DR activation (§6).
- **Failover tooling** (§9 D2):
  - WardX doesn't depend on any particular tool. It connects through a multi-host URL with
    `target_session_attrs=read-write` (asyncpg supports it), or a VIP or DNS name that points
    at the primary.
  - Recommended: **Patroni** (with etcd or Consul) on-prem, or the cloud's managed HA
    (RDS/Aurora Multi-AZ, Azure Flexible Server HA). A documented manual promotion runbook is
    included for small installs.
- **Connection behaviour on failover:** in-flight transactions fail and requests return 503.
  Background work resumes from its committed state (rotation jobs, leases, sweeps), and the
  pool reconnects with `pool_pre_ping`.
- **The audit chain** is written only on the primary, under its advisory lock. Replication
  carries it as-is; the HMAC key comes from the KEK on the app nodes, never from the database.
- **Replication lag and health:** exposed on a new admin-only `/api/v1/health/cluster`
  endpoint and as dashboard warnings (lag above threshold, no synchronous standby).
- **Degraded mode (D3):** if the synchronous standby is unavailable, the primary **falls back
  to asynchronous replication instead of blocking writes**. WardX raises a **high-severity
  alert** for as long as no synchronous standby is attached, and clears it when one returns.
  The check reads `pg_stat_replication` (`sync_state = 'sync'`) on the primary.
  - **Patroni:** `synchronous_mode: true` with `synchronous_mode_strict: false` (the default).
    Patroni keeps one synchronous standby while one is healthy. If none is, it clears
    `synchronous_standby_names`, so commits stop waiting and the primary keeps accepting
    writes. With `synchronous_mode_strict: true` the primary would block writes instead, so
    don't use it. `maximum_lag_on_failover` (for example 1 MB) stops Patroni promoting a
    standby that is too far behind.
  - **Plain PostgreSQL without Patroni:** `synchronous_standby_names = 'ANY 1 (standby1)'`
    blocks commits while the standby is down; there is no built-in fallback. Manual installs
    run asynchronous, or use the WardX watchdog in the HA lab
    (`lab/ha/sync-watchdog.sh`) that clears and restores `synchronous_standby_names`. It
    must never be enabled together with Patroni.

## 4. Scheduler leader election

- **A Postgres advisory lock held on a dedicated connection decides the leader** (§9 D4).
  - Every scheduler node tries `pg_try_advisory_lock(LEADER_KEY)` every 5 seconds.
  - The node holding it runs the jobs; the others run nothing.
  - The lock lives as long as the leader's connection. If the leader process or host dies, or
    its connection drops, Postgres releases the lock and a standby takes over on its next try
    (at most about 5 seconds plus TCP keepalive, tuned to about 15 seconds).
- **No second source of truth:** the same Postgres that holds the data decides the leader, so
  a scheduler that can't reach the primary can't be leader. That avoids a split brain between
  "who leads" and "where the data is".
- **Defence in depth stays:**
  - per-tick advisory locks;
  - lease-based `SKIP LOCKED` job claims;
  - the per-account rotation lock (`ROTATION.md` §14). Even a brief overlap during takeover,
    an old leader still finishing a tick, can't rotate one account twice.
- **On database failover:** the leader's connection drops with the old primary and leadership
  is re-elected on the new one. Rotation jobs resume from their committed states.
- **API-only nodes never run jobs**, which needs no change: `APP_ROLE=api` runs the scheduler
  in-process. In HA profiles API nodes run `api_only`. `api` is kept for single-node installs.
- **Visibility:** leader identity and the time of the last leader change are shown in
  `/health/cluster` and on the dashboard. Every leadership change is audited.

## 5. Session gateway failover

- **One gateway SSH host key, shared by every gateway node** (`WARDX_GATEWAY_HOST_KEY_FILE`,
  the same file on each node). Otherwise users' SSH clients would see a different host key
  after failover, which is exactly what they're trained to treat as an attack.
- **New sessions:** an L4 load balancer or VIP spreads them across healthy nodes. A node is
  healthy if its port 2222 answers and its database heartbeat is fresh.
- **Live sessions on a failed node can't be migrated** (an SSH connection can't move between
  hosts), §9 D6. They end.
  - Each gateway writes a **heartbeat** row (`node`, `last_seen`).
  - A scheduler job marks sessions whose node's heartbeat is older than a threshold as
    `terminated` with reason `gateway node lost`, and audits it.
  - Their check-outs are closed by the normal session-end path, so after-use rotation and
    exclusivity work as usual.
  - Users reconnect and land on a healthy node.
- **Recordings** (§9 D5, encrypted per §5.1):
  - Each node writes to a local spool, then **uploads to shared storage**: an S3-compatible
    object store such as MinIO on-prem or S3/Azure Blob in the cloud. That happens
    continuously in chunks during the session, and in full at session end.
  - The API serves replays from shared storage, so any API node can replay any session.
  - The SHA-256 over the recording is finalised at session end. A session cut off by a node
    loss keeps the chunks uploaded so far, marked **incomplete**: no final hash, and the replay
    UI says so.
  - Recordings are **encrypted before they leave the gateway** (§5.1); the object store only
    ever holds ciphertext.
- **Kill requests and check-out expiry** are already polled from the database, so they work
  from any node.

### 5.1 Recording encryption (pulled forward from `TENANCY_KEYS.md` §8)

- **Keys:**
  - Each recording gets a fresh 256-bit data key (DEK), wrapped by the tenant's **`files`**
    key (`KeyPurpose.FILES`, through `TenantKeyService` and the key provider).
  - The wrapped DEK, the files-key version and the format version go in a small header at the
    start of the encrypted object.
  - No code outside the key provider touches a key-encryption key
    (`tests/security/test_key_boundary.py`).
- **Format:** streaming AES-256-GCM in chunks of at most 64 KiB. Each chunk's nonce is derived
  from a per-recording random prefix and the chunk index. Its AAD carries the recording id,
  the chunk index and a final-chunk flag, so reordering, dropping, truncating or appending
  chunks fails to decrypt.
- **Integrity:**
  - `recording_sha256` stays the SHA-256 of the **plaintext** asciicast, hashed while it's
    written and recorded in the audit chain as today.
  - A second hash over the ciphertext object is stored for storage-level checks.
  - Replay decrypts while streaming, and refuses with a clear error on any authentication
    failure.
- **Incomplete recordings** (node lost): the chunks uploaded so far decrypt and replay up to
  the last complete chunk. With no final chunk the recording is marked **incomplete**, and
  that's what the UI shows. Nothing is presented as a full session.
- **Migrating existing recordings:** a resumable command (`wardx recordings encrypt`):
  1. Encrypt each plaintext recording into a new encrypted object.
  2. Decrypt it back and compare its SHA-256 with the stored `recording_sha256` before
     marking it migrated. A mismatch leaves the original untouched and reports it.
  3. **Originals are kept by default.** They're removed only by a separate, explicit
     `--remove-verified-originals` run, and only for recordings whose encrypted copy verified.
  4. Every step is audited per recording, with the session's safe.

## 6. Keys and secrets on every node and at the DR site

Every node of a role must have the **same**:

| Key | Needed by |
|---|---|
| KEK and retired KEKs (`WARDX_VAULT_KEK`, or the key provider) | API, scheduler, gateway |
| JWT secret | API (tokens validate on any node), gateway (gateway login) |
| Gateway SSH host key | Gateway |
| Provider app-token signing key (derived from the JWT secret) | API |

- **Delivery:** deployment tooling (Ansible, Kubernetes secrets, or the on-prem installer)
  writes them as root-only files. They're never in the database or in images.
- **Startup checks:** a node refuses to start if its KEK doesn't open a **known canary**, a
  small sealed value created at install. That catches a mismatched key before the node serves
  a single reveal.
- **The DR site** holds the same keys, delivered by the same tooling. On-prem with an HSM
  later: the HSM cluster spans both sites, or the DR site has its own HSM restored from the
  vendor backup (`TENANCY_KEYS.md` §8.2).
- **Losing the KEK means losing every secret.** Hence the M-of-N escrow in
  `TENANCY_KEYS.md` §8.2, which applies to single-tenant installs too. The DR runbook checks
  escrow before any DR test.
- **DR activation is a human decision** (§9 D8). The runbook:
  1. Confirm the primary site is really lost (no split brain).
  2. Promote the DR replica.
  3. Start the roles at the DR site.
  4. Point DNS or the VIP at it.
  5. Run the post-failover checks: chain verify, canary decrypt, a sample verify of rotation
     jobs that were in flight.

### 6.1 Rotation safety around the site-loss data-loss window (D7)

With asynchronous replication to the DR site, a site loss can lose up to the replication lag
of committed data. That includes rotation commits, so a rotated device could end up holding a
password the DR copy of the vault doesn't know about.

- **DR is an explicit setting:** `dr_site_configured` (`WARDX_DR_SITE_CONFIGURED`, default
  **false**). (Product owner, 2026-10-29: this replaces the earlier "if no DR replica is
  configured, nothing pauses".)
  - **false** (single-site installs): the DR-lag pause does not apply, scheduled rotation runs
    normally, on-demand rotation carries no `dr_lag_warning`, and no security alert is raised.
    The dashboard shows "No DR site configured" as an informational item, and
    `/health/cluster` reports `dr_site_configured: false`.
  - **true:** the rules below apply.
- **Pause on lag** (DR site configured):
  - While the DR replica's replay lag exceeds `WARDX_DR_MAX_LAG_SECONDS` (default **60**),
    the scheduler **pauses scheduled rotations**: it queues none, and jobs already queued wait
    in `pending`. It raises a high-severity alert, cleared when the lag recovers.
  - Lag is read on the primary from `pg_stat_replication` for the replica named in
    `WARDX_DR_REPLICA_NAME`.
  - An **unreadable** lag pauses too, with the alert (fail safe): the replica is not in
    `pg_stat_replication`, the query fails, or `WARDX_DR_REPLICA_NAME` is not set.
- **On-demand rotation** is still allowed while the lag is high or unreadable, but the API
  returns a `dr_lag_warning` alongside the job and the console shows it before confirming.
- **DR activation runbook step** (`wardx dr post-failover-check`):
  1. **List every account rotated in the possible loss window** (from
     `--since <time of last confirmed replication>` to failover). It uses the promoted
     database's audit trail **and**, if given, the forwarded audit or SIEM export
     (`--audit-export <file>`, JSON lines of WardX audit events). The export catches
     rotations the DR copy never received.
  2. **Run verify immediately** on each listed account (normal verify jobs, negative check
     included).
  3. **Reconcile every account whose verify fails**, through its reconcile account. Accounts
     without one are listed for manual action and flagged out of sync.
  4. Print a report and audit the whole run. `--dry-run` lists without queueing anything.

## 7. Backup and restore (single tenant)

- **What's backed up:**
  - the database, as continuous WAL archiving plus a nightly base backup, so it can be
    restored to any point in time (PITR);
  - recordings, through object-store versioning and replication;
  - configuration, without keys.

  Keys are backed up **separately** through escrow (§6), never in the same archive as data.
- **Encryption:** backup archives are encrypted (AES-256-GCM streaming, or the object store's
  server-side encryption with a customer-managed key). Sealed secrets inside the database
  stay sealed either way, but the database also holds inventory and audit data.
- **Retention:** 35 days by default, configurable. It matches the tenancy design's default.
- **Restore** (to a new database, never over a live one):
  1. Restore the base backup and replay WAL to the chosen time.
  2. Start one API node with the escrowed keys.
  3. The startup canary check passes.
  4. Run `POST /audit/verify`: the chain must verify up to the restore point.
  5. Sample-decrypt N secrets.
  6. Run verify jobs (no rotation) on a sample of accounts to see which device passwords
     drifted after the backup. Accounts rotated after the restore point are **out of sync**
     by definition and need reconcile; the runbook lists them from `last_rotated_at`.
  7. Switch traffic.
- **Restore drills:** a scripted restore into a scratch database, quarterly, with the result
  recorded and shown on the dashboard.

## 8. Testing

- **HA lab** (`lab/ha/`, opt-in under `WARDX_LAB=ha`, never in a plain test run): Docker
  Compose with 2 API, 2 scheduler and 2 gateway nodes, Postgres primary plus synchronous
  standby (Patroni or a scripted promote), and MinIO for recordings.
- **Scenarios:**
  - kill the scheduler leader mid-rotation: the standby takes over, the job resumes, and the
    account is never rotated twice;
  - kill a gateway node with a live session: the session is marked terminated with "node
    lost", its check-out is closed, the recording is kept as incomplete, and a reconnect lands
    on the other node with the same host key;
  - promote the database standby during writes: no committed secret or audit event lost, and
    the chain verifies;
  - start an API node with the wrong KEK: it refuses to start (canary);
  - restore from backup to a point in time: the chain verifies and accounts rotated after
    that point are listed for reconcile.
- **Unit and integration (plain pytest):** leader election with two in-process schedulers on
  the test database, the heartbeat sweeper, the canary check, the recording upload and replay
  path against a local fake object store.

## 9. Decisions (answered 2026-10-29; D1, D2, D4, D6, D8, D9, D10 as recommended)

1. **D1. Topology.**
   - Options: (a) active-active app tier with active-passive DB; (b) everything
     active-passive; (c) multi-primary DB.
   - **Recommend (a).** The app tier is already stateless or self-coordinating, and a
     multi-primary database would break the audit chain's single-writer order and the
     rotation commit ordering. (b) stays available as the "single node + warm standby"
     profile.
2. **D2. Database failover tooling.**
   - Options: (a) tool-agnostic WardX, recommending Patroni on-prem and managed HA in cloud,
     plus a manual runbook; (b) bundle Patroni in the on-prem installer; (c) manual only.
   - **Recommend (a) now, (b) later for the packaged appliance.**
3. **D3. Replication mode.** **Decided:** synchronous within the primary site and
   asynchronous to the DR site. **Changed by the owner:** if the synchronous standby is
   unavailable, the primary falls back to asynchronous instead of blocking writes, with a
   high-severity alert while degraded (§3).
4. **D4. Scheduler leader election.**
   - Options: (a) a Postgres advisory lock on a dedicated connection; (b) an external
     coordinator (etcd, Consul, Kubernetes lease).
   - **Recommend (a).** No new dependency, and the leader is always the node that can reach
     the primary.
5. **D5. Recordings storage.**
   - Options: (a) S3-compatible object store with local spool and chunked upload; (b) shared
     NFS; (c) local disk per node plus rsync.
   - **Decided (a).** **Changed by the owner:** recordings are encrypted before upload,
     pulled forward into this module, and existing recordings are migrated with originals
     kept until the encrypted copies verify (§5.1).
6. **D6. Live gateway sessions when a node is lost.**
   - **Recommend: end them, audited as "gateway node lost", close their check-outs, keep the
     partial recording marked incomplete.** SSH sessions can't be migrated.
7. **D7. Targets.** **Decided:** RTO 5 minutes or less and RPO 0 in-site (automatic); RTO 1
   hour or less and RPO 5 minutes or less for a site loss (manual DR activation). **Added by
   the owner:** the rotation-safety rule in §6.1 (pause scheduled rotation on DR lag, warn on
   on-demand, and a post-failover verify and reconcile command).
8. **D8. DR activation.**
   - **Recommend manual, by runbook, with a named decision-maker.** Automatic cross-site
     failover risks a split brain for a vault, where two primaries could each rotate the same
     device.
9. **D9. Backups.**
   - **Recommend: continuous WAL archiving plus a nightly base backup, encrypted, 35-day
     retention, keys only in escrow, quarterly restore drills shown on the dashboard.**
10. **D10. Node key mismatch.**
    - **Recommend: a node refuses to start if its KEK can't open the install's canary.** It's
      better to fail at deploy time than to serve "secret could not be decrypted" to users.

## 10. Build stop

Stop for review when failover works end to end in a local test setup: primary plus standby
database, two API nodes, two gateway nodes. That includes a **killed-primary test** and a
**killed-gateway test** (§8).

## 11. Effort (one engineer)

| Part | Days |
|---|---|
| Leader election, `/health/cluster`, dashboard items | 2 |
| Gateway heartbeat, lost-node sweeper, shared host key checks | 2 |
| Recordings to object storage (spool, chunked upload, replay from storage, incomplete marking) | 3–4 |
| Recording encryption (streaming GCM, files key) and the migration command | 2–3 |
| Degraded-sync alert, DR-lag rotation pause and warning, `dr post-failover-check` | 2–3 |
| KEK canary and startup checks | 1 |
| Backup and restore tooling and runbooks (PITR, restore verification, drill script) | 2–3 |
| HA lab (compose) and failover scenario tests | 3 |
| **Total** | **17–21** |

## 12. Build log (smaller choices, logged rather than asked)

Built 2026-10-29. Runbooks: [runbooks/failover.md](runbooks/failover.md),
[runbooks/dr-activation.md](runbooks/dr-activation.md),
[runbooks/backup-restore.md](runbooks/backup-restore.md). HA lab: `lab/ha/README.md`.
Migrations 022 to 026. Where a choice was open, the more restrictive one was taken.

**Scheduler leader (§4)**
1. The lock is held on a connection from its own engine (`NullPool`), separate from the
   request pool. Keepalive is tuned server side through asyncpg `server_settings`
   (`tcp_keepalives_idle=5`, `interval=5`, `count=2`), so PostgreSQL frees a vanished leader's
   lock in about 15 s.
2. On every tick the leader re-checks, within the interval, that its connection is alive and
   still holds the lock (`pg_locks`), and stamps `last_seen`. Any error or timeout makes it step
   down before the server could hand the lock to another node. Jobs are wrapped in
   `leader_only`; the per-tick, lease and per-account locks stay.
3. `ha.scheduler_leader` is a display row (node, term, elected_at, last_seen); the lock decides.
   `scheduler.leader_elected` (with the previous node and term) and `scheduler.leader_released`
   (clean shutdown) are audited. "Fresh" = last_seen within max(3 × interval, 15 s).
4. `APP_ROLE=api` (single node) also elects, so `/health/cluster` always names a leader.
   `build_scheduler()` without an elector keeps running every job (tests, tools).
5. `/health/cluster` is gated by a new admin-only codename `cluster.view`.

**Degraded synchronous replication (§3)**
6. Expected only with `WARDX_HA_EXPECT_SYNC_STANDBY=true` (default false, so single-node
   installs never alert). `sync_state` `sync` or `quorum` (the `ANY 1 (...)` form) with
   `state = 'streaming'` counts as synchronous.
7. "Cleared on recovery" = the system acknowledges the open alert (`acknowledged_by` NULL) and
   audits `cluster.sync_restored`. The append-only alert trigger is unchanged. Each condition
   (`ha.conditions`) has a stable object id (uuid5), so its alerts are found again; a condition
   that stays active raises one alert, not one per check.

**Gateways (§5)**
8. Heartbeat every 5 s, lost after 30 s (defaults). A session on a node that never registered
   counts as lost once it is older than the threshold.
9. The sweep is idempotent: a session is ended (and audited) only while still `active`; a
   cut-off node that finishes late no longer writes a second `session.end`.
10. A restarted node's own orphans now go through the same path (`failed` / "Gateway
    restarted"), with recording salvage, and **their check-outs are closed** at once through
    the normal check-in (before: left to expiry). Sessions record `owns_checkout` (023).
11. Shared host key: a node refuses to start (before listening) if its key differs from a live
    node's or from the optional `WARDX_GATEWAY_HOST_KEY_FINGERPRINT`. How to deploy one key:
    failover runbook §1.

**Recordings (§5, §5.1)**
12. Plaintext never touches disk: the local spool holds ciphertext. A partial chunk is sealed
    every `WARDX_RECORDING_FLUSH_SECONDS` (5 s), so chunks are at most 64 KiB, not always
    64 KiB, and a lost node loses at most that much output.
13. Objects: `spool/<session>/header` and `spool/<session>/<index>` while live,
    `recordings/<session>.wxrec` when finished (chunk objects then removed). For a lost node,
    the sweep joins the header and the contiguous uploaded chunks into the final object, marked
    incomplete. A final upload that fails stays in the spool and is uploaded when the node starts
    again.
14. Chunk AAD also binds the SHA-256 of the header, so a header edit fails every chunk. The
    AES-GCM calls live in `vault/envelope.py` (data keys only); the key boundary test's allowlist
    is unchanged. The DEK is wrapped by the `files` key from `TenantKeyService`.
15. A session whose recording cannot be opened (store or key unavailable) fails before any
    target contact: no recording, no session.
16. Replay decrypts the whole object before answering, so an authentication failure is a clean
    409 (`recording_integrity_failed`) and never half a stream. A recording recorded as finished
    but missing its final chunk is refused as truncated. Legacy plaintext recordings still replay
    until migrated.
17. S3 client: `minio==7.2.20` (MinIO's Python SDK, pinned), calls in worker threads; the bucket
    is created on first use. Local-filesystem store with the same interface for single-node
    installs and the plain tests.
18. The package is `src/services/session_recordings/`: `recordings/` is ignored by
    `Backend/.gitignore` (the local recording directory), and the ignore rule was left as is.

**`wardx recordings encrypt`**
19. Verification reads the object back from the store before decrypting and comparing with
    `recording_sha256`. A mismatch also deletes the unverified copy. A recording with no stored
    hash cannot be verified, so it is left as is and reported. `--remove-verified-originals`
    re-verifies each copy right before deleting the original and then clears `recording_path`.
    Audited: `session.recording_encrypted`, `session.recording_encrypt_failed`,
    `session.recording_original_removed`, `session.recording_original_remove_failed`.
20. The `wardx` CLI is `python -m src.cli` (wrapper `Backend/wardx`) and starts like a node
    (migrations, KEK canary); `backup` commands load only the key provider.

**KEK canary (§6, D10)**
21. A random 32-byte value wrapped by the key provider (`keystore.kek_canary`, 025), checked
    after migrations on every start. On an existing install the canary is created only after the
    node's KEK has opened the existing tenant keys, so a wrong-KEK node can never create it.
    After a KEK rotation it is re-wrapped under the active KEK while the retired one is loaded.

**DR lag (§6.1, with the owner's explicit `dr_site_configured`)**
22. Paused while the lag is high or unreadable: scheduled **and after-use** rotations (both
    automatic). Verifies are still queued; on-demand rotate, reconcile and compromise run with
    the warning; jobs already past `pending` resume (finishing a half-done rotation is safer).
23. The lag is read fresh at every rotation tick (and by the cluster check); a check that throws
    pauses. `replay_lag` NULL with zero bytes behind and `streaming` counts as 0 s (PostgreSQL
    clears it when idle); NULL while behind is unreadable.
24. `dr_lag_warning` is also on `GET /accounts/{id}/rotation`, which the console reads to show
    the warning before confirming; the request's audit event records `dr_lag_warning: true`.

**`wardx dr post-failover-check`**
25. The window includes any non-verify rotation activity (audited `rotation.*` events, jobs
    started, finished or still open), not only successes: over-listing costs a verify,
    under-listing could hide a device holding an unknown password.
26. It waits for its verify jobs (`--wait-seconds`, default 900) run by the scheduler leader,
    then reconciles failures or flags them out of sync; exit code 1 when anything needs a person.

**Backup and restore (§7)**
27. Archive DEKs are wrapped by the **KEK** through the key provider, not by the `backup` tenant
    key: that key lives inside the database being restored. Archive format mirrors recordings
    (`WXBAK`, 64 KiB chunks, AAD with name, index, final flag, header hash).
28. The drill restores a **logical** dump into the scratch database (fast, no second cluster);
    base backups are physical (`pg_basebackup` tar) and the WAL scripts are the PITR hooks.
    Base backups are written as `.part` and renamed only when complete.

**HA lab (§8)**
29. App nodes are host processes from `Backend/.venv` (fast restarts, a SIGKILL is a real
    process death), in production mode with explicit keys from `lab/.secrets/ha`, each in its own
    `lab/ha/.run/<node>` directory (no `.env`, no dev state).
30. Plain PostgreSQL 17.6 with a scripted promote (`pg_promote`) and the lab sync watchdog; no
    Patroni in the lab. MinIO image `pgsty/minio:RELEASE.2026-08-04T00-00-00Z` (pinned): the
    upstream `minio/minio` and `quay.io/minio/minio` images could not be pulled here.
31. Lab timings: heartbeat 2 s, lost after 10 s, leader interval 2 s, rotation lease 15 s,
    recording flush 1 s.

**Differences from the spec and limitations**
- §8 "restore to a point in time" is covered by the WAL hooks and the runbook; the lab drill
  restores a logical dump, and PITR replay itself is not exercised automatically.
- The DR lag rules are tested with a patched lag source (plain tests); the lab has no DR replica.
- Replay holds one decrypted recording in memory per request.
- Patroni is documented, not bundled (D2 a).
