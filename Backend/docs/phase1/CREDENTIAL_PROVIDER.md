# Phase 1 (d) MonetX credential provider: spec

Status: **approved design, 2026-10-29** (security decisions answered by the product owner).
MonetX and its collectors fetch device credentials (SSH, SNMP, API) from WardX at poll time
instead of storing them. This file is the internal design. The contract for the MonetX team
is `docs/integrations/monetx-credential-provider-api.md` and must always match it.

Layering follows `Backend/ARCHITECTURE.md`. Encryption goes only through the vault service.
Smaller choices made during the build are logged in §11, not asked.

## 1. Application identities

An **application identity** ("app") is a non-human principal, for example `monetx-prod` or
`monetx-collector-karachi`.

| Field | Notes |
|---|---|
| `name` | Unique, case-insensitive. |
| `description`, `enabled` | Disabling an app invalidates all its outstanding tokens at once (a `token_version` per app, checked on every request). |
| `ip_allowlist` | CIDR list. **Empty means no access**: an app is unusable until at least one CIDR is set, and the UI warns. |
| `rate_limit_per_minute` | Fetches per minute, default 600. Enforced across all API workers (Postgres fixed-window counter), not per process. |
| `created_by`, timestamps | |

**Secrets:**
- `client_id` (public) plus `client_secret` (shown **once**, at creation).
- Only an argon2id hash and a short prefix are stored; the plaintext is never stored or logged.
- **Up to two active secrets per app**, so a collector can be moved to a new secret during an
  overlap window without downtime. Add a second secret, update the collectors, revoke the old
  one. A third is refused until one is revoked.
- A secret may have an optional `expires_at`. Revoking is immediate.

**Management:**
- New codename `apps.manage` (admin role). Every create, change, secret add or revoke, and
  enable or disable is audited.
- Apps never hold user permissions or roles, and can never sign in to the console or the
  gateway.

## 2. Authentication

`POST /api/v1/provider/token` takes `{client_id, client_secret}`, or HTTP Basic with the same
pair.
- **Checks:** the app exists and is enabled; the source IP is in its allowlist; the secret
  matches an active, unexpired secret (argon2, constant-time).
- **Source IP:** taken from the connection. `X-Forwarded-For` is honoured only from proxies
  listed in `WARDX_TRUSTED_PROXIES`, which is empty by default.
- **Failed attempts:** audited (`app.token`, outcome failure, no secret in the details) and
  rate-limited per `client_id` and per source IP (default 10 per minute, then 429).
- **The token:** an access token valid **5 minutes**. It's a JWT with `typ=app`,
  `aud=wardx-credential-provider`, `sub=<app id>`, `tv=<app token_version>` and a `jti`.
  There's no refresh token; the app asks again with its secret.
- **App tokens can't be used on any user route.** `get_current_user` refuses `typ=app`, and
  provider routes refuse user tokens.
- The token route is the only new entry in `PUBLIC_ROUTES`. It authenticates by client
  credentials; review it as such.

## 3. Safe access: the `fetch` permission

- New safe permission **`fetch`**, valid only for the new member principal type **`app`**.
  Apps can't be given any other safe permission, and users or groups can't be given `fetch`.
- Adding an app to a safe needs `manage_members` on the safe, as for any member. It's
  audited per safe.
- **A fetch is not a check-out:**
  - no check-out record;
  - no rotate-after-use trigger;
  - not blocked by exclusive check-outs;
  - not part of the approval workflow, except as below.
- **Approval-required safes refuse app fetches**, unless the safe's new setting
  `allow_app_fetch` is on. That setting is off by default, needs `manage_members`, and is
  audited.
- **Accounts not served to apps:**
  - those whose rotation needs attention;
  - those whose verify is untrustworthy;
  - those with no stored secret;
  - those whose current secret is flagged empty.

## 4. Fetching credentials

`POST /api/v1/provider/credentials/fetch` (POST, so nothing is cached or prefetched; the
response is `no-store`). The body:

```json
{
  "target": {"external_ref": "monetx-device-1234"},
  "kind": "ssh",
  "username": "netadmin",
  "purpose": "poll"
}
```

**Request fields:**
- **`target`:** exactly one of `external_ref` (MonetX's device id, the preferred match),
  `address` or `name`.
- **`kind`:** `ssh` | `snmp` | `api` | `enable`.
- **`username`:** optional. It's required when the app can fetch several accounts of that kind
  on the target; an ambiguous match is refused with `credential_ambiguous`, never resolved by
  guessing.
- **`purpose`:** `poll` | `ncm_backup` | `onboarding` | `other`. It's recorded in the audit.

**Response (200):**

```json
{
  "account_id": "…",
  "target": {"id": "…", "name": "…", "address": "…", "external_ref": "…"},
  "kind": "ssh",
  "username": "netadmin",
  "secret": {"password": "…"},
  "version_id": "cv_3f9a…",
  "max_cache_seconds": 300,
  "issued_at": "2026-10-29T10:00:00Z"
}
```

**`secret` by kind:**

| Kind | Fields |
|---|---|
| `ssh` | `{"password"}` or `{"private_key", "passphrase"?}` |
| `enable` | `{"password"}` |
| `api` | `{"token"}` |
| `snmp` | SNMPv2c: `{"version": "2c", "community"}`. SNMPv3: `{"version": "3", "security_name", "security_level", "auth_protocol", "auth_password", "priv_protocol", "priv_password"}`, with fields omitted where the security level doesn't use them. |

**`version_id`:** opaque and stable for one stored secret version. It changes when the
credential is rotated or replaced, so MonetX can key its cache on it.

**`max_cache_seconds`:** from the safe's new setting `app_cache_seconds` (default **300**,
0 to 3600).

**SNMP secrets** are new account secret types `snmp_v2c` and `snmp_v3`. The structured SNMPv3
secret is sealed as one JSON document in the vault. SNMP accounts are vaultable and fetchable
but not rotatable yet, and the engine refuses them with a clear reason.

**`POST /api/v1/provider/credentials/{account_id}/fetch` `{purpose}`:** the same, by account
id, for apps that already know it.

## 5. Errors (distinct codes)

Every refusal uses the standard error envelope.

| HTTP | `error.code` | Meaning for MonetX |
|---|---|---|
| 401 | `invalid_token` | Get a new token (expired, revoked, app disabled) |
| 401 | `invalid_client` | Wrong client_id or secret (token route) |
| 403 | `ip_not_allowed` | Source IP not in the app's allowlist |
| 404 | `credential_not_found` | No fetchable account matches (or the app has no `fetch` there): don't distinguish |
| 409 | `credential_ambiguous` | Several accounts match: send `username` |
| 409 | `credential_unavailable.approval_required` | The safe requires approval and doesn't allow apps |
| 409 | `credential_unavailable.verify_untrustworthy` | WardX can't vouch for the current password |
| 409 | `credential_unavailable.rotation_needs_attention` | A rotation needs an administrator |
| 409 | `credential_unavailable.no_secret` | Nothing stored, or the stored secret is empty |
| 429 | `rate_limited` | Back off (`Retry-After` header) |

MonetX shows any `credential_unavailable.*` as "credential unavailable", never "device down".

## 6. Client rules (written into the contract)

1. **Cache:** keep a credential in memory only, for at most `max_cache_seconds`, keyed by
   `version_id`. Never write it to disk, a database or a log.
2. **Re-fetch on an authentication failure:** if a device rejects a cached credential, fetch
   again immediately and retry the device once with the result. **Never retry a cached
   credential more than once.** If the fresh credential is also rejected, report an
   authentication failure and stop until the next poll.
3. **Tokens:** reuse a token until shortly before it expires. On `invalid_token`, get a new one
   once, then fail.
4. **Retries:** back off on 429 and on 5xx with jitter, and never retry 403 or 404 in a loop.
5. **Transport:** TLS only, and verify WardX's certificate (pin its CA).
6. **Secrets:** `client_secret` lives in the collector's secret store or environment, never in
   MonetX's database. Rotating it uses the two-secret overlap (§1).

## 7. Audit

- **Every fetch, served or refused,** is audited as `secret.app_fetch` (outcome success or
  failure) with:
  - the account's `safe_id`;
  - app id and name, and the source IP;
  - account, target and kind;
  - purpose, `version_id`, and the error code on refusal.
- The actor is the app (`actor_name = "app:<name>"`, a stable `actor_id`).
- **Token issuance:** `app.token` events, successes and failures.
- **No secret value, client secret or token** is ever written to an audit event or log.

## 8. Rotation interplay

- A fetch always serves the account's **current** version.
- After a rotation, `version_id` changes. A cached credential fails on the device, and the
  client rule (re-fetch once on authentication failure) picks up the new one.
- With the default cache of 300 seconds, the worst case is one failed device login per
  collector per rotation.
- Rotation is unaware of app caches by design; apps never hold a check-out.

## 9. Console

- **Settings → Application identities:**
  - list, create, edit (allowlist, rate limit, enabled);
  - secrets: add (shown once, with a copy button and a warning), revoke, at most two active;
  - per-app recent fetches (from the audit).
- **Safes:**
  - add an app as a member with `fetch` (the only permission offered for apps);
  - safe settings `allow_app_fetch` and `app_cache_seconds`.
- **Accounts:** create SNMPv2c and SNMPv3 accounts (structured form).

## 10. Demo and tests

- **Demo:** `tools/demo/monetx_fetch_demo.py` does what a MonetX collector does.
  - Gets a token, fetches a credential by `external_ref`, and caches it by `version_id`.
  - Optionally logs in once to the Linux lab container with it, then shows re-fetch on
    authentication failure.
  - It prints metadata, never the secret (masked unless `--reveal`), and reads the client
    secret from an environment variable or a file, never from argv.
- **Tests:**
  - token: good and bad secret; disabled app; IP not allowed; both secrets working during the
    overlap; a third refused; revoked or expired secrets refused; failed-attempt rate limit;
    app tokens refused on user routes and user tokens refused on provider routes;
  - fetch: only from safes with `fetch`; every distinct refusal code; ambiguous match;
    rate limit 429 across workers;
  - side effects: audit per fetch with `safe_id`; no check-out created; rotate-after-use not
    triggered; an exclusive check-out doesn't block; `version_id` changes after a rotation;
    `max_cache_seconds` from the safe; SNMP v2c and v3 stored and fetched;
  - the route-coverage and audit safe-coverage guard tests extended.

## 11. Build log (smaller choices, logged rather than asked)

Choices made during the build (the more restrictive option where the spec was silent).

**Data (migration 021, additive).**
- Tables `iam.apps`, `iam.app_secrets`, `iam.rate_counters`. App names are unique
  case-insensitively and limited to letters, digits and `. _ -`.
- `client_id` is `wxa_` + 24 hex characters; a client secret is `wxs_` + 43 URL-safe
  characters (256 bits). The stored prefix is the first 12 characters.
- Two active secrets are enforced by slots (1, 2) under a partial unique index. **An expired
  secret keeps its slot until it is revoked** (it no longer authenticates).
- `fetch` only for `app` members and apps only `fetch` is a CHECK constraint as well as a
  service rule. App members are not counted by safe health (they are nobody's way in).
- No app deletion: disable instead (history stays attributable).

**Authentication.**
- App tokens are signed with a key derived from the JWT secret (HMAC "wardx-app-token-v1"), so
  they can never verify as user tokens (and vice versa) even before the `typ`/`aud` checks.
- The token carries `sid` (the secret it was issued for): revoking or expiry of that secret
  kills the token at once. Disabling bumps `token_version`; re-enabling does not revive old
  tokens. The 5-minute lifetime is a constant, not a setting.
- The allowlist is checked on **every** provider request, not only at token issue.
- Token route order: failure rate limit → app exists and enabled (`invalid_client`) → IP
  (`ip_not_allowed`) → secret. `ip_not_allowed` counts as a failed attempt. Both secret slots
  are always verified (dummy hashes for missing ones) so timing does not reveal the count.
- Failure limit: `WARDX_PROVIDER_TOKEN_FAILURES_PER_MINUTE` (default 10) per client_id
  (hashed into the bucket name) and per source IP; refusals while limited are audited.
  The pre-check and the increment are separate, so concurrent guesses can overshoot by the
  number in flight.
- The token response uses the house envelope (`data.access_token`, `token_type`,
  `expires_in`); JSON body wins over HTTP Basic when both are sent.
- `X-Forwarded-For` is read only when the peer is in `WARDX_TRUSTED_PROXIES`; the source is
  the right-most hop that is not a trusted proxy; a malformed hop makes the source unknown
  (refused).
- A missing or non-app token on a provider route answers `invalid_token`; the route-coverage
  guard expects that code there. Refusals of an authentic token (disabled app, revoked
  secret, IP) are audited as `secret.app_fetch` failures; a token that is not authentic is
  refused without an audit event (it identifies no app).

**Fetch.**
- Rate limit: one fixed one-minute window per app in `iam.rate_counters` (database clock),
  incremented in its own committed transaction so every worker sees it; every authenticated
  fetch counts, served or refused. Old windows are pruned opportunistically (1 hit in 200).
- Matching: `external_ref` exact; `address` and `name` case-insensitive; `username` exact.
  Inactive safes and inactive targets read as `credential_not_found`.
- Kind to secret type: `ssh` = password or ssh_key, `enable` = enable_secret, `api` = api_key,
  `snmp` = snmp_v2c or snmp_v3. By account id the kind follows the account's type.
- Refusal order: approval → rotation needs attention (open needs_attention job or account
  `rotation_status`) → `verify_untrustworthy` → no secret / empty flag / blank plaintext.
  `confirmed_untrustworthy` (an admin accepted the risk) is served, as for people.
- `version_id` = `cv_` + the first 32 hex of SHA-256(account id : secret version).
- `ssh_key` accounts return `{private_key}` only: WardX stores no passphrase.
- Audit details: app id and name, kind, purpose, match key and value, username, account,
  target, safe, `version_id`, `error_code`. Refusals before an account is matched
  (not found, ambiguous, rate limited) are recorded with object type `app`.
- `credential_ambiguous` returns `details.matches` (a count, never usernames).

**Safes, SNMP, console.**
- Safe settings live at `GET/PUT /safes/{id}/app-fetch` (manage_members on the safe or
  safes.manage), audited as `safe.app_fetch_update`.
- SNMP secrets are submitted in a structured `snmp` field (not `secret`), validated per
  security level (fields a level does not use are refused, auth/priv passwords at least 8
  characters) and sealed as canonical JSON through the vault service. MD5 and DES are
  accepted because devices still use them. The SSH transport refuses SNMP accounts outright
  so a document is never sent as a password; rotation refuses them with a clear reason.
- Console: Identity → Application identities; the secret-once modal masks the secret until
  revealed and needs "I have stored it" to close. Safe drawer: app members and an
  "Application access" tab. Accounts: SNMP v2c/v3 forms.

**Tests and demo.** The cross-worker rate-limit test starts a second real `uvicorn` worker on
the same database. The suite is run without `test_mikrotik_lab.py` and `test_mikrotik_e2e.py`
for this module (they drive the CHR, which this module must leave untouched). The demo tools
are `tools/demo/monetx_fetch_demo.py` and `tools/demo/seed_demo.py`; the seed puts the demo
account in the Default safe, because an administrator cannot grant their own role on a new
safe.
