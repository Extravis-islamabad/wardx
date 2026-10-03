-- Tamper-evident audit trail. Each row carries the SHA-256 of the previous row's
-- hash plus its own canonical content, so editing or removing any row breaks the
-- chain from that point on. The triggers make the table append-only for every
-- role that does not own it; the hash chain catches anyone who bypasses them.

CREATE SCHEMA IF NOT EXISTS audit;

CREATE TABLE IF NOT EXISTS audit.events (
    seq          BIGSERIAL PRIMARY KEY,
    id           UUID        NOT NULL UNIQUE,
    occurred_at  TIMESTAMPTZ NOT NULL,
    actor_id     UUID,
    actor_name   VARCHAR(150),
    action       VARCHAR(80) NOT NULL,
    object_type  VARCHAR(40),
    object_id    UUID,
    outcome      VARCHAR(20) NOT NULL DEFAULT 'success',
    source_ip    VARCHAR(64),
    details      JSONB       NOT NULL DEFAULT '{}',
    prev_hash    CHAR(64)    NOT NULL,
    hash         CHAR(64)    NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_audit_occurred ON audit.events (occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_object ON audit.events (object_type, object_id);
CREATE INDEX IF NOT EXISTS ix_audit_actor ON audit.events (actor_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS ix_audit_action ON audit.events (action, occurred_at DESC);

CREATE OR REPLACE FUNCTION audit.forbid_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'audit.events is append-only (% blocked)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_audit_no_update ON audit.events;
CREATE TRIGGER trg_audit_no_update BEFORE UPDATE OR DELETE ON audit.events
    FOR EACH ROW EXECUTE FUNCTION audit.forbid_change();

DROP TRIGGER IF EXISTS trg_audit_no_truncate ON audit.events;
CREATE TRIGGER trg_audit_no_truncate BEFORE TRUNCATE ON audit.events
    FOR EACH STATEMENT EXECUTE FUNCTION audit.forbid_change();
