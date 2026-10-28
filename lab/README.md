# WardX rotation lab

Lab targets for the rotation engine (Backend/docs/phase1/ROTATION.md §1, §9).
**Lab only: never point rotation at a production, customer or shared device.**
Rotation tests create their own `wardx_rot_*` accounts and remove only those.

| Target | How | Host ports (127.0.0.1 only) | Status |
|---|---|---|---|
| Linux (Debian 12, OpenSSH, sudo) | `wardx-lab/linux-ssh:1`, one throwaway container per test run (`wardx-lab-linux-*`), accounts from `LAB_USERS` | chosen per test | ready |
| MikroTik CHR 7.25 (arm64) | `wardx-lab-mikrotik`, QEMU inside a container, booted from a throwaway overlay | SSH 2232, API 8738, API-SSL 8739 | ready |
| Windows Server (eval) | not yet: no ARM64 Windows Server build for this Apple Silicon host | — | pending decision |
| Cisco / Huawei | simulated CLIs until an office lab device is confirmed (**lab-unverified**) | — | simulators |

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
