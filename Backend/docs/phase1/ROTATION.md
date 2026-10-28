# Phase 1 (c) Rotation engine and platforms: spec (draft for review)

Status: **draft for review. No rotation code is written until it is approved.**
Builds on the groundwork already in the repo: migration `007_rotation.sql` (job queue, per-account
rotation fields), `src/rotation/passwords.py` (generator) and `src/transport/ssh.py` (expect-style
CLI with redacted transcripts). Layering follows `Backend/ARCHITECTURE.md`. Encryption goes only
through the vault service (key provider).

## 1. Safety rules (apply to code, tests and every environment)

1. **Off unless switched on twice.** Rotation runs only when `WARDX_ROTATION_ENABLED=true`
   **and** the target has `rotation_allowed = true`. Both default to off, so adding a device
   never rotates anything by accident.
2. **Never lose the only working password.** The new password is stored in the vault before
   the device is touched. No version that might be the working one is deleted.
3. **Never rotate under a live holder.** A rotation of an account that someone holds (normal or
   emergency check-out, or a live gateway session) waits until every holder has released it.
4. **Never put secrets in logs, transcripts, process lists or command history.**
   - Current, new and reconcile passwords are redacted in every transcript.
   - Passwords go through interactive prompts, stdin or the API, never through argv.
   - A platform that would echo the password into a persistent log is driven in a way that
     avoids it (see §3).
5. **Pinned identity only.** SSH host keys must match the pin from the gateway's
   trust-on-first-use (TOFU) store, and WinRM certificates must validate. A mismatch refuses
   the rotation, and the credential is never sent. Telnet is refused for rotation.
6. **Testing only on lab devices and containers** set up for WardX. Never rotate an existing
   account on any real or shared device. Destructive tests create dedicated accounts first
   (`wardx_rot_<random>`), and clean-up removes only accounts the test itself created. The
   existing dev-DB accounts are never rotated: tests make their own targets and accounts.

## 2. Platform plugin interface

One driver per platform, registered by `Platform` id. A driver contains no policy, scheduling
or vault logic; it only talks to the device.

```python
class PlatformDriver(Protocol):
    platform: Platform
    capabilities: frozenset[Capability]   # CHANGE_SELF, CHANGE_VIA_RECONCILE, VERIFY,
                                          # PERSIST (network config save), SSH_KEY (later)
    default_policy: PasswordPolicy

    async def connect(self, target: TargetRef, login: Credential, ctx: DriverContext) -> DriverSession: ...
    async def change(self, session: DriverSession, account: AccountRef,
                     current: str | None, new: str, ctx: DriverContext) -> StepResult: ...
        # current is None when changing through a reconcile account
    async def persist(self, session: DriverSession, ctx: DriverContext) -> StepResult: ...
        # no-op where the change is already durable
    async def verify(self, target: TargetRef, account: AccountRef, secret: str,
                     ctx: DriverContext) -> StepResult: ...   # always a fresh login
    async def reconcile(self, session: DriverSession, account: AccountRef, new: str,
                        ctx: DriverContext) -> StepResult: ...
        # session is logged in as the reconcile account
```

- `StepResult.outcome`:
  - `ok`;
  - `auth_failed`;
  - `rejected_by_device` (for example a complexity or history rule);
  - `unreachable`;
  - `host_key_mismatch`;
  - `ambiguous` (the command was sent, but the connection dropped before a definite answer).
- `DriverContext` carries timeouts, the transcript recorder (with redaction list) and the
  pinned host key or certificate.
- Drivers are pure async and unit-testable against simulated CLIs (`tests/integration/fake_device.py`
  extended per dialect).

### First platforms

| Platform | Transport | Change (self) | Change via reconcile account | Persist | Verify |
|---|---|---|---|---|---|
| **Linux/Unix** | SSH (pinned key) | `passwd` with interactive prompts | `sudo chpasswd` with `user:pass` on stdin | not needed | new SSH login with the new password |
| **Windows** (local accounts) | WinRM over HTTPS 5986, NTLM, cert validated | none (can't change self without admin rights) | PowerShell `Set-LocalUser -Password` with a SecureString built from stdin, never in the command line | not needed | WinRM logon as the account; SMB auth if it has no WinRM rights (question Q6) |
| **Cisco IOS / IOS-XE** | SSH CLI | `configure terminal` → `username X algorithm-type scrypt secret <pw>` → `end` | same, as an admin user | `copy running-config startup-config` (confirm prompt) | new SSH login, plus `enable` if the account uses it |
| **Huawei VRP** | SSH CLI | `system-view` → `aaa` → `local-user X password irreversible-cipher <pw>` → `return` | same, as an admin user | `save` (answer `Y`) | new SSH login, handling the first-login "change password?" prompt by answering N |
| **MikroTik RouterOS** | API-SSL 8729 (preferred), SSH CLI fallback | `/user/set` via the API | same, as an admin user | not needed | new API or SSH login |

Device notes the drivers must handle:
- **Cisco:** the `?` key triggers help, and some IOS versions cap secret length. The policy
  below avoids `?`, and driver tests cover the length cap.
- **Huawei:** VRP enforces password history and "can't contain the username". A
  `rejected_by_device` result maps to a clear message.
- **MikroTik:** commands typed over SSH can land in `/system history`. The API avoids that,
  which is why it is preferred (question Q7).

## 3. Password policy per platform

```python
@dataclass(frozen=True)
class PasswordPolicy:
    length: int                     # generated length
    min_length: int
    max_length: int                 # device cap
    classes: frozenset[CharClass]   # lower, upper, digit, symbol
    min_classes: int                # e.g. Windows "3 of 4"
    symbols: str                    # allowed symbol set for this platform
    forbid_leading_symbol: bool
    forbid_username_substring: bool
    max_repeat: int                 # longest run of one character
```

**Defaults** (to be confirmed per firmware in the lab, and recorded in the driver):

| Platform | Length (min–max) | Classes | Symbols | Notes |
|---|---|---|---|---|
| Linux | 24 (12–128) | all 4 | `-_.,:+=@#%^*` | |
| Windows | 24 (14–127) | all 4 (needs 3) | `-_.,:+=@#%^*` | no username substring |
| Cisco IOS | 24 (12–25*) | all 4 | `-_.,:+=@#%^*` | *older IOS cap; newer allow longer, set per target |
| Huawei VRP | 20 (12–32*) | all 4 (needs 3) | `-_.,:+=@#%^*` | no username or reversed username |
| MikroTik | 24 (12–64) | all 4 | `-_.,:+=@#%^*` | |

**How a policy is resolved:** platform default → **target override** (device-specific caps
such as an old IOS) → account `password_length`, clamped to the target's min and max. Every
policy is validated on save, so it must be satisfiable. The generator
(`src/rotation/passwords.py`) takes the policy instead of a bare length.

## 4. Triggers

| Trigger | When | Notes |
|---|---|---|
| **Scheduled** | `rotation_interval_days` passed since `last_rotated_at` (per account; safe-level default, question Q1) | The scheduler enqueues due jobs with jitter, within the safe's maintenance window if one is set (question Q12). |
| **After use** | Check-in, check-out expiry or revoke, gateway session end, or a used approval, when the account's safe policy has `rotate_after_use` | The job is created at once in state `waiting_release`. It runs only when **every** holder (normal and emergency check-outs, live gateway sessions) has released the account. |
| **On demand** | A holder of `manage_accounts` on the safe clicks Rotate | Audited with a reason. Also **Verify now** and **Reconcile now**. |
| **Compromise** (later) | The key-compromise procedure (TENANCY_KEYS.md §6.1) | Same engine, high priority. |

**Holders and waiting** (question Q3):
- A job in `waiting_release` blocks **new normal** check-outs and gateway sessions of that
  account ("rotation pending"), so the wait can't be extended forever.
- Emergency check-outs are still allowed. They extend the wait and are counted as holders.
- If the wait passes `max_release_wait` (default 4 hours), a high alert is raised and the
  job keeps waiting. It never rotates under a holder.

**Concurrency:**
- At most one open job per account (existing unique index).
- At most one running job per **target**, because two config sessions on one switch collide.
- A global worker pool (default 4).
- Jobs are claimed with `FOR UPDATE SKIP LOCKED`, so several scheduler processes are safe.
- Retries back off (1, 5, 15 minutes), up to 3 attempts.

## 5. Rotation state machine and failure handling

Account versions: **N** is the current, working version (`accounts.secret_version`). **C** is
the candidate.

```
pending ─▶ (waiting_release) ─▶ claimed
  1. generate C per policy
  2. store C in the vault as version N+1   ── commit ──▶ state candidate_stored
       (secret_version still N; nothing on the device has changed yet)
  3. connect with N (or with the reconcile account)
  4. change to C on the device             ── commit ──▶ state device_changed
  5. persist on the device (network)       ── commit ──▶ state persisted
  6. verify: fresh login with C
  7. promote: secret_version = N+1, last_rotated_at, sync_status = in_sync
                                           ── commit ──▶ succeeded (audited)
```

Each state is committed **before** the next step touches the device, so a crash at any point
is recoverable. On restart, a job found in a non-final state is resumed by the recovery rule
for its state.

| Failure | What WardX does | Why the working password survives |
|---|---|---|
| Vault write of C fails (step 2) | Job fails. The device is never touched. | N unchanged everywhere. |
| Can't connect, or N is rejected (step 3) | Job fails. Account marked `out_of_sync` if N was rejected; alert; reconcile path. C is marked `abandoned`, kept, never promoted. | N still current in the vault. |
| Device rejects C, e.g. its complexity rule (step 4) | Job fails with the device's reason; C abandoned. | Device still on N, vault still on N. |
| **Device accepted C, but WardX failed to record it** (crash or DB down after step 4) | Recovery: verify with C. If it works, promote. If not, verify with N: if N works, the change never happened, so retry. If neither works, `needs_attention` and reconcile. | C was stored in the vault **before** the device changed, so WardX already holds the device's new password. |
| **WardX recorded the change, but the device didn't keep it** (for example save failed, or a reboot reverted it) | Persist fails: retry the save once. If it still fails, roll the device back to N, then verify N. If the rollback fails, `needs_attention`. A later periodic verify catches a device that reverts after a reboot: N still works and C doesn't. | N is never deleted, so WardX can always fall back to it. |
| Ambiguous (connection dropped mid-change) | Same as the "device accepted" recovery: verify C, then N. | Both versions are in the vault. |
| Verify with C fails after the device said OK | Verify with N. If N works, the change didn't apply, so retry. If neither works, `needs_attention`. | Both versions kept. |

**Invariants:**
- Rotation never deletes secret versions.
- The current and previous versions are always kept, plus the last 5 (question Q10).
- Versions referenced by open check-outs are kept too.
- `needs_attention` raises a high alert and blocks automatic retries until an admin resolves it
  by reconciling, marking it fixed by hand, or setting the secret manually. The resolution is
  audited.

**Holders keep their version.** A check-out records the version it revealed. Because rotation
waits for release, no holder is ever left with a stale password mid-session.

## 6. Verify and reconcile

**Verify:**
- A fresh login with the current version.
- Runs on a schedule (default every 24 hours per account, set per safe), immediately after
  every rotation, and on demand.
- Results: `in_sync`, `out_of_sync` (N rejected), or `unreachable` (no conclusion). Stored as
  `sync_status` and `last_verified_at`.
- `out_of_sync` raises an alert. Unreachable three times in a row raises a warning.

**Reconcile account:**
- A privileged account on the same target (or one designated per safe or platform), for
  example root via sudo, a Windows local admin, or a network admin user.
- It is itself a WardX account, stored in a safe and protected like any other.
- Linked by `accounts.reconcile_account_id`. It must be a different account, on the same target
  or one the platform allows (Windows domain admin, later).

**Reconcile flow:**
1. Connect as the reconcile account.
2. Set the target account to a **new** candidate C, stored in the vault first, with the same
   state machine. It is never set to the unknown old password.
3. Verify with C, then promote.
4. Audited as `rotation.reconcile`. Using the reconcile account is audited and doesn't count as
   a check-out.

**Rules:**
- **Auto-reconcile** on `out_of_sync` is off by default per safe (question Q5). When it's on,
  WardX reconciles automatically and still alerts.
- **The reconcile account itself** can't be reconciled through itself. If it goes out of sync,
  it needs another reconcile account or a manual reset. Rotating it follows the normal
  self-change path.
- **Reconcile accounts can't be checked out** by users unless the safe grants `retrieve` on
  them explicitly. Recommended: a dedicated safe for reconcile accounts.

## 7. Data model (additive migrations)

- **`inventory.targets`:** `rotation_allowed` (default false), `policy_overrides` (JSONB:
  min/max length, symbols, and so on).
- **`inventory.accounts`:** `reconcile_account_id`, `sync_status`, `last_verified_at`,
  `rotation_status`. The existing `rotation_interval_days`, `rotate_after_checkin` (to be
  renamed `rotate_after_use`), `password_length`, `last_rotated_at` and
  `last_rotation_status` are kept.
- **Safe policy:**
  - `rotate_after_use`
  - `rotation_interval_days` (default for its accounts)
  - `verify_interval_hours`
  - `auto_reconcile`
  - `maintenance_window` (days and hours)
  - `max_release_wait_minutes`
- **`access.rotation_jobs`:**
  - New reasons: `after_use`, `reconcile`, `verify`, `compromise`.
  - New states: `waiting_release`, `candidate_stored`, `device_changed`, `persisted`.
  - New field: `secret_versions_touched`.
- **`access.rotation_job_steps`:** per-step outcome, timestamps and the redacted transcript
  fragment.
- **`vault.secrets`:** `status` (`current` / `previous` / `candidate` / `abandoned`) for
  clarity. The vault never infers which version is current; `accounts.secret_version` stays
  the source of truth.

## 8. API and UI

- **API:**
  - `POST /accounts/{id}/rotate`, `/verify`, `/reconcile` (each needs `manage_accounts`, with
    a reason).
  - `GET /accounts/{id}/rotation` (status and history).
  - `GET /rotation/jobs` with filters.
  - `POST /rotation/jobs/{id}/resolve` (for `needs_attention`).
  - Target `rotation_allowed` and policy-override fields, set under `inventory.manage`.
- **UI:**
  - An account **Rotation** tab: status, last rotated or verified, job history with step
    timeline and redacted transcript, and Rotate / Verify / Reconcile buttons.
  - The safe's rotation policy.
  - A Rotation jobs page.
  - Dashboard items for `needs_attention`, `out_of_sync` and waits that have passed
    `max_release_wait`.

## 9. Testing

**Unit:**
- policy resolution and generator compliance (property tests across policies);
- the state machine, with every failure injected at every step, including crash and resume
  from each persisted state;
- redaction;
- argv safety (assert no secret in the spawned command line).

**Integration (lab only, see §1):**
- **Linux:** the existing OpenSSH container pattern, building a throwaway container per test
  run with dedicated `wardx_rot_*` users. Covers self change, sudo reconcile, verify, and the
  "device changed, then WardX crashed" recovery.
- **Cisco, Huawei, MikroTik:** simulated CLIs (fake-device dialects reproducing prompts,
  confirmations, rejections and save behaviour), plus MikroTik CHR in a container if available
  (question Q14).
- **Windows:** WinRM against a mocked endpoint in CI, and a real Windows lab VM only if one is
  provided (question Q14).
- **The safety switches themselves:** with the global switch or the target flag off, nothing
  connects. The dev-DB accounts are never touched.

**End to end:** a two-level approval, then check-out, check-in, rotate-after-use waiting for
an emergency holder, then rotation and verify, against the Linux lab container.

## 10. Effort (one engineer)

| Part | Days |
|---|---|
| Engine: state machine, recovery, queue and workers, triggers incl. waiting for release, policy | 5–6 |
| Linux driver and lab container tests | 2 |
| Cisco, Huawei, MikroTik drivers with simulated dialects (CHR if available) | 3–4 |
| Windows driver (WinRM) with mocked tests | 2–3 |
| Verify and reconcile scheduling, reconcile accounts | 2 |
| API, UI, alerts | 3 |
| **Total** | **17–20** |

That's above the plan's 12–15 days, mostly because of the recovery cases and the three
network dialects.

## 11. Design questions (with recommendations)

1. **Q1. Policy levels:** platform default → target override → safe default interval → account
   override. Account overrides can only make a policy *stricter* (longer, more frequent).
   *Recommend: yes.*
2. **Q2. Two switches** (global plus per-target `rotation_allowed`, both off by default).
   *Recommend: yes, plus a "dry run" mode (connect and verify only) for onboarding a new device.*
3. **Q3. New check-outs while a rotation waits for release:** block new normal check-outs and
   sessions; allow emergency ones (they extend the wait); alert after `max_release_wait` (4 h),
   never force. *Recommend: yes.*
4. **Q4. Scheduled rotation while the account is held:** same waiting mechanism. Never rotate
   under a holder. *Recommend: yes.*
5. **Q5. Auto-reconcile on out-of-sync:** off by default per safe; always alert.
   *Recommend: yes.*
6. **Q6. Windows verify for accounts without WinRM rights:** fall back to SMB/NTLM
   authentication. Domain accounts and Kerberos come with a later AD platform.
   *Recommend: WinRM first; add SMB if a lab shows it is needed.*
7. **Q7. MikroTik transport:** API-SSL (8729) first, SSH CLI fallback, since the API keeps
   the password out of `/system history`. *Recommend: yes.*
8. **Q8. Telnet-only devices:** refuse rotation (cleartext). *Recommend: refuse in (c).
   Revisit only with a customer requirement.*
9. **Q9. SSH key rotation:** after password rotation, as (c2). *Recommend: later.*
10. **Q10. Version retention:** keep current and previous, the last 5, and any version an open
    check-out references; never delete during rotation. *Recommend: yes. Older versions
    destroyed only by a separate, audited retention job.*
11. **Q11. Active Directory domain accounts:** a separate AD platform (LDAPS) after the first
    five, because domain password policy and replication delay need their own handling.
    *Recommend: next, not in (c).*
12. **Q12. Maintenance windows per safe** for scheduled rotation (network teams often require
    them). On-demand and after-use ignore the window. *Recommend: optional, default any time.*
13. **Q13. Failed save on a network device:** retry once, then roll back to N and verify; if
    that fails, `needs_attention`. *Recommend: yes.*
14. **Q14. Lab availability:** I can build Linux containers and simulated CLIs myself.
    - Is there a **MikroTik CHR** image we may run?
    - Is there a **Cisco CML/IOSv** or **Huawei eNSP/NE40E** lab?
    - Is there a **Windows Server VM** with WinRM?

    Without them, those drivers ship tested against simulators only, marked "lab-unverified"
    until a real lab run.
15. **Q15. Dependent usages** (Windows services, scheduled tasks, IIS app pools, config files
    using the account): out of (c), next item after (c), since it needs discovery first.
    *Recommend: yes.*
