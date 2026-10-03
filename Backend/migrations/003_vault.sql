-- Envelope-encrypted secrets. Each version has its own data key (DEK), wrapped by
-- the key-encryption key (KEK) named in kek_id. Plaintext never touches the database.

CREATE SCHEMA IF NOT EXISTS vault;

CREATE TABLE IF NOT EXISTS vault.secrets (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_type   VARCHAR(30) NOT NULL,
    owner_id     UUID        NOT NULL,
    version      INTEGER     NOT NULL CHECK (version > 0),
    ciphertext   BYTEA       NOT NULL,
    nonce        BYTEA       NOT NULL,
    wrapped_dek  BYTEA       NOT NULL,
    dek_nonce    BYTEA       NOT NULL,
    kek_id       VARCHAR(64) NOT NULL,
    created_by   UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (owner_type, owner_id, version)
);

CREATE INDEX IF NOT EXISTS ix_secrets_kek ON vault.secrets (kek_id);
