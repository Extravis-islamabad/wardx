"""String enums shared by models, schemas and services."""

from __future__ import annotations

import uuid
from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    APPROVER = "approver"
    AUDITOR = "auditor"
    USER = "user"


class Protocol(StrEnum):
    SSH = "ssh"
    TELNET = "telnet"
    RDP = "rdp"
    VNC = "vnc"
    HTTPS = "https"
    DB = "db"


DEFAULT_PORTS: dict[Protocol, int] = {
    Protocol.SSH: 22,
    Protocol.TELNET: 23,
    Protocol.RDP: 3389,
    Protocol.VNC: 5900,
    Protocol.HTTPS: 443,
    Protocol.DB: 5432,
}


class Platform(StrEnum):
    CISCO_IOS = "cisco_ios"
    CISCO_NXOS = "cisco_nxos"
    HUAWEI_VRP = "huawei_vrp"
    H3C_COMWARE = "h3c_comware"
    JUNIPER_JUNOS = "juniper_junos"
    MIKROTIK_ROUTEROS = "mikrotik_routeros"
    FORTINET_FORTIOS = "fortinet_fortios"
    PALOALTO_PANOS = "paloalto_panos"
    LINUX = "linux"
    WINDOWS = "windows"
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    MSSQL = "mssql"
    GENERIC = "generic"


class SecretType(StrEnum):
    PASSWORD = "password"
    SSH_KEY = "ssh_key"
    ENABLE_SECRET = "enable_secret"
    API_KEY = "api_key"


class RequestStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    USED = "used"


class CheckoutStatus(StrEnum):
    ACTIVE = "active"
    RETURNED = "returned"
    EXPIRED = "expired"
    REVOKED = "revoked"


class KeyPurpose(StrEnum):
    """What a tenant key protects (Backend/TENANCY_KEYS.md §2)."""

    VAULT = "vault"
    BACKUP = "backup"
    FILES = "files"
    AUDIT = "audit"
    IDENTITY = "identity"


class SafePermission(StrEnum):
    """What a safe member may do (docs/phase1/SAFES_AND_APPROVALS.md, section (a))."""

    LIST = "list"
    USE = "use"
    RETRIEVE = "retrieve"
    MANAGE_ACCOUNTS = "manage_accounts"
    MANAGE_MEMBERS = "manage_members"
    VIEW_AUDIT = "view_audit"
    APPROVE = "approve"


class PrincipalType(StrEnum):
    USER = "user"
    GROUP = "group"
    # Migration only: keeps the Default safe's pre-safes access. The UI offers users and groups.
    ROLE = "role"


# The safe every pre-safes account was moved into (migrations/012_safes.sql).
DEFAULT_SAFE_ID = uuid.UUID("00000000-0000-0000-0000-000000005afe")
