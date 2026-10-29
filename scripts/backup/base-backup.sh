#!/bin/sh
# Nightly base backup (HA_DR.md §7): pg_basebackup as a tar stream, encrypted on the way
# out (AES-256-GCM, DEK wrapped by the KEK), then old base backups past retention removed.
# Point-in-time recovery = this base backup + the WAL archive (wal-archive.sh).
#   PGHOST/PGPORT/PGUSER (replication role) and PGPASSWORD (or .pgpass) select the server.
. "$(dirname "$0")/common.sh"
: "${WARDX_BACKUP_DIR:?set WARDX_BACKUP_DIR}"
umask 077
mkdir -p "$WARDX_BACKUP_DIR"
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="wardx-base-$stamp.tar"
out="$WARDX_BACKUP_DIR/$name.wxbak"
trap 'rm -f "$out.part"' EXIT
$PG_EXEC pg_basebackup -D - -Ft -X fetch --checkpoint=fast --label "$name" \
  | wardx backup encrypt --name "$name" --out "$out.part"
mv "$out.part" "$out"   # only a complete archive gets the final name
echo "base backup: $out"
# Retention: only this script's own files, by name.
find "$WARDX_BACKUP_DIR" -maxdepth 1 -type f -name 'wardx-base-*.tar.wxbak' \
  -mtime +"$RETENTION_DAYS" -print -exec rm -f {} \;
