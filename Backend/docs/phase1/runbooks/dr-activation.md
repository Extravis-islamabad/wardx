# Runbook: DR activation after a site loss (HA_DR.md §6, §6.1, D8)

**DR activation is a human decision** with a named decision-maker. Automatic cross-site
failover risks a split brain for a vault (two primaries rotating the same device).

## Before any DR test or activation

- The DR site holds the same keys (KEK and retired KEKs, JWT secret, gateway host key),
  delivered by the same tooling. Check the KEK **escrow** (TENANCY_KEYS.md §8.2) is current.
- `WARDX_DR_SITE_CONFIGURED=true`, `WARDX_DR_REPLICA_NAME=<application_name of the DR
  replica>`, `WARDX_DR_MAX_LAG_SECONDS=60` on the primary site. While the DR replica's replay
  lag is over the limit, or unreadable, **scheduled rotations pause** (high alert
  `cluster.dr_lag_high`), and on-demand rotations carry a `dr_lag_warning`. Without a DR site
  (`false`), nothing pauses and the dashboard shows "No DR site configured".

## Activation

1. **Confirm the primary site is really lost** (no split brain). Fence it: it must not come
   back as a primary.
2. **Note the time of the last confirmed replication** (`T_since`): from monitoring, the last
   `pg_stat_replication` sample for the DR replica, or the DR replica's
   `pg_last_xact_replay_timestamp()`. When unsure, take an earlier time: the check only lists
   more accounts.
3. **Promote the DR replica:** `SELECT pg_promote(true, 60);`
4. **Start the roles at the DR site** (API, scheduler, gateway) with the escrowed keys. Every
   node checks the KEK canary at start; a node with the wrong KEK refuses to start.
5. **Point DNS or the VIP** at the DR site.
6. **Run the post-failover check** on one DR node (it uses that node's configuration):

   ```bash
   cd /opt/wardx/Backend
   ./wardx dr post-failover-check --since 2026-10-29T10:42:00+00:00 \
       --audit-export /secure/siem-export-wardx.jsonl --dry-run      # list only
   ./wardx dr post-failover-check --since 2026-10-29T10:42:00+00:00 \
       --audit-export /secure/siem-export-wardx.jsonl                # verify + reconcile
   ```

   - It lists every account with rotation activity from `--since` to now (`--until` to set
     the failover time), from the promoted database's audit trail and rotation jobs **and** the
     forwarded audit / SIEM export (JSON lines of WardX audit events), which catches rotations
     the DR copy never received. Accounts only in the export are marked `UNKNOWN HERE`.
   - It queues a normal **verify** on each (negative check included) and waits for the
     scheduler leader to run them (`--wait-seconds`, default 900; rotation must be enabled).
   - Each failed verify gets a **reconcile** through its reconcile account; accounts without
     one are flagged **out of sync** and listed for manual action.
   - It prints a report and audits the whole run (`dr.post_failover_check`). Exit code 1 means
     something needs a person.
7. **Run the other post-failover checks:** `POST /api/v1/audit/verify` (chain verify), the
   canary was checked at start, and review `/api/v1/health/cluster`.
8. **Rebuild replication** from the new primary (a new in-site standby, a new DR replica) and
   watch the degraded-sync and DR-lag alerts clear.
