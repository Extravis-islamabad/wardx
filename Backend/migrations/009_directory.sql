-- Directory (LDAP / Active Directory) sign-in.
-- One configuration row; the service account's bind password lives in
-- vault.secrets (owner_type 'directory_bind'). Users signed in through the
-- directory are created on first sign-in with auth_source 'ldap' and have no
-- usable local password.

ALTER TABLE iam.users ADD COLUMN IF NOT EXISTS auth_source VARCHAR(10) NOT NULL DEFAULT 'local';
ALTER TABLE iam.users DROP CONSTRAINT IF EXISTS ck_users_auth_source;
ALTER TABLE iam.users ADD CONSTRAINT ck_users_auth_source CHECK (auth_source IN ('local', 'ldap'));
-- The directory's distinguished name for the user, refreshed at each sign-in.
ALTER TABLE iam.users ADD COLUMN IF NOT EXISTS external_id TEXT;
ALTER TABLE iam.users ADD COLUMN IF NOT EXISTS directory_synced_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS iam.directory_config (
    id                   SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    enabled              BOOLEAN      NOT NULL DEFAULT FALSE,
    server_url           TEXT         NOT NULL,
    start_tls            BOOLEAN      NOT NULL DEFAULT FALSE,
    verify_tls           BOOLEAN      NOT NULL DEFAULT TRUE,
    ca_cert_pem          TEXT,
    bind_dn              TEXT         NOT NULL,
    bind_secret_version  INTEGER,
    user_base_dn         TEXT         NOT NULL,
    -- {username} is replaced with the RFC 4515-escaped login name.
    user_filter          TEXT         NOT NULL,
    attr_username        VARCHAR(64)  NOT NULL,
    attr_email           VARCHAR(64)  NOT NULL DEFAULT 'mail',
    attr_full_name       VARCHAR(64)  NOT NULL DEFAULT 'displayName',
    -- Optional group search (OpenLDAP groupOfNames); otherwise memberOf is read.
    group_base_dn        TEXT,
    group_filter         TEXT,
    -- [{"group_dn": "...", "role": "admin"}, ...]; the highest role matched wins.
    role_mappings        JSONB        NOT NULL DEFAULT '[]',
    -- Role for directory users in no mapped group; NULL refuses them.
    default_role         VARCHAR(20)  CHECK (default_role IN ('admin', 'approver', 'auditor', 'user')),
    timeout_seconds      INTEGER      NOT NULL DEFAULT 10 CHECK (timeout_seconds BETWEEN 1 AND 60),
    updated_by           UUID         REFERENCES iam.users (id),
    updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);
