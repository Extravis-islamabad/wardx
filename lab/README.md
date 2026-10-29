# WardX rotation lab

> **Lab tests are opt-in.** A plain `pytest` run never touches a device, lab VM or lab container:
> those tests run only with `WARDX_LAB` naming their lab, e.g. `WARDX_LAB=mikrotik`,
> `WARDX_LAB=linux,mikrotik` or `WARDX_LAB=all`. CI never sets it (`tests/lab_gate.py`;
> guarded by `tests/security/test_lab_opt_in.py`).

Lab targets for the rotation engine (Backend/docs/phase1/ROTATION.md §1, §9).
**Lab only: never point rotation at a production, customer or shared device.**
Rotation tests create their own `wardx_rot_*` accounts and remove only those.

| Target | How | Host ports (127.0.0.1 only) | Status |
|---|---|---|---|
| Linux (Debian 12, OpenSSH, sudo) | `wardx-lab/linux-ssh:1`, one throwaway container per test run (`wardx-lab-linux-*`), accounts from `LAB_USERS` | chosen per test | ready |
| MikroTik CHR 7.25 (arm64) | `wardx-lab-mikrotik`, QEMU inside a container, booted from a throwaway overlay | SSH 2232, API 8738, API-SSL 8739 | ready |
| Windows Server (eval) | not yet: no ARM64 Windows Server build for this Apple Silicon host | — | pending decision |
| Cisco / Huawei | simulated CLIs until an office lab device is confirmed (**lab-unverified**) | — | simulators |

The **HA lab** (Postgres primary + standby, MinIO, two API, two gateway and two scheduler
nodes, failover tests) is separate: see [ha/README.md](ha/README.md) (`WARDX_LAB=ha`).

## Setup

```bash
sh lab/lab.sh build
# MikroTik image (checksum-verified, not committed):
#   https://download.mikrotik.com/routeros/7.25/chr-7.25-arm64.img.zip (+ .sha256)
#   unzip into lab/mikrotik/images/
sh lab/lab.sh up-mikrotik
sh lab/lab.sh status
sh lab/lab.sh down        # removes wardx-lab-* containers only
```

Lab credentials are generated locally into `lab/.secrets/` (gitignored, mode 0600) and never
printed. Note for the MikroTik driver: **RouterOS accepts any SSH password while an account's
password is empty**, so a successful login alone never proves a password works.

## Rotation tests against the Linux lab

`Backend/tests/integration/rotation/test_linux_lab.py` and `test_linux_e2e.py` start their own
`wardx-lab-linux-<random>` container per module (random host port on 127.0.0.1, `wardx_rot_*`
users with generated passwords passed through the environment) and remove it by name
afterwards. Without Docker or the image they are skipped with the reason.

```bash
cd Backend && .venv/bin/python -m pytest -q -rs tests/integration/rotation
```

### The end-to-end run by hand (console)

```bash
# 1. A lab target with one account; the password goes to lab/.secrets/, never to the screen.
umask 077; python3 -c 'import secrets; print("Lab-" + secrets.token_urlsafe(18))' > lab/.secrets/linux-demo
LAB_USERS="wardx_rot_demo:$(cat lab/.secrets/linux-demo)" docker run -d --name wardx-lab-linux-demo \
  --network wardx-lab -p 127.0.0.1:2242:22 -e LAB_USERS wardx-lab/linux-ssh:1
# 2. Run the API with rotation on (a scratch or dev database of your own), e.g. on 8011:
#    WARDX_ROTATION_ENABLED=true WARDX_ROTATION_TICK_SECONDS=5 .venv/bin/uvicorn main:app --port 8011
# 3. In the console: add target 127.0.0.1:2242 (linux, ssh) with "Rotation allowed",
#    Targets → Learn host key; add account wardx_rot_demo with the password from the file
#    (copy it, do not echo it); give its safe a two-level approval policy and
#    "Rotate after use"; request, approve twice, check out, check in; an emergency
#    reveal before the check-in makes the job wait; check the emergency one in and the
#    Rotation tab shows the job succeed with a clean verify.
# 4. Clean up: docker rm -f wardx-lab-linux-demo && rm lab/.secrets/linux-demo
```

## Rotation tests against the MikroTik CHR

`Backend/tests/integration/rotation/test_mikrotik_lab.py` and `test_mikrotik_e2e.py` use the
running `wardx-lab-mikrotik` container (they never start, restart or remove it) and are
skipped with the reason when Docker, the container or its API-SSL is not available. They log in
as `admin` (password from `lab/.secrets/mikrotik-admin`) only to create, change and remove their
own `wardx_rot_*` users. Some tests disable `api-ssl` or switch it to a temporary certificate
generated **on the device** (`wardx_rot_cert_*`); both are always restored, and the module
checks at the end that `api-ssl` is enabled with `wardx-lab-api` and only `admin` is left.

```bash
cd Backend && .venv/bin/python -m pytest -q -rs tests/integration/rotation -k "mikrotik or tls"
```

### The MikroTik end-to-end run by hand (console)

```bash
# 1. A wardx_rot_ user on the CHR; its password goes to lab/.secrets/, never to the screen.
umask 077; python3 -c 'import secrets; print("Lab-" + secrets.token_urlsafe(18))' > lab/.secrets/mikrotik-demo
cd Backend && PYTHONPATH=. .venv/bin/python - <<'PY'
import asyncio, pathlib
from tests.integration.rotation.mikrotik_lab import Chr
async def main():
    box = await Chr.connect()
    async with box.api() as conn:
        pw = pathlib.Path("../lab/.secrets/mikrotik-demo").read_text().strip()
        await conn.call("/user/add", {"name": "wardx_rot_demo", "group": "read", "password": pw},
                        secret_attrs=("password",))
    await box.close()
asyncio.run(main())
PY
# 2. Run the API with rotation on (a scratch or dev database of your own), e.g. on 8011:
#    WARDX_ROTATION_ENABLED=true WARDX_ROTATION_TICK_SECONDS=5 .venv/bin/uvicorn main:app --port 8011
# 3. In the console: add target 127.0.0.1, port 2232, platform MikroTik RouterOS, protocol SSH,
#    API-SSL port 8739, "Rotation allowed". Targets → Host key: compare and accept the SSH key,
#    then compare the API-SSL fingerprint with `/certificate print detail where
#    name=wardx-lab-api` and accept it. Add account wardx_rot_demo with the password from the
#    file (copy it, do not echo it), give its safe a two-level approval policy and "Rotate
#    after use"; request, approve twice, check out, check in. The Rotation tab shows the job
#    succeed over api-ssl with a clean verify.
# 4. Clean up: run the step 1 snippet with `await box.remove_user("wardx_rot_demo")` in place
#    of the `async with` block, then rm lab/.secrets/mikrotik-demo
```

## MikroTik CHR lab state

What is configured on `wardx-lab-mikrotik` (checked read-only on 2026-10-28):

| Item | State |
|---|---|
| Users | `admin` only (password in `lab/.secrets/mikrotik-admin`). Tests create and remove their own `wardx_rot_*` users; nothing else is ever changed on `admin`. |
| Certificate | `wardx-lab-api`: self-signed, RSA 2048, SHA-256, created **on the device**. Its private key exists only on the CHR; no certificate or key file is kept on this machine. |
| `api-ssl` (8729, host 8739) | enabled, using `wardx-lab-api` |
| `api` (8728, host 8738) and `telnet` | still enabled (CHR defaults), so tests can check that WardX **refuses** rotation over cleartext. Disable them on real devices (see `Backend/docs/phase1/ONBOARDING_MIKROTIK.md`). |

RouterOS 7.25 self-signs only with `key-cert-sign` in `key-usage` (`wardx-lab-api` has the
default key usage, which includes it).

The certificate was created with the same commands as the product onboarding doc. Trust in
WardX comes from pinning its SHA-256 fingerprint through the Host key flow, never from turning
off certificate checks. If the CHR container is ever rebuilt, recreate the certificate with those
commands and accept the new fingerprint in WardX.

