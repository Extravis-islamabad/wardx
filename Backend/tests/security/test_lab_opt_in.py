"""Device lab tests are opt-in (tests/lab_gate.py): without WARDX_LAB, importing the lab
helpers makes no device, Docker or network call, and their tests are skipped."""

from __future__ import annotations

import importlib

import pytest

from tests.lab_gate import LAB_ENV, enabled_labs, lab_skip_reason


def test_gate_parses_the_flag(monkeypatch):
    monkeypatch.delenv(LAB_ENV, raising=False)
    assert enabled_labs() == frozenset()
    assert "WARDX_LAB=mikrotik" in lab_skip_reason("mikrotik")
    monkeypatch.setenv(LAB_ENV, "Linux, mikrotik")
    assert enabled_labs() == {"linux", "mikrotik"}
    assert lab_skip_reason("mikrotik") is None
    monkeypatch.setenv(LAB_ENV, "all")
    assert lab_skip_reason("linux") is None and lab_skip_reason("mikrotik") is None


def test_no_device_contact_without_the_flag(monkeypatch):
    """Patched at the lowest level (subprocess and the RouterOS client), because reloading
    the lab modules redefines their own helpers."""
    import subprocess

    monkeypatch.delenv(LAB_ENV, raising=False)
    from src.transport import routeros_api
    from tests.integration.rotation import linux_lab, mikrotik_lab

    touched: list[str] = []

    async def no_chr(*args, **kwargs):
        touched.append("chr")
        raise routeros_api.Unavailable("contacted without WARDX_LAB")

    def no_subprocess(*args, **kwargs):
        touched.append("subprocess")
        raise FileNotFoundError("docker used without WARDX_LAB")

    monkeypatch.setattr(routeros_api, "fetch_certificate", no_chr)
    monkeypatch.setattr(subprocess, "run", no_subprocess)
    from tests.lab_ha import ha_cluster

    importlib.reload(mikrotik_lab)
    importlib.reload(linux_lab)
    importlib.reload(ha_cluster)
    assert ha_cluster.main(["start"]) == 2  # refuses without WARDX_LAB=ha
    assert touched == []
    assert "WARDX_LAB=ha" in lab_skip_reason("ha")
    assert "WARDX_LAB" in mikrotik_lab._REASON
    assert "WARDX_LAB" in linux_lab._REASON


@pytest.mark.parametrize("lab", ["ha", "linux", "mikrotik"])
def test_ci_never_enables_a_lab(lab):
    """The CI workflows must not set WARDX_LAB."""
    import pathlib

    workflows = pathlib.Path(__file__).resolve().parents[3] / ".github" / "workflows"
    for wf in workflows.glob("*.yml"):
        assert LAB_ENV not in wf.read_text(), f"{wf.name} sets {LAB_ENV}"
