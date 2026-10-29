#!/bin/sh
# HA LAB ONLY (HA_DR.md §3, plain PostgreSQL without Patroni). NEVER run with Patroni.
#
# Keeps the primary synchronous while its standby streams, and falls back to asynchronous
# (instead of blocking every commit) while it does not:
#   standby streaming and synchronous_standby_names empty  -> set 'ANY 1 (<standby>)'
#   standby not streaming and synchronous_standby_names set -> clear it
# WardX's degraded-sync alert fires while the primary runs without a synchronous standby.
#   sh lab/ha/sync-watchdog.sh <primary container> <standby application_name>
set -u
PRIMARY=${1:-wardx-lab-ha-pg1}
STANDBY=${2:-wardx_standby}
psql_primary() { docker exec -u postgres "$PRIMARY" psql -U wardx -d wardx -qAt -c "$1" 2>/dev/null; }
while true; do
  streaming=$(psql_primary "SELECT count(*) FROM pg_stat_replication WHERE application_name = '$STANDBY' AND state = 'streaming'")
  current=$(psql_primary "SELECT current_setting('synchronous_standby_names')")
  if [ -n "$streaming" ]; then
    if [ "$streaming" -gt 0 ] && [ -z "$current" ]; then
      psql_primary "ALTER SYSTEM SET synchronous_standby_names = 'ANY 1 ($STANDBY)'" >/dev/null
      psql_primary "SELECT pg_reload_conf()" >/dev/null
      echo "$(date -u +%FT%TZ) synchronous: standby $STANDBY streaming"
    elif [ "$streaming" -eq 0 ] && [ -n "$current" ]; then
      psql_primary "ALTER SYSTEM SET synchronous_standby_names = ''" >/dev/null
      psql_primary "SELECT pg_reload_conf()" >/dev/null
      echo "$(date -u +%FT%TZ) DEGRADED: standby $STANDBY not streaming; asynchronous"
    fi
  fi
  sleep 2
done
