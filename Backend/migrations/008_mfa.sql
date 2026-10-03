-- TOTP multi-factor authentication. The TOTP seed is envelope-encrypted in
-- vault.secrets (owner_type 'mfa_totp', owner_id = user id); this table holds
-- state only. Recovery codes are stored as SHA-256 hashes (they are random,
-- high-entropy strings, so a fast hash is enough) and each works once.

CREATE TABLE IF NOT EXISTS iam.user_mfa (
    user_id          UUID PRIMARY KEY REFERENCES iam.users (id) ON DELETE CASCADE,
    secret_version   INTEGER     NOT NULL,
    enabled          BOOLEAN     NOT NULL DEFAULT FALSE,
    -- Last accepted 30-second step: a code is accepted once, never replayed.
    last_used_step   BIGINT,
    enrolled_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS iam.mfa_recovery_codes (
    id          BIGSERIAL PRIMARY KEY,
    user_id     UUID        NOT NULL REFERENCES iam.users (id) ON DELETE CASCADE,
    code_hash   CHAR(64)    NOT NULL,
    used_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_mfa_recovery_user ON iam.mfa_recovery_codes (user_id)
    WHERE used_at IS NULL;
