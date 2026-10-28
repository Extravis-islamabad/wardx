"""The MonetX contract (docs/integrations/monetx-credential-provider-api.md) cannot drift
from the implementation: its endpoint paths and methods are the app's provider routes in the
OpenAPI schema, and its error table is exactly the provider's error codes with their HTTP
statuses (src/services/provider/provider_errors.py), each documented in the OpenAPI too."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from src.core.app_factory import create_app
from src.services.provider.provider_errors import PROVIDER_ERRORS

DOC = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "integrations"
    / ("monetx-credential-provider-api.md")
)
TEXT = DOC.read_text()
# Generic codes the contract also explains (not provider-specific).
GENERIC = {"validation_error": "422", "internal_error": "5xx", "vault_error": "5xx"}


def _openapi() -> dict:
    return create_app().openapi()


def _provider_operations(schema: dict) -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in schema["paths"].items()
        if path.startswith("/api/v1/provider/")
        for method in item
    }


def test_doc_endpoints_are_exactly_the_provider_routes():
    documented = set(re.findall(r"`(GET|POST|PUT|PATCH|DELETE) (/api/v1/provider/[^`\s]+)`", TEXT))
    assert documented == _provider_operations(_openapi())


def test_every_provider_path_in_the_doc_exists():
    paths = set(re.findall(r"(/api/v1/provider/[A-Za-z0-9_{}/-]+)", TEXT))
    known = {p for _, p in _provider_operations(_openapi())}
    assert paths and paths <= known, paths - known


def _error_table() -> dict[str, str]:
    rows = re.findall(r"^\| (\d{3}|5xx) \| `([a-z_.]+)`(?: / `([a-z_.]+)`)? \|", TEXT, re.M)
    table: dict[str, str] = {}
    for status, code, other in rows:
        for c in filter(None, (code, other)):
            assert c not in table, f"{c} listed twice"
            table[c] = status
    return table


def test_error_table_matches_the_provider_errors():
    table = _error_table()
    expected = {e.code: str(e.status_code) for e in PROVIDER_ERRORS} | GENERIC
    assert table == expected


def test_every_provider_error_code_is_in_the_openapi_examples():
    schema = _openapi()
    examples: set[str] = set()
    for path, item in schema["paths"].items():
        if not path.startswith("/api/v1/provider/"):
            continue
        for op in item.values():
            for response in op.get("responses", {}).values():
                for content in response.get("content", {}).values():
                    examples |= set(content.get("examples", {}))
    assert {e.code for e in PROVIDER_ERRORS} <= examples


def test_request_enums_match_the_schema():
    schema = _openapi()["components"]["schemas"]
    kinds = set(schema["CredentialFetch"]["properties"]["kind"]["enum"])
    purposes = set(schema["CredentialFetch"]["properties"]["purpose"]["enum"])
    assert "`ssh` \\| `snmp` \\| `api` \\| `enable`" in TEXT and kinds == {
        "ssh",
        "snmp",
        "api",
        "enable",
    }
    assert purposes == {"poll", "ncm_backup", "onboarding", "other"}
    for purpose in purposes:
        assert f"`{purpose}`" in TEXT


def test_reference_client_is_valid_python():
    blocks = re.findall(r"```python\n(.*?)```", TEXT, re.S)
    assert len(blocks) >= 2
    for block in blocks:
        ast.parse(block)
