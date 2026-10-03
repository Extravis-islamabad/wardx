-- Access requests (approval workflow) and credential check-outs.

CREATE SCHEMA IF NOT EXISTS access;

CREATE TABLE IF NOT EXISTS access.requests (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id        UUID        NOT NULL REFERENCES inventory.accounts (id) ON DELETE CASCADE,
    requester_id      UUID        NOT NULL REFERENCES iam.users (id),
    reason            TEXT        NOT NULL,
    ticket_ref        VARCHAR(100),
    duration_minutes  INTEGER     NOT NULL CHECK (duration_minutes BETWEEN 1 AND 1440),
    status            VARCHAR(20) NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'approved', 'denied', 'cancelled', 'expired', 'used')),
    decided_by        UUID        REFERENCES iam.users (id),
    decided_at        TIMESTAMPTZ,
    decision_note     TEXT,
    -- Pending: deadline for a decision. Approved: deadline to start the check-out.
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_requests_status ON access.requests (status, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_requests_requester ON access.requests (requester_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_requests_open_expiry ON access.requests (expires_at)
    WHERE status IN ('pending', 'approved');
-- One open request per person per account.
CREATE UNIQUE INDEX IF NOT EXISTS uq_requests_open ON access.requests (account_id, requester_id)
    WHERE status IN ('pending', 'approved');

CREATE TABLE IF NOT EXISTS access.checkouts (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_id      UUID        NOT NULL REFERENCES inventory.accounts (id) ON DELETE CASCADE,
    user_id         UUID        NOT NULL REFERENCES iam.users (id),
    request_id      UUID        REFERENCES access.requests (id),
    reason          TEXT        NOT NULL,
    secret_version  INTEGER     NOT NULL,
    checked_out_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    checked_in_at   TIMESTAMPTZ,
    closed_by       UUID        REFERENCES iam.users (id),
    status          VARCHAR(20) NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'returned', 'expired', 'revoked'))
);

CREATE INDEX IF NOT EXISTS ix_checkouts_active_account ON access.checkouts (account_id)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS ix_checkouts_active_expiry ON access.checkouts (expires_at)
    WHERE status = 'active';
CREATE INDEX IF NOT EXISTS ix_checkouts_user ON access.checkouts (user_id, checked_out_at DESC);
-- A person holds at most one active check-out of an account.
CREATE UNIQUE INDEX IF NOT EXISTS uq_checkouts_active_user ON access.checkouts (account_id, user_id)
    WHERE status = 'active';
