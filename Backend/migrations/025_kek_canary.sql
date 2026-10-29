-- KEK canary (docs/phase1/HA_DR.md §6, D10).
--
-- A small random value wrapped by the key provider under the install's KEK. Every node
-- unwraps it at startup and refuses to start if it cannot, so a node deployed with the
-- wrong KEK fails before it serves a single reveal. Created at install, or on the first
-- start of an existing install (by a node whose KEK opens its secrets). Re-wrapped under
-- the active KEK after a KEK rotation, while the retired KEK is still loaded.

CREATE TABLE IF NOT EXISTS keystore.kek_canary (
    id          SMALLINT     PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    kek_id      VARCHAR(64)  NOT NULL,
    wrap_nonce  BYTEA        NOT NULL,
    wrapped     BYTEA        NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    rewrapped_at TIMESTAMPTZ
);
