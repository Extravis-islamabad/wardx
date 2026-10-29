# Runbook: backup and restore (HA_DR.md §7)

## What is backed up, and where the keys are

- **Database:** continuous WAL archiving plus a nightly base backup, for point-in-time
  recovery. Both are encrypted on the way out (`wardx backup encrypt`: streaming AES-256-GCM,
  a fresh data key per archive wrapped by the KEK). Default retention 35 days.
- **Recordings:** already encrypted in the object store (§5.1); use the store's versioning
  and replication (MinIO site replication, S3 versioning + cross-region replication).
- **Configuration:** the WARDX_* settings **without keys**.
- **Keys:** never in a backup. The KEK (and retired KEKs) are escrowed (TENANCY_KEYS.md §8.2);
  a restore needs only the escrowed KEK, never the database being restored.

## Set up (on the database host)

Scripts: `scripts/backup/` (they run `wardx` from `WARDX_BACKEND`, with that node's
`WARDX_VAULT_KEK`).

```ini
# postgresql.conf
archive_mode = on
archive_command = 'WARDX_BACKEND=/opt/wardx/Backend WARDX_WAL_ARCHIVE_DIR=/backup/wal /opt/wardx/scripts/backup/wal-archive.sh %p %f'
```

```cron
# nightly base backup, keeps 35 days of its own files
15 2 * * * WARDX_BACKEND=/opt/wardx/Backend WARDX_BACKUP_DIR=/backup/base PGUSER=replicator /opt/wardx/scripts/backup/base-backup.sh
```

Copy `/backup` off the host (object store with object lock, or a backup system); it holds
only ciphertext. Prune the WAL archive older than the oldest base backup you keep.

## Restore (to a new database, never over a live one)

1. Decrypt the base backup and extract it into an empty data directory:
   `wardx backup decrypt --in wardx-base-<time>.tar.wxbak | tar -x -C $PGDATA`
2. Point-in-time recovery:
   ```ini
   restore_command = 'WARDX_BACKEND=/opt/wardx/Backend WARDX_WAL_ARCHIVE_DIR=/backup/wal /opt/wardx/scripts/backup/wal-restore.sh %f %p'
   recovery_target_time = '2026-10-29 12:00:00+00'
   recovery_target_action = 'promote'
   ```
   `touch $PGDATA/recovery.signal`, start PostgreSQL, wait for promotion.
3. Start **one** API node with the escrowed keys. The **KEK canary** check passes or the node
   refuses to start.
4. Verify the restored database (it checks the chain, sample-decrypts secrets and lists the
   accounts rotated after the restore point):
   ```bash
   WARDX_DATABASE_URL=<restored db> ./wardx restore verify \
       --restore-point 2026-10-29T12:00:00+00:00 --sample 50 --json /tmp/restore.json
   ```
5. Accounts listed under `rotated_after_restore_point` are **out of sync by definition**: their
   devices hold a newer password. Reconcile them (or run `wardx dr post-failover-check
   --since <restore point>`), and queue verify jobs on a sample of the rest.
6. Switch traffic.

## Restore drills (quarterly)

`scripts/backup/restore-drill.sh` restores into a scratch database `wardx_drill_<time>`,
runs `wardx restore verify` against it, records the result on the production database
(`wardx restore record-drill`, audited `backup.restore_drill`) and drops the scratch database.
The dashboard's Cluster panel shows the latest drill.

```bash
WARDX_BACKEND=/opt/wardx/Backend \
WARDX_DRILL_DB_URL_TEMPLATE='postgresql+asyncpg://wardx:…@db1:5432/{db}' \
PGHOST=db1 PGUSER=wardx \
/opt/wardx/scripts/backup/restore-drill.sh
```

The drill restores a logical dump (fast, no second cluster). Restoring a physical base backup
with PITR follows the steps above; rehearse it on a scratch host at least once a year.
