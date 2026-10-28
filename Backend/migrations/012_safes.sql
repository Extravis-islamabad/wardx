-- Safes: every privileged account belongs to exactly one safe, and safe members
-- (users, directory groups, or, for the migration only, WardX roles) hold up to
-- seven permissions on it. Spec: docs/phase1/SAFES_AND_APPROVALS.md, section (a).
--
-- No data is dropped or rewritten: existing accounts move into a Default safe with
-- a fixed id whose role members keep today's access.

CREATE TABLE IF NOT EXISTS inventory.safes (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         VARCHAR(150) NOT NULL,
    description  TEXT,
    is_active    BOOLEAN      NOT NULL DEFAULT TRUE,
    created_by   UUID         REFERENCES iam.users (id),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_safes_name ON inventory.safes (LOWER(name));

CREATE TABLE IF NOT EXISTS inventory.safe_members (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    safe_id         UUID         NOT NULL REFERENCES inventory.safes (id) ON DELETE CASCADE,
    principal_type  VARCHAR(10)  NOT NULL CHECK (principal_type IN ('user', 'group', 'role')),
    -- user: the user's id; group: the normalised DN; role: the role name.
    principal_key   TEXT         NOT NULL,
    permissions     TEXT[]       NOT NULL DEFAULT '{}'
                    CHECK (permissions <@ ARRAY['list', 'use', 'retrieve', 'manage_accounts',
                                                'manage_members', 'view_audit', 'approve']::TEXT[]),
    created_by      UUID         REFERENCES iam.users (id),
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (safe_id, principal_type, principal_key)
);

CREATE INDEX IF NOT EXISTS ix_safe_members_principal
    ON inventory.safe_members (principal_type, principal_key);

-- The Default safe and its role members (today's access).
INSERT INTO inventory.safes (id, name, description)
VALUES ('00000000-0000-0000-0000-000000005afe', 'Default',
        'Every account that existed before safes were introduced')
ON CONFLICT (id) DO NOTHING;

INSERT INTO inventory.safe_members (safe_id, principal_type, principal_key, permissions)
VALUES
    ('00000000-0000-0000-0000-000000005afe', 'role', 'user',
     ARRAY['list', 'use', 'retrieve']),
    ('00000000-0000-0000-0000-000000005afe', 'role', 'auditor',
     ARRAY['list', 'use', 'retrieve']),
    ('00000000-0000-0000-0000-000000005afe', 'role', 'approver',
     ARRAY['list', 'use', 'retrieve', 'approve']),
    ('00000000-0000-0000-0000-000000005afe', 'role', 'admin',
     ARRAY['list', 'use', 'retrieve', 'manage_accounts', 'manage_members', 'view_audit',
           'approve'])
ON CONFLICT (safe_id, principal_type, principal_key) DO NOTHING;

-- Every account lands in the Default safe; new ones name their safe.
ALTER TABLE inventory.accounts ADD COLUMN IF NOT EXISTS safe_id UUID
    REFERENCES inventory.safes (id) ON DELETE RESTRICT;
UPDATE inventory.accounts SET safe_id = '00000000-0000-0000-0000-000000005afe'
    WHERE safe_id IS NULL;
ALTER TABLE inventory.accounts ALTER COLUMN safe_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_accounts_safe ON inventory.accounts (safe_id);
