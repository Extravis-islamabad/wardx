# WardX credential provider API: contract for MonetX

Version 1 (WardX Phase 1). This document is the complete contract between WardX and MonetX
(the MonetX server and its collectors). It is handed over as-is; nothing else is needed to
build the integration.

## 1. Overview

MonetX does not store device credentials. When a collector polls a device (or NCM takes a
backup), it asks WardX for the device's current credential, uses it, and keeps it in memory for
a short time. WardX is the only place the credential lives, rotates it on its own schedule, and
records every fetch in its tamper-evident audit trail.

- MonetX authenticates as an **application identity** (for example `monetx-prod` or
  `monetx-collector-karachi`) with a `client_id` and `client_secret`, exchanged for a
  5-minute access token.
- An application identity only reaches the credentials of the WardX safes it was added to,
  with the `fetch` permission. It can never sign in to the WardX console or session gateway.
- Devices are matched by MonetX's own device id: in WardX every target can carry an
  `external_ref`, which is set to the MonetX device id (`device_registry.id`, a UUID string).
- A fetch is **not** a check-out: it is never blocked by a person holding the account, never
  waits for approvals, and never triggers a rotation.

All paths below are relative to the WardX base URL, for example
`https://wardx.example.net`. All bodies are JSON (`Content-Type: application/json`).

## 2. Setup

What a WardX administrator does, once per MonetX deployment or collector:

1. **Create the application identity** (Console: Identity → Application identities → Add
   application). Settings:
   - **Name**: e.g. `monetx-collector-karachi`.
   - **Allowed source networks**: the CIDRs the collector calls from, e.g. `10.20.30.0/24`.
     **An empty list means no access at all.** Through a reverse proxy, WardX uses the
     connection's address unless the proxy is listed in WardX's `WARDX_TRUSTED_PROXIES`.
   - **Fetches per minute**: default 600, counted across every WardX API worker.
2. **Copy the client secret.** It is shown **once**, at creation (or when a second secret is
   added). WardX keeps only a hash and can never show it again.
3. **Give the application access**: add it as a member of each safe whose credentials it may
   fetch (Safes → a safe → Members → Add member → Application). The only permission an
   application can hold is `fetch`.
4. **Per safe** (Safes → a safe → Application access):
   - **Apps may cache for (seconds)** (`app_cache_seconds`, 0 to 3600, default 300): returned
     to MonetX as `max_cache_seconds`.
   - **Allow app fetches despite approval** (`allow_app_fetch`, off by default): a safe that
     requires approval for people refuses application fetches unless this is on.
5. **Link devices**: set each WardX target's `external_ref` to the MonetX device id. Accounts
   on that target in a safe the application can fetch from are then served.

What MonetX receives from the WardX administrator, through a secure channel:

| Item | Example | Where MonetX keeps it |
|---|---|---|
| WardX base URL | `https://wardx.example.net` | configuration |
| WardX CA certificate (PEM) | `wardx-ca.pem` | configuration (for pinning) |
| `client_id` | `wxa_3f9c0e…` | configuration |
| `client_secret` | `wxs_…` (secret) | the collector's secret store or environment variable, **never** MonetX's database |

## 3. Authentication

### 3.1 Getting a token

`POST /api/v1/provider/token`

```http
POST /api/v1/provider/token HTTP/1.1
Host: wardx.example.net
Content-Type: application/json

{"client_id": "wxa_3f9c0e7a1b2c3d4e5f6a7b8c", "client_secret": "<client secret>"}
```

HTTP Basic is accepted instead of the body (user name = `client_id`, password =
`client_secret`):

```http
POST /api/v1/provider/token HTTP/1.1
Authorization: Basic base64(client_id:client_secret)
```

If both are sent, the JSON body is used.

**Response (200):**

```json
{
  "success": true,
  "data": {"access_token": "eyJhbGciOi…", "token_type": "Bearer", "expires_in": 300},
  "message": null
}
```

- The token is valid for **300 seconds** (5 minutes). There is no refresh token: ask again
  with the client secret.
- Send it on every provider call: `Authorization: Bearer <access_token>`.
- The token works only on the provider endpoints below. It is refused on every other WardX
  route, and WardX user tokens are refused on the provider endpoints.
- A token dies at once, before it expires, when the application is disabled or when the
  secret it was issued for is revoked or expires. Every call is also checked against the
  allowlist (`ip_not_allowed`).

**Refusals of the token route:** `invalid_client` (401) for any wrong `client_id` or
`client_secret` or a disabled application (WardX never says which), `ip_not_allowed` (403),
and `rate_limited` (429) after **10 failed attempts within a minute** for the same
`client_id` or from the same source address. Every attempt, successful or not, is audited.

### 3.2 Rotating the client secret (no downtime)

An application identity holds **at most two active secrets**, so collectors can move to a new
secret while the old one still works:

1. In WardX (Application identities → the app → Client secrets), **Add secret**. Copy it; it is
   shown once.
2. Put the new secret in every collector's secret store or environment, and restart or reload
   the collectors one by one. During this time both secrets work.
3. Confirm in WardX that the new secret is in use ("Last used" moves on the new secret's row)
   and the old one's "Last used" has stopped moving.
4. **Revoke** the old secret. Revocation is immediate: tokens issued for it stop working at
   once, so any collector still on it gets `invalid_token`, then `invalid_client`.
5. A third secret is refused until one is revoked. An expired secret keeps its slot until it is
   revoked.

## 4. Endpoints

### 4.1 Fetch a credential by device

`POST /api/v1/provider/credentials/fetch`

POST (not GET) so nothing is cached or prefetched on the way; every response carries
`Cache-Control: no-store`.

**Request:**

```json
{
  "target": {"external_ref": "6f1c2d3e-0000-4000-8000-00000000abcd"},
  "kind": "ssh",
  "username": "netadmin",
  "purpose": "poll"
}
```

| Field | Required | Values |
|---|---|---|
| `target` | yes | **exactly one** of `external_ref` (the MonetX device id; preferred), `address` (the target's address as stored in WardX, case-insensitive) or `name` (the WardX target name, case-insensitive) |
| `kind` | yes | `ssh` \| `snmp` \| `api` \| `enable` |
| `username` | when needed | the account's user name (exact). Required when the application can fetch more than one account of that kind on the device; without it WardX answers `credential_ambiguous` and never guesses |
| `purpose` | yes | `poll` \| `ncm_backup` \| `onboarding` \| `other`; recorded in the audit trail |

**Response (200):**

```json
{
  "success": true,
  "data": {
    "account_id": "0b7d1a52-8f0e-4b8e-9a51-6d2c0f3e9a10",
    "target": {
      "id": "c5e8f0a2-3b1d-4c6e-8f2a-1d0e9b7c6a54",
      "name": "khi-core-rtr-01",
      "address": "10.20.1.1",
      "external_ref": "6f1c2d3e-0000-4000-8000-00000000abcd"
    },
    "kind": "ssh",
    "username": "netadmin",
    "secret": {"password": "<password>"},
    "version_id": "cv_5b1e0d6f2a9c4e7b8d3f1a0c6e2b9d47",
    "max_cache_seconds": 300,
    "issued_at": "2026-10-29T10:00:00.123456Z"
  },
  "message": null
}
```

- `version_id`: opaque (do not parse). It stays the same while the stored credential is the
  same, and changes whenever WardX rotates or replaces it. Key the cache on it.
- `max_cache_seconds`: the longest MonetX may keep this credential in memory (0 = do not cache).
- `issued_at`: when WardX served it (UTC).

**`secret` by kind:**

| `kind` | Account type in WardX | `secret` |
|---|---|---|
| `ssh` | password | `{"password": "…"}` |
| `ssh` | SSH private key | `{"private_key": "<the OpenSSH private key, PEM text>"}` |
| `enable` | enable secret | `{"password": "…"}` |
| `api` | API key | `{"token": "…"}` |
| `snmp` | SNMP v2c | `{"version": "2c", "community": "…"}` |
| `snmp` | SNMP v3 | see below |

SNMPv3 (`security_level` is `noAuthNoPriv`, `authNoPriv` or `authPriv`; the fields a level
does not use are **absent**):

```json
{
  "version": "3",
  "security_name": "monetx",
  "security_level": "authPriv",
  "auth_protocol": "SHA-256",
  "auth_password": "…",
  "priv_protocol": "AES",
  "priv_password": "…"
}
```

`auth_protocol` is one of `MD5`, `SHA`, `SHA-224`, `SHA-256`, `SHA-384`, `SHA-512`;
`priv_protocol` one of `DES`, `3DES`, `AES`, `AES-192`, `AES-256`. A `noAuthNoPriv` secret has
only `version`, `security_name` and `security_level`; `authNoPriv` adds the two `auth_` fields.

Examples of the other kinds (only `data.kind`, `data.username` and `data.secret` differ from
the SSH response above):

```json
{"kind": "enable", "username": "enable", "secret": {"password": "…"}}
{"kind": "api", "username": "monetx-api", "secret": {"token": "…"}}
{"kind": "snmp", "username": "snmp", "secret": {"version": "2c", "community": "…"}}
{"kind": "ssh", "username": "backup", "secret": {"private_key": "<the OpenSSH private key, PEM text>"}}
```

### 4.2 Fetch a credential by account id

`POST /api/v1/provider/credentials/{account_id}/fetch`

For an application that already knows WardX's `account_id` (from an earlier response).

```json
{"purpose": "poll"}
```

The response is the same as in 4.1; `kind` is derived from the account's type. Every rule and
refusal of 4.1 applies.

## 5. Errors

Every refusal uses the same envelope:

```json
{
  "success": false,
  "status_code": 409,
  "error": {
    "code": "credential_unavailable.rotation_needs_attention",
    "message": "A rotation of this account needs attention",
    "details": {}
  }
}
```

Match on `error.code`, never on `message` (human text, may change).

| HTTP | `error.code` | Meaning | What MonetX does |
|---|---|---|---|
| 401 | `invalid_token` | Token missing, malformed, expired, or revoked (app disabled, its secret revoked or expired) | Get a new token once and repeat the call once. If that fails too, stop and alert |
| 401 | `invalid_client` | Token route: wrong `client_id` or `client_secret`, or the application is disabled | Do not retry in a loop; alert an operator (the secret is wrong, revoked or expired) |
| 403 | `ip_not_allowed` | The calling address is not in the application's allowlist | Do not retry; alert an operator (allowlist or proxy configuration) |
| 404 | `credential_not_found` | No account matches that the application may fetch (WardX does not say whether the device or account exists) | Do not retry until the next poll; report "credential unavailable" |
| 409 | `credential_ambiguous` | Several accounts of that kind match; `details.matches` gives the count | Send `username`; fix the device's credential mapping in MonetX |
| 409 | `credential_unavailable.approval_required` | The safe requires approval and does not allow applications | Report "credential unavailable"; a WardX admin must allow app fetches on that safe |
| 409 | `credential_unavailable.verify_untrustworthy` | WardX cannot vouch for the stored password (the device accepted a wrong one) | Report "credential unavailable"; retry at the next poll |
| 409 | `credential_unavailable.rotation_needs_attention` | A rotation of this account needs an administrator | Report "credential unavailable"; retry at the next poll |
| 409 | `credential_unavailable.no_secret` | Nothing is stored for the account, or the stored secret is empty | Report "credential unavailable"; retry at the next poll |
| 429 | `rate_limited` | Too many fetches for this application this minute, or too many failed token attempts; `Retry-After` header (seconds) and `details.retry_after` | Wait at least `Retry-After` seconds plus jitter, then retry |
| 422 | `validation_error` | The request body is malformed (e.g. two target keys, unknown `kind`) | Fix the request; do not retry |
| 5xx | `internal_error` / `vault_error` | WardX-side failure | Retry with exponential backoff and jitter, at most a few times per poll |

**Show any `credential_unavailable.*` as "credential unavailable" in MonetX, never as "device
down".** The device may be perfectly healthy; WardX is deliberately not serving its
credential right now.

## 6. Client rules (MonetX must follow these)

1. **Cache in memory only, keyed by `version_id`, for at most `max_cache_seconds`.** Never
   write a credential to disk, a database, a log, a metric label or an error report. When
   `max_cache_seconds` is 0, do not cache.
2. **Re-fetch at once on a device authentication failure.** If a device rejects a cached
   credential, drop it from the cache, fetch again immediately, and retry the device **once**
   with the result.
3. **Never retry a cached credential more than once.** If the freshly fetched credential is
   rejected too, report an authentication failure for that device and stop until the next
   poll. (Repeated logins with a wrong password lock accounts and trip device alarms.)
4. **Show `credential_unavailable.*` as "credential unavailable", not "device down".**
5. **Reuse the token** until shortly before it expires (e.g. 30 seconds before
   `expires_in` runs out); do not request a token per fetch. On `invalid_token`, get a new
   token **once**, then fail.
6. **Back off.** On 429 wait at least `Retry-After` seconds; on 5xx use exponential backoff with
   jitter. Never retry 403 or 404 in a loop; `invalid_client` is not retried at all.

## 7. Security requirements

- **TLS only.** Never call WardX over plain HTTP.
- **Verify WardX's certificate and pin its CA**: configure the HTTP client with the WardX CA
  certificate as the only trust anchor (`verify="/etc/monetx/wardx-ca.pem"`), with hostname
  verification on. Never disable verification.
- **Where the client secret lives:** in the collector's secret store (Vault, a KMS-backed
  secret, a Kubernetes secret) or an environment variable or file readable only by the
  collector's service account. **Never** in MonetX's database, configuration repositories,
  command lines, logs or crash reports.
- **Never log** the client secret, access tokens, or any `secret` field. Log `version_id`,
  `account_id` and `error.code` instead.
- **One application identity per deployment or collector site**, each with the narrowest
  allowlist, so one can be disabled without affecting the others.
- Everything MonetX does is audited in WardX: application, source address, device, account,
  kind, purpose, `version_id` and the error code of a refusal.

## 8. Reference client (Python)

A minimal client following every rule above (Python 3.11+, `httpx`).

```python
"""Minimal WardX credential provider client for a MonetX collector."""

from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field

import httpx

TOKEN_MARGIN_SECONDS = 30
MAX_RETRIES = 4


class CredentialUnavailable(Exception):
    """WardX will not serve this credential now: show "credential unavailable"."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


@dataclass
class _Cached:
    version_id: str
    secret: dict
    username: str
    expires_at: float


@dataclass
class WardXProvider:
    base_url: str
    client_id: str
    ca_file: str  # WardX's CA certificate: the only trust anchor
    client_secret: str = field(repr=False, default="")
    _token: str | None = field(default=None, repr=False)
    _token_expires: float = 0.0
    _cache: dict = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        # From the collector's environment or secret store, never from MonetX's database.
        self.client_secret = self.client_secret or os.environ["WARDX_CLIENT_SECRET"]
        self._http = httpx.Client(base_url=self.base_url, verify=self.ca_file, timeout=10)

    # ── token ──
    def _get_token(self, force: bool = False) -> str:
        if force or not self._token or time.time() > self._token_expires - TOKEN_MARGIN_SECONDS:
            resp = self._send("POST", "/api/v1/provider/token",
                              {"client_id": self.client_id, "client_secret": self.client_secret},
                              auth=False)
            data = resp.json()["data"]
            self._token = data["access_token"]
            self._token_expires = time.time() + data["expires_in"]
        return self._token

    # ── HTTP with the error rules ──
    def _send(self, method: str, path: str, body: dict, auth: bool = True) -> httpx.Response:
        renewed = False
        for attempt in range(MAX_RETRIES):
            headers = {"Authorization": f"Bearer {self._get_token()}"} if auth else {}
            resp = self._http.request(method, path, json=body, headers=headers)
            if resp.status_code == 200:
                return resp
            code = resp.json().get("error", {}).get("code", "")
            if code == "invalid_token" and auth and not renewed:
                self._get_token(force=True)  # once
                renewed = True
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = float(resp.headers.get("Retry-After", 2 ** attempt))
                time.sleep(wait + random.uniform(0, 1))  # backoff with jitter
                continue
            if code.startswith("credential_unavailable") or code == "credential_not_found":
                raise CredentialUnavailable(code, resp.json()["error"]["message"])
            resp.raise_for_status()  # 401 invalid_client, 403, 409 ambiguous, 422: no retry
        resp.raise_for_status()
        raise RuntimeError(f"WardX kept refusing: {resp.status_code}")

    # ── fetch with the cache rules ──
    def fetch(self, device_id: str, kind: str, username: str | None = None,
              purpose: str = "poll", fresh: bool = False) -> _Cached:
        key = (device_id, kind, username)
        hit = self._cache.get(key)
        if hit and not fresh and time.time() < hit.expires_at:
            return hit
        body = {"target": {"external_ref": device_id}, "kind": kind, "purpose": purpose}
        if username:
            body["username"] = username
        data = self._send("POST", "/api/v1/provider/credentials/fetch", body).json()["data"]
        entry = _Cached(data["version_id"], data["secret"], data["username"],
                        time.time() + data["max_cache_seconds"])
        if data["max_cache_seconds"] > 0:
            self._cache[key] = entry  # memory only
        else:
            self._cache.pop(key, None)
        return entry

    def login(self, device_id: str, kind: str, connect, username: str | None = None):
        """Call ``connect(username, secret)``; on an authentication failure re-fetch once and
        retry once. ``connect`` raises PermissionError when the device rejects the login."""
        cred = self.fetch(device_id, kind, username)
        try:
            return connect(cred.username, cred.secret)
        except PermissionError:
            self._cache.pop((device_id, kind, username), None)
            fresh = self.fetch(device_id, kind, username, fresh=True)
            return connect(fresh.username, fresh.secret)  # the only retry; failure propagates
```

Usage in a collector:

```python
provider = WardXProvider(
    base_url="https://wardx.example.net",
    client_id="wxa_3f9c0e7a1b2c3d4e5f6a7b8c",
    ca_file="/etc/monetx/wardx-ca.pem",
)
try:
    result = provider.login(device_id, "ssh", connect=my_ssh_login)
except CredentialUnavailable as exc:
    mark_device(device_id, status="credential unavailable", reason=exc.code)
except PermissionError:
    mark_device(device_id, status="authentication failed")
```

A runnable version that behaves like a collector against a lab device is in WardX's repository
at `tools/demo/monetx_fetch_demo.py`.
