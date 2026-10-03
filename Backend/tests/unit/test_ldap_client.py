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
