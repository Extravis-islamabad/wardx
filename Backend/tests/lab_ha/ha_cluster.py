"""The HA lab's WardX nodes (lab/ha, HA_DR.md §8): two API, two gateway and two scheduler
nodes as host processes from Backend/.venv, against the lab's Postgres primary + standby and
MinIO containers (started by lab/ha/ha.sh).

Lab only: nothing here runs unless WARDX_LAB=ha (tests/lab_gate.py). Secrets come from
lab/.secrets/ha (0600) into each node's environment, never argv or logs. Each node runs in
its own lab/ha/.run/<node> directory (no .env, no dev .wardx state) with
WARDX_ENVIRONMENT=production, so every key must be given explicitly.

    cd Backend && WARDX_LAB=ha .venv/bin/python -m tests.lab_ha.ha_cluster start|stop|status
"""

from __future__ import annotations

import os
import signal
import subprocess  # noqa: S404 - lab only: starts WardX nodes and lab/ha/ha.sh
import sys
import time
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
LAB_HA = REPO / "lab" / "ha"
SECRETS = REPO / "lab" / ".secrets" / "ha"
RUN = LAB_HA / ".run"
PY = BACKEND / ".venv" / "bin" / "python"
UVICORN = BACKEND / ".venv" / "bin" / "uvicorn"

PG_PORTS = (15432, 15433)
MINIO_PORT = 19000
TARGET_PORT = 2242
BUCKET = "wardx-lab-ha-recordings"


@dataclass(frozen=True)
class Node:
    name: str
    role: str  # api_only | gateway | scheduler
    port: int | None = None


NODES = {
    n.name: n
    for n in (
        Node("api-1", "api_only", 18010),
        Node("api-2", "api_only", 18011),
        Node("gw-a", "gateway", 12222),
        Node("gw-b", "gateway", 12223),
        Node("sched-1", "scheduler"),
        Node("sched-2", "scheduler"),
    )
}


def secret(name: str) -> str:
    return (SECRETS / name).read_text().strip()


def database_url() -> str:
    """Multi-host, read-write: the app follows a promotion to the standby."""
    hosts = "&".join(f"host=127.0.0.1:{p}" for p in PG_PORTS)
    return (
        f"postgresql+asyncpg://wardx:{secret('pg-password')}@/wardx?{hosts}"
        "&target_session_attrs=read-write"
    )


def node_env(node: Node, *, kek_file: str = "kek") -> dict[str, str]:
    home = RUN / node.name
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "PYTHONPATH": str(BACKEND),
        "WARDX_ENVIRONMENT": "production",
        "WARDX_APP_ROLE": node.role,
        "WARDX_NODE_NAME": node.name,
        "WARDX_DATABASE_URL": database_url(),
        "WARDX_DB_POOL_SIZE": "5",
        "WARDX_JWT_SECRET": secret("jwt-secret"),
        "WARDX_VAULT_KEK": secret(kek_file),
        "WARDX_BOOTSTRAP_ADMIN_USERNAME": "admin",
        "WARDX_BOOTSTRAP_ADMIN_PASSWORD": secret("admin-password"),
        "WARDX_GATEWAY_HOST_KEY_FILE": str(SECRETS / "gateway-host-key"),
        "WARDX_GATEWAY_PUBLIC_HOST": "127.0.0.1",
        "WARDX_GATEWAY_LISTEN_HOST": "127.0.0.1",
        "WARDX_RECORDING_DIR": str(home / "recordings"),
        "WARDX_RECORDING_STORE": "s3",
        "WARDX_S3_ENDPOINT": f"127.0.0.1:{MINIO_PORT}",
        "WARDX_S3_SECURE": "false",
        "WARDX_S3_BUCKET": BUCKET,
        "WARDX_S3_ACCESS_KEY": "wardx-lab",
        "WARDX_S3_SECRET_KEY_FILE": str(SECRETS / "minio-password"),
        "WARDX_RECORDING_FLUSH_SECONDS": "1",
        "WARDX_HA_EXPECT_SYNC_STANDBY": "true",
        "WARDX_CLUSTER_CHECK_SECONDS": "3",
        "WARDX_LEADER_INTERVAL_SECONDS": "2",
        "WARDX_GATEWAY_HEARTBEAT_SECONDS": "2",
        "WARDX_GATEWAY_LOST_SECONDS": "10",
        "WARDX_EXPIRY_SWEEP_SECONDS": "5",
        "WARDX_ROTATION_ENABLED": "true",
        "WARDX_ROTATION_TICK_SECONDS": "2",
        "WARDX_ROTATION_LEASE_SECONDS": "15",
        "WARDX_ROTATION_JITTER_SECONDS": "0",
        "WARDX_CORS_ORIGINS": "[]",
    }
    if node.role == "gateway":
        env.update(WARDX_GATEWAY_PORT=str(node.port), WARDX_GATEWAY_NODE=node.name)
    return env


def _pid_file(name: str) -> Path:
    return RUN / "pids" / f"{name}.pid"


def start(name: str, *, node: Node | None = None, kek_file: str = "kek") -> subprocess.Popen:
    node = node or NODES[name]
    home = RUN / node.name
    (home / "recordings").mkdir(parents=True, exist_ok=True, mode=0o700)
    (RUN / "logs").mkdir(parents=True, exist_ok=True)
    (RUN / "pids").mkdir(parents=True, exist_ok=True)
    if node.role == "api_only":
        argv = [
            str(UVICORN),
            "main:app",
            "--app-dir",
            str(BACKEND),
            "--host",
            "127.0.0.1",
            "--port",
            str(node.port),
            "--no-access-log",
        ]
    else:
        argv = [str(PY), str(BACKEND / "main.py")]
    log = (RUN / "logs" / f"{node.name}.log").open("ab")
    proc = subprocess.Popen(  # noqa: S603 - fixed argv; secrets only in env
        argv, cwd=home, env=node_env(node, kek_file=kek_file), stdout=log, stderr=log
    )
    _pid_file(node.name).write_text(str(proc.pid))
    return proc


def signal_node(name: str, sig: int = signal.SIGKILL) -> None:
    path = _pid_file(name)
    if path.exists():
        try:
            os.kill(int(path.read_text()), sig)
        except ProcessLookupError:
            pass
        if sig in (signal.SIGKILL, signal.SIGTERM):
            path.unlink(missing_ok=True)


def stop_all() -> None:
    pid_dir = RUN / "pids"
    for path in sorted(pid_dir.glob("*.pid")) if pid_dir.exists() else []:
        signal_node(path.stem, signal.SIGTERM)
    time.sleep(2)
    for path in sorted(pid_dir.glob("*.pid")) if pid_dir.exists() else []:
        signal_node(path.stem, signal.SIGKILL)


def lab(cmd: str) -> str:
    out = subprocess.run(  # noqa: S603
        ["sh", str(LAB_HA / "ha.sh"), cmd],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    if out.returncode != 0:
        raise RuntimeError(f"ha.sh {cmd} failed: {out.stderr.strip()[-500:]}")
    return out.stdout


def log_of(name: str) -> str:
    path = RUN / "logs" / f"{name}.log"
    return path.read_text(errors="replace") if path.exists() else ""


def main(argv: list[str]) -> int:
    from tests.lab_gate import lab_skip_reason

    reason = lab_skip_reason("ha")
    if reason:
        print(reason, file=sys.stderr)
        return 2
    cmd = argv[0] if argv else "status"
    if cmd == "start":
        lab("up")
        for name in ("api-1",):
            start(name)
        time.sleep(8)  # the first node runs the migrations
        for name in NODES:
            if name != "api-1":
                start(name)
        print("nodes started: " + ", ".join(NODES))
    elif cmd == "stop":
        stop_all()
        print("nodes stopped")
    else:
        pid_dir = RUN / "pids"
        for path in sorted(pid_dir.glob("*.pid")) if pid_dir.exists() else []:
            print(path.stem, path.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
