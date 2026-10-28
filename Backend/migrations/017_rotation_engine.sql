-- Phase 1 (c): the rotation engine (docs/phase1/ROTATION.md, sections 4 to 7).
--
-- Additive only: no column is dropped or renamed and no existing row loses data.
-- accounts.rotate_after_checkin is kept (no longer read); rotate_after_use replaces
-- it and starts from its value. vault.secrets gets a status label for clarity only:
-- accounts.secret_version stays the source of truth for the current version.

-- ── Targets: the per-target safety switch and policy overrides ──
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS rotation_allowed BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS policy_overrides JSONB NOT NULL DEFAULT '{}';

-- ── Accounts: reconcile account, sync and rotation state, onboarding risk ──
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS reconcile_account_id UUID
    REFERENCES inventory.accounts (id) ON DELETE SET NULL;
ALTER TABLE inventory.accounts DROP CONSTRAINT IF EXISTS ck_accounts_reconcile_not_self;
ALTER TABLE inventory.accounts ADD CONSTRAINT ck_accounts_reconcile_not_self
    CHECK (reconcile_account_id IS NULL OR reconcile_account_id <> id);
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS rotate_after_use BOOLEAN NOT NULL DEFAULT FALSE;
UPDATE inventory.accounts SET rotate_after_use = TRUE
    WHERE rotate_after_checkin AND NOT rotate_after_use;
-- unknown | in_sync | out_of_sync | unreachable | unverified | verify_untrustworthy
-- | confirmed_untrustworthy (an administrator accepted the risk; listed until a clean verify)
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS sync_status VARCHAR(24) NOT NULL DEFAULT 'unknown';
ALTER TABLE inventory.accounts DROP CONSTRAINT IF EXISTS ck_accounts_sync_status;
ALTER TABLE inventory.accounts ADD CONSTRAINT ck_accounts_sync_status
    CHECK (sync_status IN ('unknown', 'in_sync', 'out_of_sync', 'unreachable', 'unverified',
                           'verify_untrustworthy', 'confirmed_untrustworthy'));
-- Who accepted an untrustworthy verify, when and why (cleared by a later clean verify).
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS risk_accepted_by UUID REFERENCES iam.users (id);
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS risk_accepted_at TIMESTAMPTZ;
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS risk_accepted_reason TEXT;
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMPTZ;
-- login (a clean verify) | attested (an administrator confirmed an untrustworthy verify)
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS last_verify_method VARCHAR(12);
-- When a verify last ran, whatever its result: the schedule counts from here, so an
-- inconclusive verify is retried on schedule, never immediately.
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS last_verify_attempt_at TIMESTAMPTZ;
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS unreachable_count INTEGER NOT NULL DEFAULT 0;
-- idle | pending | waiting_release | running | needs_attention
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS rotation_status VARCHAR(20) NOT NULL DEFAULT 'idle';
-- e.g. {high_risk_empty_password}
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS risk_flags TEXT[] NOT NULL DEFAULT '{}';
-- The secret version the empty-password scan last looked at (0 = never).
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS risk_checked_version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE inventory.accounts ALTER COLUMN last_rotation_status TYPE VARCHAR(24);

-- ── Safe rotation policy ──
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS rotate_after_use BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS rotation_interval_days INTEGER;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_rotation_interval;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_rotation_interval
    CHECK (rotation_interval_days IS NULL OR rotation_interval_days BETWEEN 1 AND 3650);
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS verify_interval_hours INTEGER NOT NULL DEFAULT 24;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_verify_interval;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_verify_interval
    CHECK (verify_interval_hours BETWEEN 1 AND 8760);
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS auto_reconcile BOOLEAN NOT NULL DEFAULT FALSE;
-- {"days": [0..6, Monday = 0], "start_hour": 0..23, "end_hour": 1..24} in UTC; NULL = any time.
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS maintenance_window JSONB;
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS max_release_wait_minutes INTEGER NOT NULL DEFAULT 240;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_release_wait;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_release_wait
    CHECK (max_release_wait_minutes BETWEEN 5 AND 10080);

-- ── Rotation jobs: new reasons, states and fields ──
ALTER TABLE access.rotation_jobs DROP CONSTRAINT IF EXISTS rotation_jobs_reason_check;
ALTER TABLE access.rotation_jobs DROP CONSTRAINT IF EXISTS ck_rotation_jobs_reason;
ALTER TABLE access.rotation_jobs ADD CONSTRAINT ck_rotation_jobs_reason
    CHECK (reason IN ('manual', 'schedule', 'checkin', 'after_use', 'reconcile', 'verify',
                      'compromise'));
ALTER TABLE access.rotation_jobs ALTER COLUMN status TYPE VARCHAR(24);
ALTER TABLE access.rotation_jobs DROP CONSTRAINT IF EXISTS rotation_jobs_status_check;
ALTER TABLE access.rotation_jobs DROP CONSTRAINT IF EXISTS ck_rotation_jobs_status;
ALTER TABLE access.rotation_jobs ADD CONSTRAINT ck_rotation_jobs_status
    CHECK (status IN ('pending', 'waiting_release', 'running', 'candidate_stored',
                      'device_changed', 'persisted', 'succeeded', 'changed_unverified',
                      'failed', 'needs_attention', 'resolved', 'cancelled'));
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS secret_versions_touched INTEGER[]
    NOT NULL DEFAULT '{}';
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS note TEXT;
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS dry_run BOOLEAN NOT NULL DEFAULT FALSE;
-- A worker owns a claimed job until lease_until; an expired lease means it crashed.
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;
-- Committed just before the change command is sent: from then on the device may hold C.
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS change_sent_at TIMESTAMPTZ;
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS waiting_since TIMESTAMPTZ;
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS release_alerted_at TIMESTAMPTZ;
-- verified | untrustworthy | inconclusive (the negative check of the final verify)
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS verify_result VARCHAR(16);
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS resolution VARCHAR(20);
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS resolution_note TEXT;
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS resolved_at TIMESTAMPTZ;
ALTER TABLE access.rotation_jobs ADD COLUMN IF NOT EXISTS target_id UUID;
UPDATE access.rotation_jobs j SET target_id = a.target_id
    FROM inventory.accounts a WHERE a.id = j.account_id AND j.target_id IS NULL;

-- At most one open job per account, whatever its state (needs_attention included).
DROP INDEX IF EXISTS access.uq_rotation_open;
CREATE UNIQUE INDEX IF NOT EXISTS uq_rotation_open_job ON access.rotation_jobs (account_id)
    WHERE status IN ('pending', 'waiting_release', 'running', 'candidate_stored',
                     'device_changed', 'persisted', 'needs_attention');
CREATE INDEX IF NOT EXISTS ix_rotation_claimable ON access.rotation_jobs (not_before)
    WHERE status IN ('pending', 'running', 'candidate_stored', 'device_changed', 'persisted');
CREATE INDEX IF NOT EXISTS ix_rotation_target_leased ON access.rotation_jobs (target_id)
    WHERE lease_until IS NOT NULL;

CREATE TABLE IF NOT EXISTS access.rotation_job_steps (
    id              BIGSERIAL PRIMARY KEY,
    job_id          UUID        NOT NULL REFERENCES access.rotation_jobs (id) ON DELETE CASCADE,
    step            VARCHAR(30) NOT NULL,
    outcome         VARCHAR(24) NOT NULL,
    secret_version  INTEGER,
    detail          TEXT,
    -- Device conversation for this step with every secret replaced by ****.
    transcript      TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS ix_rotation_steps_job ON access.rotation_job_steps (job_id, id);

-- ── Vault: version status labels (never inferred; accounts.secret_version decides) ──
ALTER TABLE vault.secrets ADD COLUMN IF NOT EXISTS status VARCHAR(10);
ALTER TABLE vault.secrets DROP CONSTRAINT IF EXISTS ck_secrets_status;
ALTER TABLE vault.secrets ADD CONSTRAINT ck_secrets_status
    CHECK (status IS NULL OR status IN ('current', 'previous', 'candidate', 'abandoned'));
UPDATE vault.secrets s SET status = CASE WHEN s.version = a.secret_version THEN 'current'
                                         ELSE 'previous' END
    FROM inventory.accounts a
    WHERE s.owner_type = 'account' AND s.owner_id = a.id AND s.status IS NULL
      AND s.version <= a.secret_version;
