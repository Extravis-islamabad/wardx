-- A target whose SSH host key changed is blocked for rotation and verify until an
-- administrator re-learns the key after comparing fingerprints (ROTATION.md §14, fix 4).

ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS host_key_mismatch_at TIMESTAMPTZ;
-- The fingerprint the device presented instead of the pinned one (SHA256:...).
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS host_key_mismatch_fingerprint VARCHAR(128);
