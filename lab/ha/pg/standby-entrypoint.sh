#!/bin/sh
# Streaming standby: clone the primary once (pg_basebackup with a physical slot), then run
# as a hot standby that reports itself as "wardx_standby" (the synchronous standby name).
set -eu
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  mkdir -p "$PGDATA" && chown postgres:postgres "$PGDATA" && chmod 700 "$PGDATA"
  export PGPASSWORD="$WARDX_LAB_REPL_PASSWORD"
  until gosu postgres pg_basebackup -h wardx-lab-ha-pg1 -U replicator -D "$PGDATA" \
      -X stream -R -C -S wardx_standby \
      -d "host=wardx-lab-ha-pg1 user=replicator application_name=wardx_standby"; do
    rm -rf "${PGDATA:?}"/* ; sleep 1
  done
  unset PGPASSWORD
fi
exec gosu postgres postgres -c hot_standby=on -c hot_standby_feedback=on
