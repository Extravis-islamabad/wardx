-- Password rotation: per-account policy and a job queue.
--
-- A rotation first stores the new password in vault.secrets as a candidate
-- version above the current one, then changes it on the device, then proves it
-- by logging in. accounts.secret_version moves to the candidate only after that
-- proof, so a failed or interrupted rotation never loses the working password.

ALTER TABLE inventory.accounts
    ADD COLUMN IF NOT EXISTS rotation_interval_days INTEGER
        CHECK (rotation_interval_days BETWEEN 1 AND 3650);
ALTER TABLE inventory.accounts
    ADD COLUMN IF NOT EXISTS rotate_after_checkin BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.accounts
    ADD COLUMN IF NOT EXISTS password_length INTEGER NOT NULL DEFAULT 24
        CHECK (password_length BETWEEN 12 AND 128);
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS last_rotated_at TIMESTAMPTZ;
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS last_rotation_status VARCHAR(20);

CREATE INDEX IF NOT EXISTS ix_accounts_rotation_due ON inventory.accounts (last_rotated_at)
    WHERE rotation_interval_days IS NOT NULL;

CREATE TABLE IF NOT EXISTS access.rotation_jobs (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id         UUID        NOT NULL REFERENCES inventory.accounts (id) ON DELETE CASCADE,
    reason             VARCHAR(20) NOT NULL CHECK (reason IN ('manual', 'schedule', 'checkin')),
    requested_by       UUID        REFERENCES iam.users (id),
    status             VARCHAR(20) NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending', 'running', 'succeeded', 'failed',
                                         'needs_attention', 'cancelled')),
    not_before         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    attempts           INTEGER     NOT NULL DEFAULT 0,
    claimed_by         VARCHAR(100),
    started_at         TIMESTAMPTZ,
    finished_at        TIMESTAMPTZ,
    from_version       INTEGER,
    candidate_version  INTEGER,
    driver             VARCHAR(40),
    detail             TEXT,
    -- Device conversation with every secret replaced by ****.
    transcript         TEXT,
    resolved_by        UUID        REFERENCES iam.users (id),
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- At most one queued or running rotation per account.
CREATE UNIQUE INDEX IF NOT EXISTS uq_rotation_open ON access.rotation_jobs (account_id)
    WHERE status IN ('pending', 'running');
CREATE INDEX IF NOT EXISTS ix_rotation_due ON access.rotation_jobs (not_before)
    WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS ix_rotation_account ON access.rotation_jobs (account_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_rotation_status ON access.rotation_jobs (status, created_at DESC);
