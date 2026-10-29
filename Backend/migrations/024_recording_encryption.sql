-- Encrypted recordings in object storage (docs/phase1/HA_DR.md §5, §5.1).
--
-- recording_key: the object holding the encrypted recording (recordings/<id>.wxrec).
-- recording_sha256 stays the SHA-256 of the plaintext asciicast (also in the audit chain);
-- recording_ciphertext_sha256 is over the stored object, for storage-level checks.
-- recording_incomplete: cut off (gateway node lost): no final chunk, no final hash.
-- recording_path keeps pointing at a legacy plaintext file until `wardx recordings encrypt`
-- migrates it (recording_migrated_at); the original is removed only by a separate
-- --remove-verified-originals run (recording_original_removed_at).

ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_key TEXT;
ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_encrypted BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_incomplete BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_ciphertext_sha256 CHAR(64);
ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_migrated_at TIMESTAMPTZ;
ALTER TABLE access.sessions ADD COLUMN IF NOT EXISTS recording_original_removed_at TIMESTAMPTZ;
