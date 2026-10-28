"""SNMP credentials: validated, then sealed in the vault as one JSON document.

SNMPv2c: ``{"version": "2c", "community"}``. SNMPv3: ``{"version": "3", "security_name",
"security_level", "auth_protocol", "auth_password", "priv_protocol", "priv_password"}``,
where the security level decides which fields exist: noAuthNoPriv has neither auth nor
priv fields, authNoPriv has auth only, authPriv has both. Anything else is refused, so a
stored document always reads back exactly as the provider serves it
(docs/phase1/CREDENTIAL_PROVIDER.md §4).
"""

from __future__ import annotations

import json
from typing import Any

from src.core.enums import SecretType
from src.errors.exceptions import AppError

SNMP_TYPES = frozenset({SecretType.SNMP_V2C.value, SecretType.SNMP_V3.value})
SECURITY_LEVELS = ("noAuthNoPriv", "authNoPriv", "authPriv")
AUTH_PROTOCOLS = ("MD5", "SHA", "SHA-224", "SHA-256", "SHA-384", "SHA-512")
PRIV_PROTOCOLS = ("DES", "3DES", "AES", "AES-192", "AES-256")
_AUTH = ("auth_protocol", "auth_password")
_PRIV = ("priv_protocol", "priv_password")


class InvalidSnmpSecret(AppError):
    status_code = 422
    code = "invalid_snmp_secret"


def is_snmp(secret_type: str) -> bool:
    return secret_type in SNMP_TYPES


def _require(doc: dict[str, Any], fields: tuple[str, ...], level: str) -> None:
    missing = [f for f in fields if not str(doc.get(f) or "").strip()]
    if missing:
        raise InvalidSnmpSecret(f"{level} needs {', '.join(missing)}")


def _forbid(doc: dict[str, Any], fields: tuple[str, ...], level: str) -> None:
    present = [f for f in fields if doc.get(f) not in (None, "")]
    if present:
        raise InvalidSnmpSecret(f"{level} does not use {', '.join(present)}")


def snmp_document(secret_type: str, snmp: dict[str, Any]) -> str:
    """The canonical JSON document stored for an SNMP account, or InvalidSnmpSecret."""
    version = str(snmp.get("version") or "")
    if secret_type == SecretType.SNMP_V2C:
        if version != "2c":
            raise InvalidSnmpSecret("An snmp_v2c account stores an SNMPv2c secret")
        community = str(snmp.get("community") or "")
        if not community.strip():
            raise InvalidSnmpSecret("SNMPv2c needs a community")
        return json.dumps({"version": "2c", "community": community}, sort_keys=True)
    if secret_type != SecretType.SNMP_V3 or version != "3":
        raise InvalidSnmpSecret("An snmp_v3 account stores an SNMPv3 secret")
    level = snmp.get("security_level")
    if level not in SECURITY_LEVELS:
        raise InvalidSnmpSecret(f"security_level is one of {', '.join(SECURITY_LEVELS)}")
    _require(snmp, ("security_name",), level)
    if level == "noAuthNoPriv":
        _forbid(snmp, _AUTH + _PRIV, level)
    elif level == "authNoPriv":
        _require(snmp, _AUTH, level)
        _forbid(snmp, _PRIV, level)
    else:
        _require(snmp, _AUTH + _PRIV, level)
    if snmp.get("auth_protocol") not in (None, *AUTH_PROTOCOLS):
        raise InvalidSnmpSecret(f"auth_protocol is one of {', '.join(AUTH_PROTOCOLS)}")
    if snmp.get("priv_protocol") not in (None, *PRIV_PROTOCOLS):
        raise InvalidSnmpSecret(f"priv_protocol is one of {', '.join(PRIV_PROTOCOLS)}")
    keys = ("security_name", "security_level", *_AUTH, *_PRIV)
    doc = {k: snmp[k] for k in keys if snmp.get(k) not in (None, "")}
    return json.dumps({"version": "3", **doc}, sort_keys=True)


def read_snmp_document(plaintext: str) -> dict[str, Any]:
    """A stored SNMP document; an unreadable one counts as no secret (empty dict)."""
    try:
        doc = json.loads(plaintext)
    except ValueError:
        return {}
    return doc if isinstance(doc, dict) else {}
