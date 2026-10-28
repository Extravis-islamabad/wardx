"""SSH logins for rotation drivers: pinned host key only, one credential attempt.

- The host key must equal the pin from the gateway's TOFU store; rotation never pins.
  With no pin, or a different key, the credential is never sent.
- Exactly one password submission per login, whichever method the server offers
  (keyboard-interactive or password), so a wrong password counts as one failure
  against the device's lockout policy, never two.
"""

from __future__ import annotations

import asyncio

import asyncssh

from src.rotation.drivers.base import DriverError, Outcome, StepResult, TargetRef
from src.transport.ssh import host_key_algs


class _OneShotClient(asyncssh.SSHClient):
    def __init__(self, secret: str) -> None:
        self._secret = secret
        self.used = False

    def password_auth_requested(self) -> str | None:
        if self.used:
            return None
        self.used = True
        return self._secret

    def kbdint_auth_requested(self) -> str | None:
        return "" if not self.used else None

    def kbdint_challenge_received(self, name, instructions, lang, prompts):
        if not prompts:
            return []
        if self.used or len(prompts) != 1:
            return None
        self.used = True
        return [self._secret]


async def ssh_login(
    target: TargetRef,
    username: str,
    secret: str,
    *,
    timeout: float,  # noqa: ASYNC109 - applied to the whole login
) -> asyncssh.SSHClientConnection:
    """Log in, or raise DriverError with the outcome (never retries the credential)."""
    if not target.pinned_host_key:
        raise DriverError(
            StepResult(
                Outcome.HOST_KEY_MISMATCH,
                f"{target.name} has no pinned SSH host key; pin it before rotating. "
                "The credential was not sent.",
            )
        )
    trusted = asyncssh.import_public_key(target.pinned_host_key)
    try:
        return await asyncio.wait_for(
            asyncssh.connect(
                target.address,
                target.port,
                username=username,
                known_hosts=([trusted], [], []),
                server_host_key_algs=host_key_algs(trusted),
                client_factory=lambda: _OneShotClient(secret),
                client_keys=None,
                password=None,
                preferred_auth="keyboard-interactive,password",
                agent_path=None,
                config=None,
            ),
            timeout,
        )
    except asyncssh.HostKeyNotVerifiable as exc:
        raise DriverError(
            StepResult(
                Outcome.HOST_KEY_MISMATCH,
                f"HOST KEY MISMATCH for {target.name}: it did not present the pinned key. "
                "The credential was not sent.",
            )
        ) from exc
    except asyncssh.PermissionDenied as exc:
        raise DriverError(
            StepResult(Outcome.AUTH_FAILED, f"{target.name} refused the login for {username}")
        ) from exc
    except TimeoutError as exc:
        raise DriverError(
            StepResult(Outcome.UNREACHABLE, f"Timed out connecting to {target.name}")
        ) from exc
    except (OSError, asyncssh.Error) as exc:
        raise DriverError(
            StepResult(Outcome.UNREACHABLE, f"Could not connect to {target.name}: {exc}")
        ) from exc
