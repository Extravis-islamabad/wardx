-- Targets (devices, hosts, databases, consoles) and the privileged accounts on them.

CREATE SCHEMA IF NOT EXISTS inventory;

CREATE TABLE IF NOT EXISTS inventory.targets (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          VARCHAR(255) NOT NULL,
    address       VARCHAR(255) NOT NULL,
    platform      VARCHAR(40)  NOT NULL,
    protocol      VARCHAR(10)  NOT NULL
                  CHECK (protocol IN ('ssh', 'telnet', 'rdp', 'vnc', 'https', 'db')),
    port          INTEGER      NOT NULL CHECK (port BETWEEN 1 AND 65535),
    description   TEXT,
    tags          TEXT[]       NOT NULL DEFAULT '{}',
    -- Id of the matching device in MonetX (or another CMDB) when synced from there.
    external_ref  VARCHAR(255),
    is_active     BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_targets_name ON inventory.targets (LOWER(name));
CREATE INDEX IF NOT EXISTS ix_targets_address ON inventory.targets (address);

CREATE TABLE IF NOT EXISTS inventory.accounts (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_id             UUID         NOT NULL REFERENCES inventory.targets (id) ON DELETE CASCADE,
    username              VARCHAR(255) NOT NULL,
    secret_type           VARCHAR(20)  NOT NULL DEFAULT 'password'
                          CHECK (secret_type IN ('password', 'ssh_key', 'enable_secret', 'api_key')),
    description           TEXT,
    -- 0 = no secret stored yet; otherwise the current version in vault.secrets.
    secret_version        INTEGER      NOT NULL DEFAULT 0,
    requires_approval     BOOLEAN      NOT NULL DEFAULT FALSE,
    exclusive_checkout    BOOLEAN      NOT NULL DEFAULT TRUE,
    max_checkout_minutes  INTEGER      NOT NULL DEFAULT 60
                          CHECK (max_checkout_minutes BETWEEN 1 AND 1440),
    secret_updated_at     TIMESTAMPTZ,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    UNIQUE (target_id, username)
);
