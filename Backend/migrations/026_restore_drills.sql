-- Restore drills (docs/phase1/HA_DR.md §7): each scripted restore into a scratch database
-- records its result here, on the production database; the dashboard shows the latest.

CREATE TABLE IF NOT EXISTS ha.restore_drills (
    id             UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    ran_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    ok             BOOLEAN      NOT NULL,
    restore_point  TIMESTAMPTZ,
    details        JSONB        NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS ix_restore_drills_ran ON ha.restore_drills (ran_at DESC);
