# WardX backend architecture

WardX mirrors the MonetX 3.0 backend layering exactly, so engineers move between
the two without relearning anything. Every module is built the same way:

```
models/<module>/<table>.py            ORM, one class per table (tables come from migrations/*.sql)
contracts/dto/<module>/<x>_dto.py     frozen dataclasses the repositories return
repositories/<module>/<x>_repository.py   BaseRepository subclass; SQL lives only here
services/<module>/<x>_service.py      business rules; raises src.errors.exceptions, never HTTPException
dependencies/<module>.py              build_x_service(session) + get_x_service + XServiceDep
contracts/schemas/requests/<module>/<x>_requests.py    pydantic request bodies
contracts/schemas/responses/<module>/<x>_responses.py  pydantic response bodies
routers/v1/<module>/<x>.py            thin handlers: Dep in, _to_response(dto) out
routers/v1/__init__.py                api_router: every module router, mounted at /api/v1
```

Reference module: **inventory** (targets, accounts). Copy it.

## Rules

- **Repositories** take an `AsyncSession`, return DTOs (never ORM rows), lists return
  `(rows, total)`. Row locks (`lock=True`) are taken here.
- **Services** take repositories and other services in `__init__`. A service ends a
  unit of work with `await self._repo.commit()` after the action *and* its audit
  event, so both commit or neither. Failure audits that must survive the raised
  error (bad login, bad MFA code) commit before raising.
- **Audit**: every state change calls `AuditService.record(actor, action, ...)` in
  the same transaction.
- **DI**: `build_x_service(session)` is the single wiring. Request handlers use
  `XServiceDep`; the gateway and scheduler open a session from `session_factory()`
  and call `build_x_service(session)`. SQL lives only in repositories.
- **Routers** gate with `dependencies=[Depends(require_permission(CODENAME))]`
  (codenames in `src/core/permissions.py`), take `ActorDep` when they need the actor,
  map DTOs with a local `_to_response`, and declare
  `responses={**UNAUTHORIZED_RESPONSE, ...}`. Envelopes: `APIResponse[T]`,
  `PaginatedAPIResponse[T]`. Errors: `{success, status_code, error: {code, message, details}}`.
- **Permissions**: services decide row visibility (e.g. "see every check-out") with
  `actor.can(CODENAME)`, never with role names.
- **Security tests** (`tests/security/`) gate every change: each route needs a codename or an
  entry in `PUBLIC_ROUTES` (reviewed); crypto refuses wrong keys and any tampered byte; the audit
  table is append-only and edits or deletions break the chain; cross-tenant tests switch on with
  the tenancy step.
- **Tenancy seams** (multi-tenancy is deferred; `TENANCY_KEYS.md` is the approved design):
  - Take the DB session from `SQLSessionDep` (or `current_tenant().session_factory()` outside a
    request), never from `core.db` directly in new code.
  - Encrypt only through the vault service or `TenantKeyService`. Both go through the
    `KeyProvider` (`src/keys/`), and nothing else touches key-encryption keys.
    `tests/security/test_key_boundary.py` enforces this.
  - Per-tenant purpose keys (`KeyPurpose`) are created through `TenantKeyService` and stored
    only wrapped in `keystore.tenant_keys`.
- **Migrations**: raw SQL `migrations/NNN_name.sql`, applied in order, idempotent.
- No file over 500 lines; split by sub-area like MonetX.
