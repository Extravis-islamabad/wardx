-- Break-glass access and security alerts (docs/phase1/SAFES_AND_APPROVALS.md, section (a)).
--
-- iam.user_permissions: direct per-user grants of global codenames. Only
-- access.emergency for now, and only for local users with MFA (the service checks).
-- A revoke stamps revoked_at; rows are kept as history.
--
-- security.alerts: high-signal events (break-glass grant, revoke and use). Alerts are
-- never deleted, and the only change allowed is acknowledging an unacknowledged alert.

CREATE TABLE IF NOT EXISTS iam.user_permissions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID        NOT NULL REFERENCES iam.users (id),
    codename    VARCHAR(64) NOT NULL CHECK (codename IN ('access.emergency')),
    granted_by  UUID        REFERENCES iam.users (id),
    granted_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    revoked_by  UUID        REFERENCES iam.users (id),
    revoked_at  TIMESTAMPTZ,
    revoke_reason TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_user_permissions_active
    ON iam.user_permissions (user_id, codename) WHERE revoked_at IS NULL;

-- Emergency check-outs (break-glass reveals) are marked.
ALTER TABLE access.checkouts ADD COLUMN IF NOT EXISTS emergency BOOLEAN NOT NULL DEFAULT FALSE;

CREATE SCHEMA IF NOT EXISTS security;

CREATE TABLE IF NOT EXISTS security.alerts (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    severity         VARCHAR(10) NOT NULL CHECK (severity IN ('low', 'medium', 'high')),
    kind             VARCHAR(64) NOT NULL,
    message          TEXT        NOT NULL,
    actor_id         UUID        REFERENCES iam.users (id),
    actor_name       VARCHAR(150),
    object_type      VARCHAR(40),
    object_id        UUID,
    details          JSONB       NOT NULL DEFAULT '{}',
    acknowledged_by  UUID        REFERENCES iam.users (id),
    acknowledged_at  TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_alerts_open ON security.alerts (severity, created_at DESC)
    WHERE acknowledged_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_alerts_created ON security.alerts (created_at DESC);

CREATE OR REPLACE FUNCTION security.guard_alerts() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.acknowledged_at IS NULL
       AND NEW.acknowledged_at IS NOT NULL
       AND (NEW.id, NEW.created_at, NEW.severity, NEW.kind, NEW.message, NEW.actor_id,
            NEW.actor_name, NEW.object_type, NEW.object_id, NEW.details)
           IS NOT DISTINCT FROM
           (OLD.id, OLD.created_at, OLD.severity, OLD.kind, OLD.message, OLD.actor_id,
            OLD.actor_name, OLD.object_type, OLD.object_id, OLD.details)
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'security.alerts are never deleted or rewritten (% blocked)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_alerts_guard ON security.alerts;
CREATE TRIGGER trg_alerts_guard BEFORE UPDATE OR DELETE ON security.alerts
    FOR EACH ROW EXECUTE FUNCTION security.guard_alerts();

DROP TRIGGER IF EXISTS trg_alerts_no_truncate ON security.alerts;
CREATE TRIGGER trg_alerts_no_truncate BEFORE TRUNCATE ON security.alerts
    FOR EACH STATEMENT EXECUTE FUNCTION security.guard_alerts();
