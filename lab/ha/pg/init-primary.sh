#!/bin/sh
# Runs once, at the primary's initdb: the replication role and its pg_hba entry.
# The password comes from the container environment (WARDX_LAB_REPL_PASSWORD).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v repl_pw="$WARDX_LAB_REPL_PASSWORD" <<'SQL'
CREATE ROLE replicator WITH REPLICATION LOGIN PASSWORD :'repl_pw';
SQL
echo "host replication replicator all scram-sha-256" >> "$PGDATA/pg_hba.conf"
