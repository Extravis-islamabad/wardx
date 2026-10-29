-- Gateway node heartbeats (docs/phase1/HA_DR.md §5).
--
-- Each gateway node upserts its row at start and stamps last_seen every few seconds.
-- The scheduler leader ends the live sessions of a node whose heartbeat is stale
-- ("gateway node lost") and closes their check-outs through the normal session-end path,
-- which needs to know whether the session opened its own check-out (owns_checkout).

CREATE TABLE IF NOT EXISTS ha.gateway_nodes (
    node                  VARCHAR(200) PRIMARY KEY,
    started_at            TIMESTAMPTZ  NOT NULL,
    last_seen             TIMESTAMPTZ  NOT NULL,
    host_key_fingerprint  VARCHAR(128) NOT NULL,
    stopped_at            TIMESTAMPTZ
);

ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS owns_checkout BOOLEAN NOT NULL DEFAULT FALSE;
