"""Drivers registered by platform id."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from src.rotation.drivers.base import PlatformDriver


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

        _default = DriverRegistry()
        _default.register(LinuxDriver())
    return _default
