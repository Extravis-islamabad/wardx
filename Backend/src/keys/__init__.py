"""Key management: the master-key provider seam and per-tenant keys.

Every encryption in WardX goes through a ``KeyProvider``; nothing else touches
raw key-encryption keys. Only the file provider exists today; HSM (PKCS#11),
cloud KMS and TPM providers implement the same interface later
(Backend/TENANCY_KEYS.md §4).
"""
