-- MikroTik rotation over API-SSL (ROTATION.md §15): a target can hold a TLS certificate
-- pin next to its SSH host-key pin, each probed, compared and accepted by an
-- administrator. A presented certificate other than the pin is recorded and blocks
-- rotation and verify until a certificate is accepted again. Additive only.

-- The device's management API: port (NULL = the platform default, 8729 for API-SSL) and
-- whether it is TLS. api_tls = FALSE means the device offers only the cleartext API
-- (8728): the target stays vaultable but is non-rotatable, like Telnet.
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS api_port INTEGER;
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS api_tls BOOLEAN NOT NULL DEFAULT TRUE;

-- The pinned certificate (PEM) and its SHA-256 fingerprint over the DER encoding
-- (AA:BB:..., 95 characters).
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS tls_cert_pem TEXT;
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS tls_cert_fingerprint VARCHAR(128);
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS tls_cert_learned_at TIMESTAMPTZ;
-- Set when the device presented another certificate (the fingerprint it presented).
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS tls_cert_mismatch_at TIMESTAMPTZ;
ALTER TABLE inventory.targets ADD COLUMN IF NOT EXISTS tls_cert_mismatch_fingerprint VARCHAR(128);

-- Which channel a rotation step used on the device (api-ssl, ssh), when it used one.
ALTER TABLE access.rotation_job_steps ADD COLUMN IF NOT EXISTS channel VARCHAR(16);
