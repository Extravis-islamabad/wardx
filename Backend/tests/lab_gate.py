"""Device lab tests are opt-in.

A plain ``pytest`` run must never touch a device, a lab VM or a lab container: lab
tests run only when ``WARDX_LAB`` names their lab (comma-separated, or ``all``), e.g.
``WARDX_LAB=mikrotik``, ``WARDX_LAB=linux,mikrotik`` or ``WARDX_LAB=ha`` (the HA lab,
lab/ha/). CI never sets it.

Check the gate BEFORE probing anything: an unavailable-lab check that connects to the
device is itself device contact.
"""

from __future__ import annotations

import os

LAB_ENV = "WARDX_LAB"
KNOWN_LABS = frozenset({"ha", "linux", "mikrotik"})


def enabled_labs() -> frozenset[str]:
    raw = os.environ.get(LAB_ENV, "")
    names = {n.strip().lower() for n in raw.split(",") if n.strip()}
    return KNOWN_LABS if "all" in names else frozenset(names)


def lab_skip_reason(lab: str) -> str | None:
    """None when the lab is switched on, otherwise why its tests are skipped."""
    if lab in enabled_labs():
        return None
    return (
        f"device lab '{lab}' not enabled: set {LAB_ENV}={lab} to run these tests "
        "(a plain pytest run never touches a device)"
    )
