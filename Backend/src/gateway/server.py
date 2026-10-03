"""The SSH listener users connect to (APP_ROLE=gateway)."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import socket
from pathlib import Path

import asyncssh
import structlog

from src.core.config import Settings, resolve_gateway_host_key_file
from src.core.context import Actor
from src.errors.exceptions import AppError
from src.gateway.bridge import Bridge, alert
from src.gateway.broker import Broker, GatewayDenied
from src.gateway.naming import GatewayLogin, parse_login

logger = structlog.get_logger(__name__)


def load_host_key(path: Path) -> asyncssh.SSHKey:
    if not path.exists():
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = asyncssh.generate_private_key("ssh-ed25519")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(key.export_private_key())
        logger.info("gateway_host_key_generated", path=str(path))
    return asyncssh.read_private_key(path)


class _Listener(asyncssh.SSHServer):
    """One instance per incoming connection: password auth against WardX users."""

    def __init__(self, gateway: Gateway) -> None:
        self.gateway = gateway
        self.conn: asyncssh.SSHServerConnection | None = None

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        self.conn = conn

    def begin_auth(self, username: str) -> bool:
        return True

    def password_auth_supported(self) -> bool:
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        try:
            login = parse_login(username)
        except ValueError:
            return False
        peer = self.conn.get_extra_info("peername")
        source_ip = peer[0] if peer else None
        try:
            actor = await self.gateway.broker.authenticate(login.wardx_user, password, source_ip)
        except AppError:
            return False
        self.conn.set_extra_info(wardx_login=login, wardx_actor=actor)
        return True


class Gateway:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.node = settings.gateway_node or socket.gethostname()
        self.broker = Broker(settings, self.node)
        self.recording_dir = Path(settings.recording_dir).resolve()
        self.bridges: set[Bridge] = set()
        self.server: asyncssh.SSHAcceptor | None = None
        self._watcher: asyncio.Task | None = None

    async def start(self) -> None:
        self.recording_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        recovered = await self.broker.recover_orphans()
        if recovered:
            logger.warning("gateway_orphan_sessions_closed", count=recovered)
        host_key = load_host_key(resolve_gateway_host_key_file(self.settings))
        self.server = await asyncssh.create_server(
            lambda: _Listener(self),
            self.settings.gateway_listen_host,
            self.settings.gateway_port,
            server_host_keys=[host_key],
            process_factory=self._handle,
            encoding=None,
            line_editor=False,
            agent_forwarding=False,
            x11_forwarding=False,
            allow_scp=False,
            keepalive_interval=30,
            login_timeout=60,
        )
        self._watcher = asyncio.create_task(self._watch())
        logger.info(
            "gateway_listening",
            node=self.node,
            port=self.port,
            fingerprint=host_key.get_fingerprint("sha256"),
        )

    @property
    def port(self) -> int:
        return self.server.get_port() if self.server else 0

    async def stop(self) -> None:
        if self._watcher:
            self._watcher.cancel()
        if self.server:
            self.server.close()
            await self.server.wait_closed()

    async def _handle(self, process: asyncssh.SSHServerProcess) -> None:
        conn = process.channel.get_connection()
        login: GatewayLogin = conn.get_extra_info("wardx_login")
        actor: Actor = conn.get_extra_info("wardx_actor")
        mode = "exec" if process.command is not None else "shell"
        if process.subsystem is not None:
            process.stderr.write(alert("Subsystems (SFTP) are not available through the gateway."))
            process.exit(1)
            return
        try:
            grant = await self.broker.open(
                actor,
                target_name=login.target,
                account_username=login.account,
                mode=mode,
                command=process.command,
            )
        except GatewayDenied as exc:
            process.stderr.write(alert(str(exc)))
            process.exit(1)
            return
        bridge = Bridge(
            grant,
            process,
            self.broker,
            recording_dir=self.recording_dir,
            connect_timeout=self.settings.target_connect_timeout_seconds,
        )
        self.bridges.add(bridge)
        try:
            await bridge.run()
        finally:
            self.bridges.discard(bridge)

    async def _watch(self) -> None:
        while True:
            await asyncio.sleep(self.settings.gateway_watch_seconds)
            with contextlib.suppress(Exception):
                live = {b.grant.session_id: b for b in self.bridges}
                orders = await self.broker.close_orders([b.grant for b in live.values()])
                for sid, order in orders.items():
                    live[sid].order_close(order)


async def run_gateway(settings: Settings) -> None:
    from src.core.app_factory import startup

    await startup(settings)
    gateway = Gateway(settings)
    await gateway.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    await stop.wait()
    await gateway.stop()
