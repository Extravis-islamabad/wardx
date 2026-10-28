-- Phase 1 (b): the approval workflow (docs/phase1/SAFES_AND_APPROVALS.md, section (b)).
--
-- Approval policy moves from the per-account requires_approval flag (kept, no longer
-- read) to the safe: approval_required, ordered approval levels, ticket mode and
-- pattern, approval window, single or multi use, level timeout. Requests record their
-- level, the policy they run under, and one decision per person.
-- In-app notifications live in notify.notifications.
--
-- Nothing is dropped or rewritten; accounts move and rows are added only.

-- ── Safe policy ──
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS approval_required BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS ticket_mode VARCHAR(10) NOT NULL DEFAULT 'off';
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_ticket_mode;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_ticket_mode
    CHECK (ticket_mode IN ('off', 'optional', 'required'));
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS ticket_pattern VARCHAR(200);
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS approval_window_minutes INTEGER NOT NULL DEFAULT 120;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_window;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_window
    CHECK (approval_window_minutes BETWEEN 1 AND 10080);
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS approval_multi_use BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE inventory.safes ADD COLUMN IF NOT EXISTS level_timeout_hours INTEGER NOT NULL DEFAULT 24;
ALTER TABLE inventory.safes DROP CONSTRAINT IF EXISTS ck_safes_level_timeout;
ALTER TABLE inventory.safes ADD CONSTRAINT ck_safes_level_timeout
    CHECK (level_timeout_hours BETWEEN 1 AND 720);

CREATE TABLE IF NOT EXISTS inventory.safe_approval_levels (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    safe_id             UUID        NOT NULL REFERENCES inventory.safes (id) ON DELETE CASCADE,
    position            INTEGER     NOT NULL CHECK (position BETWEEN 1 AND 10),
    required_approvals  INTEGER     NOT NULL DEFAULT 1 CHECK (required_approvals BETWEEN 1 AND 10),
    -- safe_approvers: safe members holding 'approve'; user / group: that user or directory
    -- group, which must also hold 'approve' on the safe.
    approver_type       VARCHAR(20) NOT NULL
                        CHECK (approver_type IN ('safe_approvers', 'user', 'group')),
    approver_key        TEXT,
    CHECK ((approver_type = 'safe_approvers') = (approver_key IS NULL)),
    UNIQUE (safe_id, position)
);

-- ── Requests: level progress, the policy they run under, uses ──
ALTER TABLE access.requests ADD COLUMN IF NOT EXISTS current_level INTEGER NOT NULL DEFAULT 1;
ALTER TABLE access.requests ADD COLUMN IF NOT EXISTS level_started_at TIMESTAMPTZ;
-- Snapshot of the safe's policy when the request was made: levels, window, multi-use,
-- timeout. Later policy edits never change a request in flight.
ALTER TABLE access.requests ADD COLUMN IF NOT EXISTS policy JSONB;
ALTER TABLE access.requests ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE access.requests ADD COLUMN IF NOT EXISTS uses INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS access.request_decisions (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id   UUID        NOT NULL REFERENCES access.requests (id) ON DELETE CASCADE,
    level        INTEGER     NOT NULL,
    approver_id  UUID        NOT NULL REFERENCES iam.users (id),
    approve      BOOLEAN     NOT NULL,
    note         TEXT,
    decided_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- One decision per person per request: nobody approves at two levels.
    UNIQUE (request_id, approver_id)
);

-- ── Notifications (in-app only) ──
CREATE SCHEMA IF NOT EXISTS notify;

CREATE TABLE IF NOT EXISTS notify.notifications (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID        NOT NULL REFERENCES iam.users (id),
    kind         VARCHAR(40) NOT NULL,
    title        TEXT        NOT NULL,
    body         TEXT,
    object_type  VARCHAR(40),
    object_id    UUID,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    read_at      TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_notifications_user ON notify.notifications (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notify.notifications (user_id)
    WHERE read_at IS NULL;

-- ── Migration of the retired requires_approval flag ──
-- A "Default (approval required)" safe with the Default safe's members and one level of
-- one approval from safe members holding 'approve'. Created even when no account needs it,
-- so it has a fixed id everywhere.
DO $$
DECLARE
    approval_safe CONSTANT UUID := '00000000-0000-0000-0000-000000005aa1';
    default_safe  CONSTANT UUID := '00000000-0000-0000-0000-000000005afe';
    safe_name TEXT := 'Default (approval required)';
BEGIN
    IF NOT EXISTS (SELECT 1 FROM inventory.safes WHERE id = approval_safe) THEN
        -- Never collide with a safe an administrator already named this way.
        IF EXISTS (SELECT 1 FROM inventory.safes WHERE LOWER(name) = LOWER(safe_name)) THEN
            safe_name := safe_name || ' (migrated)';
        END IF;
        INSERT INTO inventory.safes (id, name, description, approval_required)
        VALUES (approval_safe, safe_name,
                'Accounts that required approval before approval moved to safe policies', TRUE);
        INSERT INTO inventory.safe_members (safe_id, principal_type, principal_key, permissions)
            SELECT approval_safe, principal_type, principal_key, permissions
            FROM inventory.safe_members WHERE safe_id = default_safe
        ON CONFLICT (safe_id, principal_type, principal_key) DO NOTHING;
        INSERT INTO inventory.safe_approval_levels
            (safe_id, position, required_approvals, approver_type)
        VALUES (approval_safe, 1, 1, 'safe_approvers')
        ON CONFLICT (safe_id, position) DO NOTHING;
    END IF;

    UPDATE inventory.accounts SET safe_id = approval_safe
        WHERE requires_approval AND safe_id = default_safe;

    -- requires_approval accounts an administrator already put in another safe: that safe
    -- now requires approval (the more restrictive reading), with the same default level.
    INSERT INTO inventory.safe_approval_levels (safe_id, position, required_approvals, approver_type)
        SELECT DISTINCT a.safe_id, 1, 1, 'safe_approvers'
        FROM inventory.accounts a JOIN inventory.safes s ON s.id = a.safe_id
        WHERE a.requires_approval AND NOT s.approval_required
    ON CONFLICT (safe_id, position) DO NOTHING;
    UPDATE inventory.safes SET approval_required = TRUE
        WHERE id IN (SELECT safe_id FROM inventory.accounts WHERE requires_approval);
END
$$;

-- Open requests continue at level 1 of their account's safe policy, on its snapshot.
UPDATE access.requests r
SET policy = jsonb_build_object(
        'levels', COALESCE((
            SELECT jsonb_agg(jsonb_build_object(
                       'position', l.position,
                       'required_approvals', l.required_approvals,
                       'approver_type', l.approver_type,
                       'approver_key', l.approver_key) ORDER BY l.position)
            FROM inventory.safe_approval_levels l WHERE l.safe_id = a.safe_id), '[]'::jsonb),
        'approval_window_minutes', s.approval_window_minutes,
        'approval_multi_use', s.approval_multi_use,
        'level_timeout_hours', s.level_timeout_hours),
    level_started_at = COALESCE(r.level_started_at, r.created_at)
FROM inventory.accounts a JOIN inventory.safes s ON s.id = a.safe_id
WHERE a.id = r.account_id AND r.policy IS NULL;

-- Decisions made before levels existed count as level 1.
INSERT INTO access.request_decisions (request_id, level, approver_id, approve, note, decided_at)
    SELECT id, 1, decided_by, status <> 'denied', decision_note, decided_at
    FROM access.requests
    WHERE decided_by IS NOT NULL AND decided_at IS NOT NULL
ON CONFLICT (request_id, approver_id) DO NOTHING;
UPDATE access.requests SET approved_at = decided_at
    WHERE approved_at IS NULL AND decided_by IS NOT NULL AND status IN ('approved', 'used');
