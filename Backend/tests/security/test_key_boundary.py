"""Only the key provider and the envelope do key-encryption-key crypto.

Everything else goes through ``KeyProvider`` (src/keys/provider.py), which is
what lets an HSM, KMS or TPM provider replace the file provider without
touching modules.
"""

from __future__ import annotations

import pathlib
import re

SRC = pathlib.Path(__file__).resolve().parents[2] / "src"

# Files allowed to use AES-GCM / raw cipher primitives directly.
ALLOWED = {
    "keys/file_provider.py",  # the provider itself
    "vault/envelope.py",  # data keys only; KEKs stay inside the provider
}


def _python_files():
    for path in SRC.rglob("*.py"):
        yield path.relative_to(SRC).as_posix(), path.read_text()


def test_only_the_provider_and_envelope_use_cipher_primitives():
    offenders = [
        rel
        for rel, text in _python_files()
        if re.search(r"\bAESGCM\b|hazmat\.primitives\.ciphers", text) and rel not in ALLOWED
    ]
    assert offenders == []


def test_nothing_reaches_into_a_provider_for_raw_keys():
    offenders = [
        rel
        for rel, text in _python_files()
        if not rel.startswith("keys/")
        and re.search(r"\._kek\(|\._keys\b|resolve_vault_kek", text)
        and rel != "core/config.py"
        and rel != "core/app_factory.py"  # loads the KEK into the provider at startup
    ]
    assert offenders == []
