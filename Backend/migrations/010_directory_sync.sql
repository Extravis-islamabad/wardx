-- Scheduled directory sync: disable leavers without waiting for their next sign-in.

ALTER TABLE iam.directory_config
    ADD COLUMN IF NOT EXISTS sync_interval_minutes INTEGER NOT NULL DEFAULT 60
        CHECK (sync_interval_minutes = 0 OR sync_interval_minutes BETWEEN 5 AND 1440);
-- A run that would disable more than this share of directory users stops untouched.
ALTER TABLE iam.directory_config
    ADD COLUMN IF NOT EXISTS sync_max_disable_percent INTEGER NOT NULL DEFAULT 20
        CHECK (sync_max_disable_percent BETWEEN 1 AND 100);
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ;
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS last_sync_status VARCHAR(20);
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS last_sync_summary JSONB;

-- Why an account is inactive. Sync only ever re-enables accounts it disabled
-- itself; an administrator's decision is never overridden.
ALTER TABLE iam.users ADD COLUMN IF NOT EXISTS disabled_reason VARCHAR(30);
