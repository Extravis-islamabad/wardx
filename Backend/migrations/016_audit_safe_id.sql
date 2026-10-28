-- The safe an audit event belongs to, recorded when the event is written.
--
-- Nullable and never backfilled: audit.events is append-only (trigger) and every
-- keyed row's hash covers its content, so existing rows are not rewritten. Events
-- written before this migration have no safe_id; the safe-scoped audit falls back to
-- the current account-to-safe mapping for them. For keyed events the value is part
-- of the HMAC'd canonical body when present (src/services/audit/audit_chain.py).
-- Adding a nullable column without a default does not touch existing rows.

ALTER TABLE audit.events ADD COLUMN IF NOT EXISTS safe_id UUID;
CREATE INDEX IF NOT EXISTS ix_audit_safe ON audit.events (safe_id, seq DESC)
    WHERE safe_id IS NOT NULL;
