# WardX HA lab (Backend/docs/phase1/HA_DR.md §8)

> **Opt-in.** Nothing here runs in a plain `pytest` run or in CI: the tests need
> `WARDX_LAB=ha` (`Backend/tests/lab_gate.py`). Lab only: local containers and processes,
> no real devices.

## What it runs

| Part | How | 127.0.0.1 ports |
|---|---|---|
| PostgreSQL 17.6 primary `wardx-lab-ha-pg1` | container, `wal_level=replica`, `synchronous_commit=on` | 15432 |
| Streaming standby `wardx-lab-ha-pg2` | container, `pg_basebackup -R` with slot `wardx_standby`, hot standby, `application_name=wardx_standby` | 15433 |
| Sync watchdog | `lab/ha/sync-watchdog.sh` (host process): sets `synchronous_standby_names = 'ANY 1 (wardx_standby)'` while the standby streams and clears it while it does not (degraded = asynchronous, never blocked). **Lab only; never with Patroni.** | — |
| MinIO (`pgsty/minio:RELEASE.2026-08-04T00-00-00Z`) `wardx-lab-ha-minio` | container, bucket `wardx-lab-ha-recordings` (created by WardX) | 19000 (S3), 19001 (console) |
| Linux SSH target `wardx-lab-linux-ha` | `wardx-lab/linux-ssh:1` with `wardx_rot_ha` (sudo) and `wardx_rot_sess` | 2242 |
| API nodes `api-1`, `api-2` | host processes (uvicorn, `WARDX_APP_ROLE=api_only`) | 18010, 18011 |
| Gateway nodes `gw-a`, `gw-b` | host processes, one shared host key | 12222, 12223 |
| Scheduler nodes `sched-1`, `sched-2` | host processes, leader by advisory lock | — |

App nodes run as **host processes** from `Backend/.venv` (no image build, fast restarts, and a
SIGKILL is a real process death). Each runs in `lab/ha/.run/<node>/` with
`WARDX_ENVIRONMENT=production` and every key given explicitly, so no `.env` or dev `.wardx`
state is used. They connect with a multi-host URL,
`postgresql+asyncpg://wardx:…@/wardx?host=127.0.0.1:15432&host=127.0.0.1:15433&target_session_attrs=read-write`,
so they follow a promotion of the standby. Docker objects: only `wardx-lab-ha-*` containers,
volumes and the `wardx-lab-ha-net` network, plus the `wardx-lab-linux-ha` target.

Credentials are generated into `lab/.secrets/ha/` (gitignored, 0700/0600) and passed to the
containers and nodes through environment variables, never on a command line or in a log:
Postgres and replication passwords, MinIO password, JWT secret, KEK, a deliberately wrong KEK
(for the canary test), admin, user and target passwords, and the gateway host key.

## Prerequisites

```bash
sh lab/lab.sh build          # builds wardx-lab/linux-ssh:1 (once)
docker pull postgres:17.6-alpine
```

## Run the failover tests

```bash
cd Backend
WARDX_LAB=ha .venv/bin/python -m pytest -q -s tests/lab_ha
```

The module brings the lab down and up fresh (`ha.sh down`, `ha.sh up`), starts the six nodes,
seeds a user, the pinned Linux target and its accounts, runs the scenarios in order, then stops
every node and removes every lab container, volume and the network:

1. **Wrong KEK:** a node started with `kek-wrong` exits; its log says `KEK canary check failed`.
2. **API node killed:** `api-1` SIGKILLed; `api-2` serves (with a token issued by `api-1`).
3. **Scheduler leader killed:** the standby scheduler takes the advisory lock (term + 1,
   audited `scheduler.leader_elected` naming the previous leader).
4. **Killed gateway:** a live SSH session through `gw-a` to the Linux target; `gw-a` is
   SIGKILLed. Within the lost-node threshold (10 s in the lab) the session is `terminated` /
   "Gateway node lost" (audited with its safe), its check-out is returned, the partial
   recording is in MinIO as ciphertext only, marked incomplete, and replays from `api-2`. A
   reconnect through `gw-b` presents the **same** host key and works.
5. **Killed primary:** writes run against both API nodes; an on-demand rotation of
   `wardx_rot_ha` is caught in flight (`candidate_stored` or later) and `wardx-lab-ha-pg1` is
   killed; the standby is promoted (`ha.sh promote`). Every acknowledged account and its
   secret and audit event exist on the new primary, sample secrets reveal, `POST /audit/verify`
   passes, scheduler leadership is re-established on the new primary, the in-flight rotation
   completes exactly once (one new secret version, one `rotation.succeeded`), a verify
   afterwards succeeds, and the degraded-sync alert is raised (the promoted primary has no
   standby).

## By hand

```bash
sh lab/ha/ha.sh up                     # containers + watchdog (idempotent)
sh lab/ha/ha.sh status                 # roles and synchronous_standby_names
cd Backend && WARDX_LAB=ha .venv/bin/python -m tests.lab_ha.ha_cluster start   # six nodes
#   console API: http://127.0.0.1:18010/api/v1, admin password in lab/.secrets/ha/admin-password
#   gateways: ssh -p 12222 'netops%account%target'@127.0.0.1 (after creating a user)
docker kill wardx-lab-ha-pg1 && sh ../lab/ha/ha.sh promote                     # failover
WARDX_LAB=ha .venv/bin/python -m tests.lab_ha.ha_cluster stop                  # nodes
sh ../lab/ha/ha.sh down                # removes wardx-lab-ha-* and wardx-lab-linux-ha
```

Node logs: `lab/ha/.run/logs/<node>.log`.
