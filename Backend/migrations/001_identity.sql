-- Local identity: users, roles and login state.
-- gen_random_uuid() is built in from PostgreSQL 13.

CREATE SCHEMA IF NOT EXISTS iam;

CREATE TABLE IF NOT EXISTS iam.users (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    username       VARCHAR(150) NOT NULL,
    email          VARCHAR(255),
    full_name      VARCHAR(255),
    password_hash  TEXT         NOT NULL,
    role           VARCHAR(20)  NOT NULL DEFAULT 'user'
                   CHECK (role IN ('admin', 'approver', 'auditor', 'user')),
    is_active      BOOLEAN      NOT NULL DEFAULT TRUE,
    -- Bumped on logout / password change; tokens carrying an older value are rejected.
    token_version  INTEGER      NOT NULL DEFAULT 0,
    failed_logins  INTEGER      NOT NULL DEFAULT 0,
    locked_until   TIMESTAMPTZ,
    last_login_at  TIMESTAMPTZ,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_users_username ON iam.users (LOWER(username));
