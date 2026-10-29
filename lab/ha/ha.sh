#!/bin/sh
# WardX HA lab (Backend/docs/phase1/HA_DR.md §8). Lab only: touches ONLY the containers,
# network and volumes named wardx-lab-ha-* (plus the wardx-lab-linux-ha target), on
# 127.0.0.1 ports 15432-15433 (Postgres), 19000-19001 (MinIO) and 2242 (Linux target).
# Never prunes; never stops anything else.
#   sh lab/ha/ha.sh secrets|up|status|promote|watchdog-start|watchdog-stop|down
set -eu
HA=$(cd "$(dirname "$0")" && pwd)
LAB=$(dirname "$HA")
SECRETS="$LAB/.secrets/ha"
RUN="$HA/.run"
PG_IMAGE=postgres:17.6-alpine
MINIO_IMAGE=pgsty/minio:RELEASE.2026-08-04T00-00-00Z
LINUX_IMAGE=wardx-lab/linux-ssh:1
NET=wardx-lab-ha-net

secret() { # name nbytes: create once (0600), never print
  f="$SECRETS/$1"
  if [ ! -s "$f" ]; then
    (umask 077; python3 -c "import secrets,sys; print(secrets.token_urlsafe(int(sys.argv[1])))" "$2" > "$f")
  fi
}

secrets() {
  mkdir -p "$SECRETS" && chmod 700 "$SECRETS"
  secret pg-password 24; secret repl-password 24; secret minio-password 24
  secret jwt-secret 48; secret admin-password 18; secret user-password 18
  secret target-password 18
  for k in kek kek-wrong; do
    [ -s "$SECRETS/$k" ] || (umask 077; python3 -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())" > "$SECRETS/$k")
  done
  [ -s "$SECRETS/gateway-host-key" ] || (umask 077; ssh-keygen -q -t ed25519 -N '' -C wardx-lab-ha-gateway -f "$SECRETS/gateway-host-key" && rm -f "$SECRETS/gateway-host-key.pub")
  chmod 600 "$SECRETS"/*
}

wait_pg() { # container
  i=0; until docker exec "$1" pg_isready -U wardx -d wardx -q 2>/dev/null; do
    i=$((i+1)); [ $i -lt 120 ] || { echo "$1 not ready" >&2; exit 1; }; sleep 1; done
}

up() {
  secrets
  mkdir -p "$RUN"
  docker network inspect $NET >/dev/null 2>&1 || docker network create $NET >/dev/null
  if ! docker container inspect wardx-lab-ha-pg1 >/dev/null 2>&1; then
    POSTGRES_PASSWORD=$(cat "$SECRETS/pg-password") WARDX_LAB_REPL_PASSWORD=$(cat "$SECRETS/repl-password") \
    docker run -d --name wardx-lab-ha-pg1 --network $NET -p 127.0.0.1:15432:5432 \
      -v wardx-lab-ha-pg1:/var/lib/postgresql/data \
      -v "$HA/pg/init-primary.sh:/docker-entrypoint-initdb.d/10-replication.sh:ro" \
      -e POSTGRES_USER=wardx -e POSTGRES_DB=wardx -e POSTGRES_PASSWORD -e WARDX_LAB_REPL_PASSWORD \
      $PG_IMAGE postgres -c wal_level=replica -c max_wal_senders=10 -c max_replication_slots=10 \
      -c synchronous_commit=on -c wal_keep_size=256MB >/dev/null
  fi
  wait_pg wardx-lab-ha-pg1
  if ! docker container inspect wardx-lab-ha-pg2 >/dev/null 2>&1; then
    WARDX_LAB_REPL_PASSWORD=$(cat "$SECRETS/repl-password") \
    docker run -d --name wardx-lab-ha-pg2 --network $NET -p 127.0.0.1:15433:5432 \
      -v wardx-lab-ha-pg2:/var/lib/postgresql/data \
      -v "$HA/pg/standby-entrypoint.sh:/standby-entrypoint.sh:ro" \
      -e WARDX_LAB_REPL_PASSWORD --entrypoint /standby-entrypoint.sh $PG_IMAGE >/dev/null
  fi
  wait_pg wardx-lab-ha-pg2
  if ! docker container inspect wardx-lab-ha-minio >/dev/null 2>&1; then
    MINIO_ROOT_USER=wardx-lab MINIO_ROOT_PASSWORD=$(cat "$SECRETS/minio-password") \
    docker run -d --name wardx-lab-ha-minio --network $NET \
      -p 127.0.0.1:19000:9000 -p 127.0.0.1:19001:9001 -v wardx-lab-ha-minio:/data \
      -e MINIO_ROOT_USER -e MINIO_ROOT_PASSWORD \
      $MINIO_IMAGE server /data --console-address :9001 >/dev/null
  fi
  if ! docker container inspect wardx-lab-linux-ha >/dev/null 2>&1; then
    LAB_USERS="wardx_rot_ha:$(cat "$SECRETS/target-password"):sudo wardx_rot_sess:$(cat "$SECRETS/target-password")" \
    docker run -d --name wardx-lab-linux-ha --network $NET -p 127.0.0.1:2242:22 \
      -e LAB_USERS $LINUX_IMAGE >/dev/null
  fi
  watchdog_start
  echo "HA lab up"
}

watchdog_start() {
  mkdir -p "$RUN"
  if [ -f "$RUN/watchdog.pid" ] && kill -0 "$(cat "$RUN/watchdog.pid")" 2>/dev/null; then return; fi
  nohup sh "$HA/sync-watchdog.sh" wardx-lab-ha-pg1 wardx_standby >"$RUN/watchdog.log" 2>&1 &
  echo $! > "$RUN/watchdog.pid"
}

watchdog_stop() {
  if [ -f "$RUN/watchdog.pid" ]; then kill "$(cat "$RUN/watchdog.pid")" 2>/dev/null || true; rm -f "$RUN/watchdog.pid"; fi
}

promote() { # promote the standby (after the primary is gone)
  watchdog_stop
  docker exec -u postgres wardx-lab-ha-pg2 psql -U wardx -d wardx -qAt -c "SELECT pg_promote(true, 30)"
}

status() {
  docker ps -a --filter name=^/wardx-lab-ha- --filter name=^/wardx-lab-linux-ha$ \
    --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
  for c in wardx-lab-ha-pg1 wardx-lab-ha-pg2; do
    docker exec -u postgres "$c" psql -U wardx -d wardx -qAt -c \
      "SELECT '$c', CASE WHEN pg_is_in_recovery() THEN 'standby' ELSE 'primary' END, current_setting('synchronous_standby_names')" 2>/dev/null || true
  done
}

down() {
  watchdog_stop
  for c in wardx-lab-ha-pg1 wardx-lab-ha-pg2 wardx-lab-ha-minio wardx-lab-linux-ha; do
    docker rm -f "$c" >/dev/null 2>&1 || true
  done
  for v in wardx-lab-ha-pg1 wardx-lab-ha-pg2 wardx-lab-ha-minio; do
    docker volume rm "$v" >/dev/null 2>&1 || true
  done
  docker network rm $NET >/dev/null 2>&1 || true
  echo "HA lab down (wardx-lab-ha-* and wardx-lab-linux-ha removed)"
}

case "${1:-status}" in
  secrets) secrets ;;
  up) up ;;
  status) status ;;
  promote) promote ;;
  watchdog-start) watchdog_start ;;
  watchdog-stop) watchdog_stop ;;
  down) down ;;
  *) echo "usage: $0 secrets|up|status|promote|watchdog-start|watchdog-stop|down" >&2; exit 2 ;;
esac
