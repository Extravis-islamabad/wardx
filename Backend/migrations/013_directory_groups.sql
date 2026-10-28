-- Directory groups for safe membership.
--
-- iam.user_group_cache holds each directory user's groups (normalised DNs) as of
-- fetched_at: written at directory sign-in, refreshed through the service account
-- when older than WARDX_GROUP_CACHE_MINUTES, refreshed by directory sync and
-- removed for users the sync disables.
--
-- directory_config gains nested_groups (Active Directory LDAP_MATCHING_RULE_IN_CHAIN,
-- on by default for AD) and the outcome of the most recent directory contact, which
-- the dashboard uses to warn while the directory is unreachable.

CREATE TABLE IF NOT EXISTS iam.user_group_cache (
    user_id     UUID PRIMARY KEY REFERENCES iam.users (id) ON DELETE CASCADE,
    groups      TEXT[]      NOT NULL DEFAULT '{}',
    fetched_at  TIMESTAMPTZ NOT NULL
);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'iam' AND table_name = 'directory_config'
          AND column_name = 'nested_groups'
    ) THEN
        ALTER TABLE iam.directory_config
            ADD COLUMN nested_groups BOOLEAN NOT NULL DEFAULT FALSE;
        -- On by default for Active Directory (the only directory that supports it).
        UPDATE iam.directory_config SET nested_groups = TRUE
            WHERE LOWER(attr_username) = 'samaccountname';
    END IF;
END
$$;

-- NULL until WardX has tried to reach the directory.
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS reachable BOOLEAN;
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS reachability_checked_at TIMESTAMPTZ;
ALTER TABLE iam.directory_config ADD COLUMN IF NOT EXISTS reachability_error TEXT;
