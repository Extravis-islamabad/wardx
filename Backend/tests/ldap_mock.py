"""An in-memory Active Directory-like tree (ldap3 MOCK_SYNC) for directory tests."""

from __future__ import annotations

import ldap3

from src.directory.ldap_client import DirectorySettings

BASE = "dc=corp,dc=test"
SVC_DN, SVC_PW = f"cn=wardx-svc,ou=service,{BASE}", "Svc-Bind-Pass-1"
ADMINS = f"cn=PAM-Admins,ou=groups,{BASE}"
OPERATORS = f"cn=NOC-Operators,ou=groups,{BASE}"
AUDITORS = f"cn=Auditors,ou=groups,{BASE}"


def build_directory() -> ldap3.Server:
    server = ldap3.Server("mock-ad", get_info=ldap3.OFFLINE_AD_2012_R2)
    seed = ldap3.Connection(server, user=SVC_DN, password=SVC_PW, client_strategy=ldap3.MOCK_SYNC)
    seed.strategy.add_entry(SVC_DN, {"objectClass": ["user"], "userPassword": SVC_PW})

    def person(cn: str, sam: str, pw: str, groups: list[str], mail: str | None = None) -> None:
        attrs = {
            "objectClass": ["user"],
            "sAMAccountName": sam,
            "userPassword": pw,
            "displayName": cn,
            "memberOf": groups,
        }
        if mail:
            attrs["mail"] = mail
        seed.strategy.add_entry(f"cn={cn},ou=people,{BASE}", attrs)

    person("Ayesha Khan", "akhan", "Dir-Pass-akhan1", [ADMINS, OPERATORS], "akhan@corp.test")
    person("Bilal Ahmed", "bahmed", "Dir-Pass-bahmed1", [OPERATORS], "bahmed@corp.test")
    person("Sara Malik", "smalik", "Dir-Pass-smalik1", [AUDITORS])
    person("No Group", "nogroup", "Dir-Pass-nogroup1", [])
    # Two entries share a login name: the gateway must refuse, not guess.
    person("Dup One", "dupe", "Dir-Pass-dupe1", [OPERATORS])
    person("Dup Two", "dupe", "Dir-Pass-dupe2", [ADMINS])
    # A directory user whose name collides with a local WardX account.
    person("Admin Impostor", "admin", "Dir-Pass-admin1", [ADMINS])
    return server


def mock_factory(server: ldap3.Server):
    def factory(_: DirectorySettings, user: str, password: str) -> ldap3.Connection:
        return ldap3.Connection(
            server, user=user, password=password, client_strategy=ldap3.MOCK_SYNC
        )

    return factory


def settings(**overrides) -> DirectorySettings:
    base = {
        "server_url": "ldap://mock-ad",
        "bind_dn": SVC_DN,
        "bind_password": SVC_PW,
        "user_base_dn": f"ou=people,{BASE}",
        "user_filter": "(&(objectClass=user)(sAMAccountName={username}))",
        "attr_username": "sAMAccountName",
        "role_mappings": ((ADMINS, "admin"), (OPERATORS, "user"), (AUDITORS, "auditor")),
    }
    base.update(overrides)
    return DirectorySettings(**base)
