-- Tenant keys (wrapped only) and the keyed audit chain.
--
-- keystore.tenant_keys is the single-database stand-in for the parent DB's
-- platform.tenant_keys (Backend/TENANCY_KEYS.md §3). Keys are stored only as
-- wrapped by the key provider; the provider's key-encryption key is never in
-- the database.

CREATE SCHEMA IF NOT EXISTS keystore;

CREATE TABLE IF NOT EXISTS keystore.tenant_keys (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id    UUID        NOT NULL,
    purpose      VARCHAR(16) NOT NULL
                 CHECK (purpose IN ('vault', 'backup', 'files', 'audit', 'identity')),
    version      INTEGER     NOT NULL CHECK (version >= 1),
    state        VARCHAR(12) NOT NULL DEFAULT 'active'
                 CHECK (state IN ('active', 'retired', 'compromised', 'destroyed')),
    kek_id       TEXT        NOT NULL,
    wrapped_key  BYTEA,
    wrap_nonce   BYTEA,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    retired_at   TIMESTAMPTZ,
    destroyed_at TIMESTAMPTZ,
    UNIQUE (tenant_id, purpose, version)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_tenant_keys_active
    ON keystore.tenant_keys (tenant_id, purpose) WHERE state = 'active';

-- A key row is never deleted, and its identity and wrapped bytes never change.
-- Only state transitions are allowed (and erasing the bytes when destroyed).
CREATE OR REPLACE FUNCTION keystore.guard_tenant_keys() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'keystore.tenant_keys rows are never deleted';
    END IF;
    IF NEW.tenant_id <> OLD.tenant_id OR NEW.purpose <> OLD.purpose
       OR NEW.version <> OLD.version OR NEW.kek_id <> OLD.kek_id THEN
        RAISE EXCEPTION 'keystore.tenant_keys identity is immutable';
    END IF;
    IF NEW.state <> 'destroyed' AND (NEW.wrapped_key IS DISTINCT FROM OLD.wrapped_key
       OR NEW.wrap_nonce IS DISTINCT FROM OLD.wrap_nonce) THEN
        RAISE EXCEPTION 'keystore.tenant_keys wrapped key is immutable';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_tenant_keys_guard ON keystore.tenant_keys;
CREATE TRIGGER trg_tenant_keys_guard BEFORE UPDATE OR DELETE ON keystore.tenant_keys
    FOR EACH ROW EXECUTE FUNCTION keystore.guard_tenant_keys();

-- NULL = legacy event hashed with plain SHA-256 (before the chain was keyed).
-- Otherwise the version of the tenant's audit key that HMAC'd this event.
ALTER TABLE audit.events ADD COLUMN IF NOT EXISTS key_version INTEGER;
