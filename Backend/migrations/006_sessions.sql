-- Proxied sessions through the WardX gateway, the commands typed in them,
-- command rules, and pinned SSH host keys (trust on first use).

ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS ssh_host_key TEXT;
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS ssh_host_key_fingerprint VARCHAR(128);
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS ssh_host_key_learned_at TIMESTAMPTZ;

-- A rule applies to one account, one target, one platform, or (all three NULL) everywhere.
CREATE TABLE IF NOT EXISTS access.command_rules (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id   UUID        REFERENCES inventory.accounts (id) ON DELETE CASCADE,
    target_id    UUID        REFERENCES inventory.targets (id) ON DELETE CASCADE,
    platform     VARCHAR(40),
    pattern      TEXT        NOT NULL,
    action       VARCHAR(10) NOT NULL DEFAULT 'deny' CHECK (action IN ('deny')),
    description  TEXT,
    is_active    BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by   UUID        REFERENCES iam.users (id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_command_rules_scope
    ON access.command_rules (account_id, target_id, platform) WHERE is_active;

-- Sessions outlive the accounts and targets they used: they are evidence. The
-- names are copied onto the row and the references are cleared on delete.
CREATE TABLE IF NOT EXISTS access.sessions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    checkout_id             UUID        REFERENCES access.checkouts (id) ON DELETE SET NULL,
    user_id                 UUID        NOT NULL REFERENCES iam.users (id),
    account_id              UUID        REFERENCES inventory.accounts (id) ON DELETE SET NULL,
    target_id               UUID        REFERENCES inventory.targets (id) ON DELETE SET NULL,
    account_username        VARCHAR(255) NOT NULL,
    target_name             VARCHAR(255) NOT NULL,
    target_address          VARCHAR(255) NOT NULL,
    protocol                VARCHAR(10) NOT NULL,
    mode                    VARCHAR(10) NOT NULL DEFAULT 'shell' CHECK (mode IN ('shell', 'exec')),
    exec_command            TEXT,
    client_ip               VARCHAR(64),
    gateway_node            VARCHAR(100),
    status                  VARCHAR(20) NOT NULL DEFAULT 'active'
                            CHECK (status IN ('active', 'closed', 'terminated', 'failed')),
    started_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at                TIMESTAMPTZ,
    close_reason            TEXT,
    terminate_requested_by  UUID        REFERENCES iam.users (id),
    terminate_requested_at  TIMESTAMPTZ,
    recording_path          TEXT,
    recording_sha256        CHAR(64),
    recording_bytes         BIGINT,
    bytes_from_target       BIGINT      NOT NULL DEFAULT 0,
    bytes_from_user         BIGINT      NOT NULL DEFAULT 0,
    commands_count          INTEGER     NOT NULL DEFAULT 0,
    blocked_count           INTEGER     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS ix_sessions_started ON access.sessions (started_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_user ON access.sessions (user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_account ON access.sessions (account_id, started_at DESC);
CREATE INDEX IF NOT EXISTS ix_sessions_active ON access.sessions (gateway_node) WHERE status = 'active';

CREATE TABLE IF NOT EXISTS access.session_commands (
    id              BIGSERIAL PRIMARY KEY,
    session_id      UUID        NOT NULL REFERENCES access.sessions (id) ON DELETE CASCADE,
    occurred_at     TIMESTAMPTZ NOT NULL,
    offset_seconds  DOUBLE PRECISION NOT NULL,
    command         TEXT        NOT NULL,
    verdict         VARCHAR(10) NOT NULL CHECK (verdict IN ('allowed', 'blocked')),
    rule_id         UUID
);

CREATE INDEX IF NOT EXISTS ix_session_commands_session ON access.session_commands (session_id, id);
