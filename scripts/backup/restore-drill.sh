#!/bin/sh
# Scripted restore drill into a SCRATCH database (HA_DR.md §7), never over a live one:
#   1. dump the source database and encrypt the dump (as a backup would be stored);
#   2. decrypt it and restore it into a new scratch database wardx_drill_<time>;
#   3. start WardX against the scratch database (KEK canary), verify the audit chain,
#      sample-decrypt secrets, list accounts rotated after the restore point;
#   4. record the result on the source database (shown on the dashboard), drop the scratch.
# Environment: the source node's WARDX_* configuration (WARDX_DATABASE_URL, WARDX_VAULT_KEK,
# ...), PGUSER/PGPASSWORD for the PostgreSQL tools, PG_EXEC as in common.sh, and
# WARDX_DRILL_DB_URL_TEMPLATE: the WardX database URL with {db} in place of the database name.
. "$(dirname "$0")/common.sh"
: "${WARDX_DRILL_DB_URL_TEMPLATE:?set WARDX_DRILL_DB_URL_TEMPLATE (with {db})}"
SOURCE_DB=${WARDX_DRILL_SOURCE_DB:-wardx}
SAMPLE=${WARDX_DRILL_SAMPLE:-20}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
umask 077
point=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
scratch="wardx_drill_$(date -u +%Y%m%d%H%M%S)"

$PG_EXEC pg_dump -Fc -d "$SOURCE_DB" | wardx backup encrypt --name "drill-$scratch" --out "$work/dump.wxbak"
wardx backup decrypt --in "$work/dump.wxbak" --out "$work/dump.pgc"
$PG_EXEC createdb "$scratch"
cleanup() { $PG_EXEC dropdb --if-exists "$scratch" >/dev/null 2>&1 || true; rm -rf "$work"; }
trap cleanup EXIT
$PG_EXEC pg_restore --no-owner -d "$scratch" < "$work/dump.pgc"

scratch_url=$(printf '%s' "$WARDX_DRILL_DB_URL_TEMPLATE" | sed "s/{db}/$scratch/")
status=0
(cd "$WARDX_BACKEND" && WARDX_DATABASE_URL="$scratch_url" $WARDX restore verify \
   --restore-point "$point" --sample "$SAMPLE" --json "$work/result.json") >/dev/null || status=$?
[ -s "$work/result.json" ] || printf '{"ok": false, "error": "restore verify did not complete (exit %s)"}' "$status" > "$work/result.json"
wardx restore record-drill --result "$work/result.json"
exit $status
