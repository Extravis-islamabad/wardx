-- Phase 1 (d): the credential provider for MonetX (docs/phase1/CREDENTIAL_PROVIDER.md).
--
-- Additive only: new tables, new columns with defaults, and widened CHECK constraints.
-- No existing row is rewritten or loses data.

-- ── Application identities (non-human principals) ──
CREATE TABLE IF NOT EXISTS iam.apps (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                   VARCHAR(100) NOT NULL,
    description            TEXT,
    -- Public identifier sent with the secret; never changes.
    client_id              VARCHAR(64)  NOT NULL UNIQUE,
    enabled                BOOLEAN      NOT NULL DEFAULT TRUE,
    -- CIDRs the app may call from. Empty = no access at all.
    ip_allowlist           TEXT[]       NOT NULL DEFAULT '{}',
    rate_limit_per_minute  INTEGER      NOT NULL DEFAULT 600
                           CHECK (rate_limit_per_minute BETWEEN 1 AND 100000),
    -- Bumped on disable: every token carrying an older value is refused.
    token_version          INTEGER      NOT NULL DEFAULT 0,
    created_by             UUID         REFERENCES iam.users (id),
    created_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at             TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_apps_name ON iam.apps (LOWER(name));

-- Client secrets: only an argon2id hash and a display prefix are stored.
CREATE TABLE IF NOT EXISTS iam.app_secrets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    app_id       UUID         NOT NULL REFERENCES iam.apps (id) ON DELETE CASCADE,
    -- 1 or 2: an app holds at most two unrevoked secrets (the rotation overlap).
    slot         SMALLINT     NOT NULL CHECK (slot IN (1, 2)),
    secret_hash  TEXT         NOT NULL,
    prefix       VARCHAR(16)  NOT NULL,
    expires_at   TIMESTAMPTZ,
    revoked_at   TIMESTAMPTZ,
    last_used_at TIMESTAMPTZ,
    created_by   UUID         REFERENCES iam.users (id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_app_secrets_slot ON iam.app_secrets (app_id, slot)
    WHERE revoked_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_app_secrets_app ON iam.app_secrets (app_id);

-- Fixed-window counters shared by every API worker (fetch rate limit, failed token
-- attempts per client_id and per source IP).
CREATE TABLE IF NOT EXISTS iam.rate_counters (
    bucket        VARCHAR(160) NOT NULL,
    window_start  TIMESTAMPTZ  NOT NULL,
    hits          INTEGER      NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket, window_start)
);

CREATE INDEX IF NOT EXISTS ix_rate_counters_window ON iam.rate_counters (window_start);

-- ── Safe members: the app principal and the fetch permission ──
ALTER TABLE inventory.safe_members DROP CONSTRAINT IF EXISTS safe_members_principal_type_check;
ALTER TABLE inventory.safe_members DROP CONSTRAINT IF EXISTS ck_safe_members_principal_type;
ALTER TABLE inventory.safe_members ADD CONSTRAINT ck_safe_members_principal_type
    CHECK (principal_type IN ('user', 'group', 'role', 'app'));
ALTER TABLE inventory.safe_members DROP CONSTRAINT IF EXISTS safe_members_permissions_check;
ALTER TABLE inventory.safe_members DROP CONSTRAINT IF EXISTS ck_safe_members_permissions;
ALTER TABLE inventory.safe_members ADD CONSTRAINT ck_safe_members_permissions
    CHECK (permissions <@ ARRAY['list', 'use', 'retrieve', 'manage_accounts', 'manage_members',
                                'view_audit', 'approve', 'fetch']::TEXT[]);
-- fetch only for apps, and apps only fetch.
ALTER TABLE inventory.safe_members DROP CONSTRAINT IF EXISTS ck_safe_members_app_fetch;
ALTER TABLE inventory.safe_members ADD CONSTRAINT ck_safe_members_app_fetch
    CHECK (
        (principal_type = 'app' AND permissions = ARRAY['fetch']::TEXT[])
        OR (principal_type <> 'app' AND NOT ('fetch' = ANY (permissions)))
    );

-- ── Safe settings for app fetches ──
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS allow_app_fetch BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS app_cache_seconds INTEGER NOT NULL DEFAULT 300;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_app_cache_seconds;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_app_cache_seconds
    CHECK (app_cache_seconds BETWEEN 0 AND 3600);

-- ── SNMP secret types ──
ALTER TABLE inventory.accounts DROP CONSTRAINT IF EXISTS accounts_secret_type_check;
ALTER TABLE inventory.accounts DROP CONSTRAINT IF EXISTS ck_accounts_secret_type;
ALTER TABLE inventory.accounts ADD CONSTRAINT ck_accounts_secret_type
    CHECK (secret_type IN ('password', 'ssh_key', 'enable_secret', 'api_key', 'snmp_v2c',
                           'snmp_v3'));
