-- High availability (docs/phase1/HA_DR.md §3, §4, §6.1).
--
-- ha.scheduler_leader: one row naming the scheduler node that holds the leader
-- advisory lock (the lock itself decides; this row is for display and audit).
-- ha.conditions: cluster conditions the leader tracks (degraded sync, DR lag), each
-- with the alert it raised while active.

CREATE SCHEMA IF NOT EXISTS ha;

CREATE TABLE IF NOT EXISTS ha.scheduler_leader (
    id          SMALLINT     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    node        VARCHAR(200) NOT NULL,
    term        BIGINT       NOT NULL,
    elected_at  TIMESTAMPTZ  NOT NULL,
    last_seen   TIMESTAMPTZ  NOT NULL
);

CREATE TABLE IF NOT EXISTS ha.conditions (
    kind        VARCHAR(64)  PRIMARY KEY,
    active      BOOLEAN      NOT NULL,
    since       TIMESTAMPTZ  NOT NULL,
    checked_at  TIMESTAMPTZ  NOT NULL,
    details     JSONB        NOT NULL DEFAULT '{}',
    alert_id    UUID
);
