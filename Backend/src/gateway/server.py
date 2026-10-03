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

# Failed authentication attempts per connection before it is dropped (sshd default is 6).
MAX_AUTH_TRIES = 3


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
        # Keyboard-interactive is two rounds when MFA is on: password, then code.
        self._stage = "password"
        self._pending: tuple[GatewayLogin, Actor] | None = None
        self._failures = 0

    def connection_made(self, conn: asyncssh.SSHServerConnection) -> None:
        self.conn = conn

    def begin_auth(self, username: str) -> bool:
        return True

    def _source_ip(self) -> str | None:
        peer = self.conn.get_extra_info("peername")
        return peer[0] if peer else None

    async def _check_password(
        self, username: str, password: str
    ) -> tuple[GatewayLogin, Actor] | None:
        try:
            login = parse_login(username)
        except ValueError:
            return None
        try:
            actor = await self.gateway.broker.authenticate(
                login.wardx_user, password, self._source_ip()
            )
        except AppError:
            return None
        return login, actor

    def _reject(self) -> bool:
        """Count a failed attempt; drop the connection after MAX_AUTH_TRIES, like sshd."""
        self._failures += 1
        if self._failures >= MAX_AUTH_TRIES:
            self.conn.disconnect(
                asyncssh.DISC_NO_MORE_AUTH_METHODS_AVAILABLE, "Too many authentication failures"
            )
        return False

    def _accept(self, login: GatewayLogin, actor: Actor) -> bool:
        self.conn.set_extra_info(wardx_login=login, wardx_actor=actor)
        return True

    # ── Password: for users without MFA ──

    def password_auth_supported(self) -> bool:
        return True

    async def validate_password(self, username: str, password: str) -> bool:
        checked = await self._check_password(username, password)
        if checked is None:
            return self._reject()
        if await self.gateway.broker.mfa_enabled(checked[1]):
            # Plain password auth cannot ask for the code; the client falls back
            # to keyboard-interactive, which can.
            return False
        return self._accept(*checked)

    # ── Keyboard-interactive: password, then code when MFA is on ──

    def kbdint_auth_supported(self) -> bool:
        return True

    def get_kbdint_challenge(self, username: str, lang: str, submethods: str):
        self._stage, self._pending = "password", None
        return ("WardX sign-in", "", "", [("WardX password: ", False)])

    async def validate_kbdint_response(self, username: str, responses: list[str]):
        if len(responses) != 1:
            return self._reject()
        if self._stage == "password":
            checked = await self._check_password(username, responses[0])
            if checked is None:
                return self._reject()
            if not await self.gateway.broker.mfa_enabled(checked[1]):
                return self._accept(*checked)
            self._stage, self._pending = "code", checked
            return ("WardX sign-in", "", "", [("Authenticator or recovery code: ", True)])
        if self._stage == "code" and self._pending is not None:
            login, actor = self._pending
            if await self.gateway.broker.verify_mfa(actor, responses[0]):
                return self._accept(login, actor)
        return self._reject()


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
