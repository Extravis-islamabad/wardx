# Phase 1 (c) Rotation engine and platforms: spec (draft for review)

Status: **approved 2026-10-28** with the decisions in §11. Build order: plugin interface and the
failure-handling core (tests for every recovery path) → Linux → MikroTik → Windows → Cisco →
Huawei. **Review stop:** after the core and the Linux driver work end to end in a lab container.
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
   the rotation, and the credential is never sent.
   - **Telnet-only devices are never rotated.** They can still be vaulted, and are flagged
     `non-rotatable (Telnet)` in the API and UI; a rotate request on them is refused with that
     reason.
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
  - `ambiguous` (the command was sent, but the connection dropped before a definite answer);
  - `blocked_by_dependents` (Windows: the account runs services, tasks or app pools).
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
| **MikroTik RouterOS** | API-SSL 8729 only, pinned certificate (§15) | `/password` via the API | `/user/set` via the API, as an admin user | not needed | new API login; SSH only if API-SSL is off |

Device notes the drivers must handle:
- **Cisco:** the `?` key triggers help, and some IOS versions cap secret length. The policy
  below avoids `?`, and driver tests cover the length cap.
- **Huawei:** VRP enforces password history and "can't contain the username". A
  `rejected_by_device` result maps to a clear message.
- **MikroTik:** commands typed over SSH can land in `/system history`. The API avoids that,
  which is why it is preferred (question Q7).
  - **RouterOS accepts any SSH password while an account's password is empty** (found while
    setting up the lab). So the MikroTik `verify` never treats a successful login alone as
    proof: it also logs in once with a deliberately wrong password and requires that to be
    refused, and refuses to promote if it isn't.
- **Windows: dependent usages block rotation (Q15).** Before any change, the driver checks
  whether the account runs a **service** (`Win32_Service.StartName`), a **scheduled task**
  (`Get-ScheduledTask` principal) or an **IIS application pool** (`processModel.userName`, when
  the WebAdministration module is present). If any match, the rotation is refused before the
  device is touched, with outcome `blocked_by_dependents` and a reason naming each dependent.
  Rotating them along with the password comes later (§11, Q15).

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
  `rotation_status`, `rotate_after_use`. The existing `rotation_interval_days`,
  `password_length`, `last_rotated_at` and `last_rotation_status` are kept.
  `rotate_after_checkin` was merged into `rotate_after_use` and dropped (§14, fix 3).
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
- **MikroTik:** the CHR 7.25 lab container (`lab/`), plus a simulated dialect for edge cases.
- **Cisco, Huawei:** simulated CLIs (prompts, confirmations, rejections, save behaviour), marked
  **lab-unverified** until an office lab device is confirmed. Never a production or customer
  device.
- **Windows:** WinRM against a mocked endpoint in CI, including the dependent-usage refusal
  (service, scheduled task, app pool each block rotation, with the reason). A real Windows
  Server lab is still open (see `lab/README.md`): this host is Apple Silicon and there is no
  ARM64 Windows Server evaluation build.
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

## 11. Decisions (answered in review, 2026-10-28)

1. **Q1. Policy levels:** platform default → target override → safe default interval → account
   override; account overrides can only make a policy stricter.
2. **Q2. Two switches** (global plus per-target `rotation_allowed`, both off by default), plus a
   dry-run mode (connect and verify only).
3. **Q3. New check-outs while a rotation waits for release:** normal ones blocked; emergency
   ones allowed and extend the wait; alert after `max_release_wait` (4 h); never forced.
4. **Q4. Scheduled rotation while held:** the same waiting mechanism; never under a holder.
5. **Q5. Auto-reconcile on out-of-sync:** off by default per safe; always alert.
6. **Q6. Windows verify:** WinRM first; SMB/NTLM fallback only if the lab shows it's needed.
7. **Q7. MikroTik:** API-SSL first, SSH CLI fallback. Narrowed by the owner during the build
   (§15): changes only over API-SSL; SSH is a fallback for the verify login only.
8. **Q8. Telnet-only devices:** never rotated; vaulted and flagged `non-rotatable (Telnet)`.
9. **Q9. SSH key rotation:** later, as (c2).
10. **Q10. Version retention:** current and previous, the last 5, and any version an open
    check-out references; never deleted during rotation; older ones only by a separate,
    audited retention job.
11. **Q11. Active Directory domain accounts:** a separate AD platform, scheduled **immediately
    after (c)** in the roadmap.
12. **Q12. Maintenance windows:** optional per safe, default any time; on-demand and after-use
    ignore them.
13. **Q13. Failed save on a network device:** retry once, roll back to N and verify, else
    `needs_attention`.
14. **Q14. Labs:** Linux containers and MikroTik CHR set up (`lab/`). Windows Server: pending
    (Apple Silicon host). Cisco and Huawei: simulators, **lab-unverified**, until the owner
    confirms an office lab device. **Never** a production or customer device.
15. **Q15. Dependent usages:** rotating them is out of (c). The Windows driver must detect
    services, scheduled tasks and IIS app pools running as the account and refuse rotation
    with a clear reason (§2), with a test.

## 12. Additions from the product owner (2026-10-28, during the build)

### 12.1 Negative check in every verify (all platforms)

- After a successful login with the password being verified, the core verify flow makes
  **exactly one** login with a deliberately wrong password: freshly generated per verify,
  never stored or logged. It must be **refused** before the verify counts.
  - One wrong attempt per verify run, never retried, so lockout policies (pam_faillock,
    Windows lockout, RouterOS login limits) are not tripped.
  - Drivers do not implement it: the engine calls `driver.verify` twice (real secret,
    then the wrong one). Logins send the credential once per attempt (one method, no
    keyboard-interactive-then-password retry), so one wrong attempt is one failure.
  - Recovery decisions inside the state machine (§5 "verify C, then N") are positive
    logins only; promotion always goes through the final verify, which carries the single
    negative check. So a rotation run makes at most one wrong attempt.
- **Wrong password accepted → `verify_untrustworthy`.**
  - In a rotation, the device already holds the new password, so the candidate **is**
    promoted (accounts.secret_version = C; the previous version is kept), but it is not
    verified: sync state `verify_untrustworthy`, `last_verified_at` unchanged, job and
    `last_rotation_status` = `changed_unverified`, a high alert and an audit event with
    the safe.
  - While `verify_untrustworthy`: new **normal** check-outs and gateway sessions are refused
    (409 `verify_untrustworthy`, with the reason). Break-glass still works and returns the
    current (new) password. Scheduled rotations and verifies skip the account, and an
    on-demand verify is refused: an administrator reviews it.
  - Review, both needing `manage_accounts` on the account's safe:
    - **Confirm** (`POST /accounts/{id}/rotation/confirm`): accepting a known risk, so it
      needs a written reason of at least **20 characters** (as break-glass). It is stored
      and audited with the safe. The confirming administrator must not be the one who
      requested that rotation (enforced). The account becomes **`confirmed_untrustworthy`**
      (not `in_sync`): normal access works again and the untrustworthy alert is
      acknowledged, but the account stays on the dashboard ("confirmed despite failed
      negative check": who, when, reason) until a **later clean verify** (positive login
      and the wrong password refused) moves it to `in_sync`, audited as
      `rotation.accepted_risk_cleared`. A later verify where the wrong password is accepted
      again puts it back to `verify_untrustworthy` (blocked, new alert). Inconclusive or
      unreachable verifies leave it `confirmed_untrustworthy`.
    - **Reconcile**: the normal reconcile flow; it clears the state only when it ends in a
      clean verify, negative check included.
- **Inconclusive** (the wrong-password attempt timed out or the device was unreachable):
  the rotation stays unverified (current = new version, sync state `unverified`, job
  `changed_unverified`). The positive login is retried on the normal verify schedule,
  and the negative check runs again only then: never as an immediate retry, never more
  than once per verify run. The schedule counts from `last_verify_attempt_at`.

### 12.2 Onboarding check: empty passwords

- WardX refuses to store an empty or blank password for a password account (422
  `empty_secret`), on create, on set secret and on resolving a job by hand.
- Existing empty ones are flagged `high_risk_empty_password` by the scheduler's scan
  (each stored version is looked at once): high alert, audit with the safe, shown on the
  account and on the dashboard. Setting or rotating to a real password clears the flag.
  A verify or rotation that finds an empty current password flags it and stops.
- **On the device, per platform:**
  - **Linux:** not probed directly. The lab's reconcile account may only run
    `chpasswd` through sudo (reading `/etc/shadow` would widen sudo), and an SSH login
    with an empty password is refused by OpenSSH's default `PermitEmptyPasswords no`
    whatever the account's password is, so a probe proves nothing and would spend the
    one-wrong-attempt budget. Instead, a clean verify (stored non-empty password works,
    a wrong one is refused) proves the device password is that non-empty value.
  - **MikroTik (built, §15):** a login with an empty password being accepted means it is
    empty (and the negative check catches "accepts anything").
  - **Windows, Cisco, Huawei (later):** no side-effect-free probe identified yet; the
    clean verify is the evidence. Recorded per driver when built.

## 13. Implementation notes and judgment calls (core and Linux, 2026-10-28)

Where the spec left a question open, the more restrictive choice was taken:

1. **Host keys:** rotation, verify and reconcile never pin a key themselves (no TOFU from
   rotation). A target needs a pin from a gateway session or from the new
   `POST /targets/{id}/host-key/learn` (reads the key, sends no credential, audited).
2. **Blocking states:** new normal check-outs and gateway sessions are refused while the
   account's job is waiting for release, running (claimed, candidate stored, device
   changed, persisted) or **needs attention**, not only while waiting. Emergency
   check-outs are always allowed.
3. **A holder appearing mid-run** (an emergency check-out after the claim): before the
   change is sent, holders are checked again under the account lock; if any, the
   candidate is labelled abandoned and the job goes back to `waiting_release`.
4. **Switch turned off mid-rotation:** a resumed job whose device may hold C goes to
   `needs_attention` instead of failing, so the candidate is never forgotten.
5. **One open job per account of any kind** (verify included, `needs_attention` counts as
   open); resolving releases it. A new final state `resolved` records the resolution
   (keep_current, use_candidate, set_secret, reconcile).
6. **Retries:** a job is claimed at most 3 times (back-off 1, 5, 15 minutes). Exhausted
   retries fail the job when the device is known untouched (C abandoned) and go to
   `needs_attention` when the device state is uncertain.
7. **"Change sent" marker:** `change_sent_at` is committed just before the change command
   is sent, so recovery knows whether the device may hold C.
8. **Policy:** account `password_length` only lengthens; the effective interval is the
   shorter of account and safe; `rotate_after_use` is on if either says so. Policies
   need at least 10 distinct characters and may only use symbols from the safe set.
9. **`rotate_after_checkin`** was first kept and copied into `rotate_after_use`; review
   fix 3 (§14) then merged and dropped it, so `rotate_after_use` is the only setting.
10. **Holders** include check-outs still marked active after their expiry until the sweep
    closes them (at most `expiry_sweep_seconds`).
11. **Dry run** (per request, or `WARDX_ROTATION_DRY_RUN` for all) still needs both
    switches: it connects (as the account or reconcile account) and verifies, including
    the negative check, and changes nothing.
12. **Unreachable verifies** keep an earlier `in_sync`/`out_of_sync`/`unverified`
    conclusion and count; three in a row raise a medium alert.

## 14. Review fixes (2026-10-28, after the core + Linux review)

1. **One rotation per account at a time.** Every rotation, verify or reconcile run holds a
   PostgreSQL advisory lock keyed on the account id, on its own connection, for the whole
   run (`RotationEngine.run`). A second run of the same account does nothing and returns:
   this covers a second worker or scheduler process, and the case where a job's lease
   expired while a slow run was still on the device and another worker claimed it. The
   lock is released when the run ends, and by PostgreSQL if the process dies. Once it
   holds the lock, a run re-reads the job and does nothing if an earlier run already
   finished it. This is on top of the one-open-job-per-account index (which also stops a
   verify starting while a rotation is open) and per-target serialisation.
   Tests: `tests/integration/rotation/test_concurrency.py` (mutation-checked: with the lock
   disabled, the two overlap tests fail).
2. **Scheduler.** Scheduled rotation and scheduled verify are also tested through the real
   background scheduler: APScheduler as built by `src/scheduler/jobs.py`, ticking on its
   own (`tests/integration/rotation/test_scheduler.py`). The test found that
   `build_scheduler` didn't pass its settings to `rotation_tick`, so each tick read
   `get_settings()` instead; it now gets the scheduler's settings.
3. **One after-use setting.** Migration `018_rotation_fixes.sql` merges
   `rotate_after_checkin` into `rotate_after_use` (TRUE in either stays TRUE), then drops
   `rotate_after_checkin`. No code, schema, API or UI reads the old column.
4. **Host keys: probe, compare, accept.**
   - `POST /targets/{id}/host-key/probe` reads the key the device presents without
     authenticating (no credential is sent) and returns its `SHA256:` fingerprint, key type,
     the pinned fingerprint and any recorded mismatch. It pins nothing.
   - `POST /targets/{id}/host-key/accept {fingerprint}` re-reads the key and pins it only if
     the device still presents exactly the fingerprint the administrator compared; a key
     swapped in between is refused (409) and audited as a failed accept. Accept also
     re-pins after a legitimate change and clears a recorded mismatch. The old one-step
     `learn` endpoint is gone.
   - Probe, accept and reset need `inventory.manage` plus `manage_accounts` on **every** safe
     holding an account on the target (a target with no accounts: `inventory.manage` alone).
   - Learning (`target.host_key_learned`), changing (`target.host_key_changed`, with the old
     and new fingerprints), resetting and mismatches are audited once at target level and
     once per affected safe.
   - A device presenting another key, seen by the gateway, a rotation or a verify, records
     the presented fingerprint on the target (`host_key_mismatch_at`,
     `host_key_mismatch_fingerprint`, migration `019`) and raises one high alert
     (`target.host_key_changed`) per new presented key. Every later rotation and verify of
     that target is refused before connecting. Nothing is ever accepted automatically:
     **reset** clears the pin but not the mismatch, so only an explicit **accept** unblocks
     rotation.
   - The gateway still pins a target's **first-seen** key on its first session (trust on
     first use, existing behaviour); a different key after that is always a mismatch.
     Question open for the product owner: should first use also require an explicit accept?
   - Console: a Host key dialog on each SSH target shows the presented and pinned
     fingerprints and accepts only after the administrator ticks that they compared it on
     the device; the targets list tags a changed key in red.
   Tests: `tests/integration/rotation/test_host_keys.py`, plus the gateway mismatch test.
5. **Break-glass while a rotation needs attention or is untrustworthy.** Normal check-outs
   and sessions are blocked; break-glass is never blocked by rotation. It always reveals the
   account's **current** version (`accounts.secret_version`, the vault's source of truth),
   never an unpromoted candidate, and returns a `notice`:
   - job needs attention: names the current version and the candidate version the device
     may hold instead (versions only, never a value), and says both are kept until an
     administrator resolves the job;
   - last verify untrustworthy: says the current version is stored but not verified.
   Tests: `tests/integration/rotation/test_break_glass_rotation.py`.

## 15. MikroTik driver (2026-10-29)

Owner's additions for this driver: passwords change **only over API-SSL with a pinned
certificate**; SSH is used only for the verify login and only when API-SSL is not enabled;
the cleartext API (8728) is refused like Telnet; both identities must be pinned; a mismatch on
either blocks, and nothing ever falls back to another channel because an identity check failed.

### 15.1 Design

- **Two pinned identities per target.** Next to the SSH host key, a MikroTik target pins its
  API-SSL certificate: the PEM and the SHA-256 of its DER encoding (`AA:BB:…`). Migration
  `020_tls_cert_pin.sql` adds `api_port` (NULL = 8729), `api_tls` (FALSE = cleartext API only),
  `tls_cert_pem`, `tls_cert_fingerprint`, `tls_cert_learned_at`, `tls_cert_mismatch_at`,
  `tls_cert_mismatch_fingerprint`, and `access.rotation_job_steps.channel`.
- **The Host key flow, for certificates.** `POST /targets/{id}/tls-cert/probe` (TLS handshake
  only: no API word, no credential; pins nothing), `/accept {fingerprint}` (re-reads and pins
  only if the device still presents exactly that fingerprint; 64 hex digits, colons optional,
  so the RouterOS spelling can be pasted), `/reset` (clears the pin, never a mismatch). Same
  permissions as host keys: `inventory.manage` plus `manage_accounts` on every safe with an
  account on the target; audited once at target level and once per safe
  (`target.tls_cert_learned|changed|reset|accept|mismatch`). The shared rules live in
  `TargetIdentityService`. The console's Host key dialog shows both identities.
- **Trust.** `src/transport/routeros_api.py` connects with a `CERT_REQUIRED` context whose only
  trust anchor is the pinned certificate (partial chain allowed, expiry checked, host name not
  checked: identity is the pin), then compares the presented fingerprint with the pin before
  the first API word. Certificate verification is never disabled; the only unverified read is
  the probe (and, after a failed pin check, a re-read of what was presented), neither of which
  sends anything.
- **Order of checks, per connection:** refuse unless both pins exist and `api_tls` → TLS
  handshake that only the pinned certificate passes → compare the SSH host key the device
  presents (read without authenticating) → one `/login`. A certificate mismatch therefore
  never opens an SSH connection.
- **Device steps.** Self change: `/password` with `old-password`, `new-password`,
  `confirm-new-password` as API attributes. Reconcile: `/user/print ?name=` then `/user/set
  =.id= =password=` as the reconcile account. Persist: not needed. Verify: one API-SSL login.
  Transcripts show `=password=****`; every secret is also redacted by the transcript.
- **Engine.** New outcomes `channel_unavailable` (API-SSL refused, closed or not TLS: the job
  goes to `needs_attention` with exactly "API-SSL not enabled on device"; nothing is sent) and
  `refused` (a precondition failed before sending: the job fails). A `host_key_mismatch`
  carries which identity failed and is recorded on the target (SSH: `host_key_mismatch_*`,
  TLS: `tls_cert_mismatch_*`, one high `target.tls_cert_changed` alert per new certificate);
  every later rotation and verify is refused before connecting until an explicit accept.
  Each step records its channel (`api-ssl`, `ssh`).
- **Empty passwords (§12.2).** When the stored password is refused over the API, the driver
  makes one API-SSL login with an empty password (`empty_password_probe`). Accepted means the
  device password is empty: the account is flagged `high_risk_empty_password` (high alert) and
  the job stops. The probe takes the place of the run's single negative check (which only
  follows an accepted login), so a run still makes at most one login with a password WardX did
  not store. Never over SSH, where such an account accepts anything; there the negative check
  catches it.

### 15.2 Findings on the CHR (RouterOS 7.25)

1. `/password` over the API works for an account with the `password` policy (group `read`
   has it); a wrong old password answers `failure: Bad old password!`.
2. Login refusal answers `invalid user name or password (6)`. A user without rights calling
   `/user/set` gets `not enough permissions (9)`.
3. An empty-password account: the API accepts only the empty password; SSH accepts any.
4. Passwords set over the API appeared neither in `/system history` (its redo/undo hold no
   password) nor in `/log` (it records "password changed by <user>"). Checked by the lab test
   after each self change; not guaranteed by MikroTik.
5. With api-ssl disabled, the QEMU-forwarded port accepts TCP and resets during the TLS
   handshake; the plain API port fails TLS with `WRONG_VERSION_NUMBER`. Both are "API-SSL not
   enabled on device"; only a TLS ClientHello is ever sent.
6. `/certificate sign` of a self-signed certificate fails with `CA not found` unless
   `key-usage` includes `key-cert-sign` (the onboarding doc's Option B was fixed).
7. Rapid repeated SSH logins as admin were refused (`Permission denied`, nothing logged on the
   device); the lab helper keeps one SSH connection per run.

### 15.3 Judgment calls (the more restrictive choice where the spec was silent)

1. **Only a refusal falls back to SSH for verify.** A timeout is `unreachable` (retried later),
   never an SSH fallback. A certificate mismatch, refusal or any device answer never falls back.
2. **API-SSL off during a rotation:** `needs_attention` as specified; the candidate is kept
   unpromoted for the administrator's resolution, never sent over SSH.
3. **The SSH host key is compared on every API-SSL connection**, after the certificate check.
   A different key blocks and is recorded; an unreadable one is noted in the transcript and
   does not block, because no credential ever goes over SSH on that path.
4. **A pinned certificate that no longer verifies** (e.g. expired) is `refused`, not recorded
   as a mismatch and never re-accepted automatically: renew it on the device and accept the
   new one.
5. **Login result:** only the explicit "invalid user name or password" counts as refused;
   any other answer (fatal, lost connection, other trap) is inconclusive, so a negative check
   can never look clean by accident.
6. **Cleartext API:** `api_tls = false` makes the target `non-rotatable (cleartext API)`
   (vaultable, refused at request time, no certificate probe). There is no code path that
   speaks the plain API.
7. **Missing pins** are refused at request time (409 "learn the device identity first") and
   again by the engine for jobs queued earlier; a recorded mismatch keeps the existing
   behaviour (queued, then refused by the engine before connecting).
8. **No trust on first use for certificates.** Unlike the gateway's first-seen SSH key, a
   certificate is pinned only by an explicit accept.
9. **Reconcile accounts** need `write` and `policy` (built-in group `full` in the lab); a
   permission error is reported as such, never retried with another account.

### 15.4 Tests and limitations

- `tests/unit/transport/test_routeros_api.py`: word encoding, pin checked before any word,
  wrong certificate, wrong fingerprint, expired pin, closed port, cleartext service, timeout,
  traps, fatal, `!empty`, lost connection, redaction. A local TLS server with a certificate
  generated per run; its key touches disk only under `lab/.secrets/` and is deleted at once.
- `tests/integration/rotation/test_tls_certs.py`: the pin flow and the driver against a
  simulated RouterOS (no CHR needed).
- `tests/integration/rotation/test_mikrotik_lab.py` and `test_mikrotik_e2e.py`: against the
  CHR, skipped with the reason when Docker, the container or its API-SSL is unavailable. They
  create and remove only `wardx_rot_*` users, may disable api-ssl or swap in a temporary
  certificate generated on the device, and always restore both.
- Limitations: only RouterOS 7.25 (CHR) tested; the ambiguous-change recovery is covered by
  the engine tests, not provoked on the CHR; the console dialog was checked by type-check and
  build, not in a browser.
