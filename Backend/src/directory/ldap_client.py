"""LDAP / Active Directory lookups and password checks (ldap3, synchronous; run in a thread).

Sign-in is search-then-bind: the service account finds exactly one entry for
the login name, then a bind as that entry's DN with the user's password
proves the password. The login name is escaped (RFC 4515) before it goes into
the filter, so ``*`` or ``)(`` cannot widen the search. An empty password is
refused before any bind: many servers treat it as an anonymous bind that
"succeeds".
"""

from __future__ import annotations

import ssl
from collections.abc import Callable
from dataclasses import dataclass, field

import ldap3
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars

ROLE_RANK = {"admin": 4, "approver": 3, "auditor": 2, "user": 1}


class DirectoryError(Exception):
    """The directory could not be used: unreachable, bad service credentials, bad config."""


class DirectoryAuthFailed(Exception):
    """Unknown user, wrong password, ambiguous match, or no WardX role for the user."""


class UserNotFound(DirectoryAuthFailed):
    """No entry matches the login name: in a sync, the person has left."""


class AmbiguousUser(DirectoryAuthFailed):
    """Several entries match: a directory data problem, never a reason to disable."""


@dataclass(frozen=True)
class DirectorySettings:
    server_url: str
    bind_dn: str
    bind_password: str
    user_base_dn: str
    user_filter: str
    attr_username: str
    attr_email: str = "mail"
    attr_full_name: str = "displayName"
    start_tls: bool = False
    verify_tls: bool = True
    ca_cert_pem: str | None = None
    group_base_dn: str | None = None
    group_filter: str | None = None
    role_mappings: tuple[tuple[str, str], ...] = ()
    default_role: str | None = None
    timeout_seconds: int = 10


@dataclass(frozen=True)
class DirectoryUser:
    dn: str
    username: str
    email: str | None
    full_name: str | None
    groups: tuple[str, ...] = field(default_factory=tuple)
    role: str | None = None


ConnectionFactory = Callable[[DirectorySettings, str, str], ldap3.Connection]


def default_connection(settings: DirectorySettings, user: str, password: str) -> ldap3.Connection:
    tls = ldap3.Tls(
        validate=ssl.CERT_REQUIRED if settings.verify_tls else ssl.CERT_NONE,
        ca_certs_data=settings.ca_cert_pem or None,
    )
    server = ldap3.Server(
        settings.server_url,
        use_ssl=settings.server_url.lower().startswith("ldaps://"),
        tls=tls,
        connect_timeout=settings.timeout_seconds,
        get_info=ldap3.NONE,
    )
    return ldap3.Connection(
        server,
        user=user,
        password=password,
        receive_timeout=settings.timeout_seconds,
        read_only=True,
        raise_exceptions=False,
    )


def normalise_dn(dn: str) -> str:
    """Compare DNs case-insensitively and ignoring spaces around separators."""
    return ",".join(part.strip().lower() for part in dn.split(","))


def resolve_role(
    groups: tuple[str, ...], mappings: tuple[tuple[str, str], ...], default: str | None
) -> str | None:
    member_of = {normalise_dn(g) for g in groups}
    matched = [role for group_dn, role in mappings if normalise_dn(group_dn) in member_of]
    if matched:
        return max(matched, key=lambda r: ROLE_RANK.get(r, 0))
    return default


def _first(entry: ldap3.Entry, attr: str) -> str | None:
    if attr not in entry:
        return None
    value = entry[attr].value
    if isinstance(value, list):
        value = value[0] if value else None
    return str(value) if value is not None else None


class DirectoryClient:
    def __init__(
        self, settings: DirectorySettings, factory: ConnectionFactory = default_connection
    ) -> None:
        self.settings = settings
        self.factory = factory

    def _bind(self, user: str, password: str) -> ldap3.Connection | None:
        try:
            # Building the connection can fail too (bad TLS material, socket errors).
            conn = self.factory(self.settings, user, password)
            if self.settings.start_tls:
                conn.open()
                conn.start_tls()
            return conn if conn.bind() else None
        except LDAPException as exc:
            raise DirectoryError(f"Directory unreachable or TLS failed: {exc}") from exc

    def _service(self) -> ldap3.Connection:
        conn = self._bind(self.settings.bind_dn, self.settings.bind_password)
        if conn is None:
            raise DirectoryError("The service account could not bind; check bind DN and password")
        return conn

    def _find(self, conn: ldap3.Connection, username: str) -> ldap3.Entry:
        s = self.settings
        search_filter = s.user_filter.replace("{username}", escape_filter_chars(username))
        attrs = [s.attr_username, s.attr_email, s.attr_full_name, "memberOf"]
        try:
            conn.search(
                s.user_base_dn, search_filter, ldap3.SUBTREE, attributes=attrs, size_limit=2
            )
        except LDAPException as exc:
            raise DirectoryError(f"User search failed: {exc}") from exc
        if not conn.entries:
            raise UserNotFound("no unique directory entry for that login name")
        if len(conn.entries) > 1:
            # The filter is too loose; refuse rather than guess which person this is.
            raise AmbiguousUser("no unique directory entry for that login name")
        return conn.entries[0]

    def _groups(self, conn: ldap3.Connection, entry: ldap3.Entry) -> tuple[str, ...]:
        s = self.settings
        if s.group_base_dn and s.group_filter:
            group_filter = s.group_filter.replace("{user_dn}", escape_filter_chars(entry.entry_dn))
            try:
                conn.search(s.group_base_dn, group_filter, ldap3.SUBTREE, attributes=[])
            except LDAPException as exc:
                raise DirectoryError(f"Group search failed: {exc}") from exc
            return tuple(e.entry_dn for e in conn.entries)
        if "memberOf" in entry:
            return tuple(str(v) for v in entry["memberOf"].values)
        return ()

    def _to_user(self, conn: ldap3.Connection, entry: ldap3.Entry, login: str) -> DirectoryUser:
        s = self.settings
        groups = self._groups(conn, entry)
        return DirectoryUser(
            dn=entry.entry_dn,
            username=_first(entry, s.attr_username) or login,
            email=_first(entry, s.attr_email),
            full_name=_first(entry, s.attr_full_name),
            groups=groups,
            role=resolve_role(groups, s.role_mappings, s.default_role),
        )

    def lookup(self, username: str) -> DirectoryUser:
        """Find a user with the service account only (for the admin's 'test' button)."""
        conn = self._service()
        try:
            return self._to_user(conn, self._find(conn, username), username)
        finally:
            conn.unbind()

    def authenticate(self, username: str, password: str) -> DirectoryUser:
        if not username or not password:
            raise DirectoryAuthFailed("empty username or password")
        conn = self._service()
        try:
            entry = self._find(conn, username)
            user_conn = self._bind(entry.entry_dn, password)
            if user_conn is None:
                raise DirectoryAuthFailed("wrong password")
            user_conn.unbind()
            user = self._to_user(conn, entry, username)
        finally:
            conn.unbind()
        if user.role is None:
            raise DirectoryAuthFailed("user is in no group mapped to a WardX role")
        return user
