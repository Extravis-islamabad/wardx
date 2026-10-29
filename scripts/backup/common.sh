# Shared settings for the WardX backup scripts (HA_DR.md §7). Sourced, not run.
#   WARDX_BACKEND          WardX Backend/ directory (its .venv runs `wardx`)
#   WARDX_BACKUP_DIR       where encrypted base backups go (one install's dir only)
#   WARDX_WAL_ARCHIVE_DIR  where encrypted WAL segments go
#   WARDX_BACKUP_RETENTION_DAYS  default 35
#   PG_EXEC                optional prefix to run PostgreSQL tools, e.g.
#                          "docker exec -i wardx-lab-ha-pg1 gosu postgres" in the HA lab
# The KEK comes from the node's own configuration (WARDX_VAULT_KEK); archives never
# contain keys, and keys are never written next to archives (escrow, §6).
set -eu
# A failed producer in a pipeline must fail the script (dash and bash both support it).
set -o pipefail 2>/dev/null || true
: "${WARDX_BACKEND:?set WARDX_BACKEND to the WardX Backend directory}"
WARDX="$WARDX_BACKEND/.venv/bin/python -m src.cli"
RETENTION_DAYS=${WARDX_BACKUP_RETENTION_DAYS:-35}
PG_EXEC=${PG_EXEC:-}
wardx() { (cd "$WARDX_BACKEND" && $WARDX "$@"); }
