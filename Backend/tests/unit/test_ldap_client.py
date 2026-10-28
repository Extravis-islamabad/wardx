import pytest

from src.directory.ldap_client import (
    DirectoryAuthFailed,
    DirectoryClient,
    DirectoryError,
    normalise_dn,
    resolve_role,
)
from tests.ldap_mock import ADMINS, AUDITORS, OPERATORS, build_directory, mock_factory, settings


@pytest.fixture(scope="module")
def client():
    return DirectoryClient(settings(), mock_factory(build_directory()))


def test_good_password_returns_profile_and_highest_role(client):
    user = client.authenticate("akhan", "Dir-Pass-akhan1")
    assert user.dn.startswith("cn=Ayesha Khan,")
    assert (user.username, user.email, user.full_name) == (
        "akhan",
        "akhan@corp.test",
        "Ayesha Khan",
    )
    assert user.role == "admin"  # in admins and operators: highest wins


def test_wrong_and_empty_password_refused(client):
    with pytest.raises(DirectoryAuthFailed):
        client.authenticate("akhan", "wrong")
    with pytest.raises(DirectoryAuthFailed):
        client.authenticate("akhan", "")


def test_unknown_and_ambiguous_users_refused(client):
    with pytest.raises(DirectoryAuthFailed):
        client.authenticate("nobody", "x")
    with pytest.raises(DirectoryAuthFailed, match="unique"):
        client.authenticate("dupe", "Dir-Pass-dupe1")


def test_filter_injection_cannot_widen_the_search(client):
    # Unescaped, "*" would match every user and ")(" could add clauses.
    with pytest.raises(DirectoryAuthFailed):
        client.authenticate("*", "Dir-Pass-akhan1")
    with pytest.raises(DirectoryAuthFailed):
        client.authenticate("akhan)(sAMAccountName=*", "Dir-Pass-akhan1")


def test_user_in_no_mapped_group_is_refused_unless_default_role():
    server = build_directory()
    strict = DirectoryClient(settings(), mock_factory(server))
    with pytest.raises(DirectoryAuthFailed, match="no group"):
        strict.authenticate("nogroup", "Dir-Pass-nogroup1")
    lenient = DirectoryClient(settings(default_role="user"), mock_factory(server))
    assert lenient.authenticate("nogroup", "Dir-Pass-nogroup1").role == "user"


def test_bad_service_credentials_is_a_configuration_error():
    bad = DirectoryClient(settings(bind_password="nope"), mock_factory(build_directory()))
    with pytest.raises(DirectoryError, match="service account"):
        bad.lookup("akhan")


def test_lookup_without_user_password(client):
    user = client.lookup("smalik")
    assert user.role == "auditor" and AUDITORS in user.groups


def test_role_resolution_ignores_dn_case_and_spacing():
    groups = ("CN=pam-admins, OU=Groups, DC=corp, DC=test",)
    assert resolve_role(groups, ((ADMINS, "admin"),), None) == "admin"
    assert resolve_role((), ((ADMINS, "admin"),), "auditor") == "auditor"
    assert resolve_role((OPERATORS,), ((ADMINS, "admin"),), None) is None
    assert normalise_dn("CN=A, DC=B") == "cn=a,dc=b"


# ── Nested groups (Active Directory LDAP_MATCHING_RULE_IN_CHAIN) ──
# ldap3's mock rejects extensible-match filters, so these check what WardX sends
# with a recording wrapper around a mock connection.


def test_in_chain_filter_uses_the_ad_rule_and_escapes_the_dn():
    from src.directory.ldap_client import in_chain_filter

    got = in_chain_filter("cn=Smith\\, J (ops)*,ou=people,dc=corp,dc=test")
    assert got.startswith("(&(objectClass=group)(member:1.2.840.113556.1.4.1941:=")
    assert "\\28ops\\29\\2a" in got and "(ops)" not in got


def test_domain_root_is_the_dc_suffix():
    from src.directory.ldap_client import domain_root

    assert domain_root("ou=people, DC=corp,dc=test") == "DC=corp,dc=test"
    assert domain_root("o=example") == "o=example"


def test_nested_lookup_searches_in_chain_and_unions_with_member_of():
    import ldap3

    from tests.ldap_mock import BASE

    nested_group = f"cn=Parent Group,ou=groups,{BASE}"
    searches: list[tuple[str, str]] = []

    class Recording:
        def __init__(self, conn):
            self._conn, self.entries = conn, []

        def __getattr__(self, name):
            return getattr(self._conn, name)

        def search(self, base, flt, *args, **kwargs):
            searches.append((base, flt))
            if "1.2.840.113556.1.4.1941" in flt:
                entry = type("E", (), {"entry_dn": nested_group})()
                self.entries = [entry]
                return True
            ok = self._conn.search(base, flt, *args, **kwargs)
            self.entries = self._conn.entries
            return ok

    server = build_directory()

    def factory(s, user, password):
        conn = ldap3.Connection(
            server, user=user, password=password, client_strategy=ldap3.MOCK_SYNC
        )
        return Recording(conn)

    user = DirectoryClient(settings(nested_groups=True), factory).lookup("bahmed")
    in_chain = [s for s in searches if "1.2.840.113556.1.4.1941" in s[1]]
    assert in_chain and in_chain[0][0] == BASE  # no group base: the domain root
    assert "cn=Bilal Ahmed" in in_chain[0][1]
    assert user.groups == (OPERATORS, nested_group)


def test_nested_groups_off_reads_member_of_only(client):
    assert client.lookup("bahmed").groups == (OPERATORS,)
