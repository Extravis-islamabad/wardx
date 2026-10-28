"""Drivers registered by platform id."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from src.rotation.drivers.base import Identity, PlatformDriver


class DriverRegistry:
    def __init__(self) -> None:
        self._drivers: dict[str, PlatformDriver] = {}

    def register(self, driver: PlatformDriver) -> None:
        self._drivers[str(driver.platform)] = driver

    def get(self, platform: str) -> PlatformDriver | None:
        return self._drivers.get(str(platform))

    def platforms(self) -> frozenset[str]:
        return frozenset(self._drivers)

    @contextmanager
    def override(self, platform: str, driver: PlatformDriver) -> Iterator[None]:
        """Tests: swap in a driver for one platform, restoring the previous one after."""
        previous = self._drivers.get(str(platform))
        self._drivers[str(platform)] = driver
        try:
            yield
        finally:
            if previous is None:
                self._drivers.pop(str(platform), None)
            else:
                self._drivers[str(platform)] = previous


_default: DriverRegistry | None = None


def default_registry() -> DriverRegistry:
    """The process-wide registry with every built-in driver."""
    global _default
    if _default is None:
        from src.rotation.drivers.linux import LinuxDriver
        from src.rotation.drivers.mikrotik import MikroTikDriver

        _default = DriverRegistry()
        _default.register(LinuxDriver())
        _default.register(MikroTikDriver())
    return _default


def identities_of(driver: PlatformDriver | None) -> frozenset[Identity]:
    """The device identities a driver needs pinned before it may rotate (SSH host key
    by default; MikroTik also its API-SSL certificate)."""
    return frozenset(getattr(driver, "identities", (Identity.SSH,)))


def uses_tls_identity(platform: str) -> bool:
    """Whether targets of this platform carry a TLS certificate pin."""
    return Identity.TLS in identities_of(default_registry().get(platform))
