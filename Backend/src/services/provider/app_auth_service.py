"""Application identity authentication (docs/phase1/CREDENTIAL_PROVIDER.md §2).

Token route (``issue_token``), in this order:
1. too many failed attempts this minute for the client_id or the source IP: 429;
2. the app exists and is enabled, else ``invalid_client`` (never says which part failed);
3. the source IP is in the app's allowlist (empty = nobody), else ``ip_not_allowed``;
4. the secret matches an unrevoked, unexpired secret of the app (argon2id; both slots
   are always checked, so timing does not reveal how many secrets exist).
Every outcome is audited as ``app.token`` (no secret, no token); failures commit their
audit before raising and count against both failure buckets.

Provider routes (``authenticate``): a valid app token (own signing key, ``typ=app``,
audience), the app still enabled with the same token_version, the secret it was issued
for still active, and the source IP allowed. Refusals of an authentic token are audited
as ``secret.app_fetch`` failures; a token that is not even authentic is refused without
an audit event (it identifies nobody).
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from src.contracts.dto.provider.app_dto import AppDTO, AppPrincipalDTO, AppTokenDTO
from src.core.client_ip import in_networks, parse_networks
from src.core.config import Settings, resolve_jwt_secret
from src.core.context import Actor
from src.core.enums import Role
from src.core.security import (
    burn_password_check,
    create_app_token,
    decode_app_token,
    verify_password,
)
from src.errors.exceptions import AppError
from src.models import utcnow
from src.repositories.provider.app_repository import AppRepository
from src.services.audit.audit_service import AuditService
from src.services.provider.app_service import APP_FETCH_ACTION, MAX_ACTIVE_SECRETS
from src.services.provider.provider_errors import (
    InvalidClient,
    InvalidToken,
    IpNotAllowed,
    RateLimited,
)
from src.services.provider.rate_limit_service import (
    RateLimitService,
    client_id_bucket,
    ip_bucket,
)

# Fixed by the approved design: no setting stretches it.
APP_TOKEN_TTL = timedelta(minutes=5)
_BAD_CLIENT = "Invalid client credentials"


def app_actor(app: AppDTO | None, source_ip: str | None, client_id: str | None = None) -> Actor:
    """How an app appears in the audit trail: ``app:<name>``, its id as actor_id."""
    if app is None:
        return Actor(
            id=None, username=f"app:?{(client_id or '')[:40]}", role=Role.USER, source_ip=source_ip
        )
    return Actor(id=app.id, username=f"app:{app.name}", role=Role.USER, source_ip=source_ip)


def ip_allowed(app: AppDTO, source_ip: str | None) -> bool:
    return in_networks(source_ip, parse_networks(app.ip_allowlist))


class AppAuthService:
    def __init__(
        self,
        apps: AppRepository,
        audit: AuditService,
        rate: RateLimitService,
        settings: Settings,
    ) -> None:
        self._apps = apps
        self._audit = audit
        self._rate = rate
        self._settings = settings

    # ── Token route ──

    async def issue_token(
        self, client_id: str | None, client_secret: str | None, source_ip: str | None
    ) -> AppTokenDTO:
        client_id = (client_id or "").strip()[:64]
        buckets = [client_id_bucket(client_id), ip_bucket(source_ip)]
        limit = self._settings.provider_token_failures_per_minute
        retry_after = await self._rate.exceeded(buckets, limit)
        if retry_after is not None:
            await self._token_failure(None, client_id, source_ip, "rate_limited")
            raise RateLimited("Too many failed attempts; try again later", retry_after)

        app = await self._apps.get_by_client_id(client_id) if client_id else None
        if app is None or not app.enabled or not client_secret:
            await self._burn(client_secret or "")
            reason = (
                "unknown_client" if app is None else "disabled" if not app.enabled else "no_secret"
            )
            await self._fail(buckets, app, client_id, source_ip, reason, InvalidClient(_BAD_CLIENT))
        if not ip_allowed(app, source_ip):
            await self._fail(
                buckets,
                app,
                client_id,
                source_ip,
                "ip_not_allowed",
                IpNotAllowed("This source address is not allowed for this application"),
            )
        secret_id = await self._match_secret(app, client_secret)
        if secret_id is None:
            await self._fail(
                buckets, app, client_id, source_ip, "bad_secret", InvalidClient(_BAD_CLIENT)
            )

        now = utcnow()
        await self._apps.touch_secret(secret_id, now)
        await self._audit.record(
            app_actor(app, source_ip),
            "app.token",
            object_type="app",
            object_id=app.id,
            details={"client_id": app.client_id, "secret_id": str(secret_id)},
        )
        await self._apps.commit()
        token = create_app_token(
            secret=resolve_jwt_secret(self._settings),
            app_id=app.id,
            token_version=app.token_version,
            secret_id=secret_id,
            ttl=APP_TOKEN_TTL,
        )
        return AppTokenDTO(access_token=token, expires_in=int(APP_TOKEN_TTL.total_seconds()))

    async def _match_secret(self, app: AppDTO, client_secret: str) -> uuid.UUID | None:
        now = utcnow()
        candidates = [
            s
            for s in await self._apps.unrevoked_hashes(app.id)
            if s.expires_at is None or s.expires_at > now
        ]
        found = None
        for candidate in candidates:
            if await verify_password(candidate.secret_hash, client_secret) and found is None:
                found = candidate.id
        for _ in range(MAX_ACTIVE_SECRETS - len(candidates)):
            await burn_password_check(client_secret)
        return found

    @staticmethod
    async def _burn(client_secret: str) -> None:
        for _ in range(MAX_ACTIVE_SECRETS):
            await burn_password_check(client_secret)

    async def _token_failure(
        self, app: AppDTO | None, client_id: str, source_ip: str | None, reason: str
    ) -> None:
        await self._audit.record(
            app_actor(app, source_ip, client_id),
            "app.token",
            object_type="app",
            object_id=app.id if app else None,
            outcome="failure",
            details={"client_id": client_id[:64], "reason": reason},
        )
        await self._apps.commit()

    async def _fail(
        self,
        buckets: list[str],
        app: AppDTO | None,
        client_id: str,
        source_ip: str | None,
        reason: str,
        error: AppError,
    ) -> None:
        await self._token_failure(app, client_id, source_ip, reason)
        for bucket in buckets:
            await self._rate.hit(bucket, self._settings.provider_token_failures_per_minute)
        raise error

    # ── Provider routes ──

    async def authenticate(self, token: str | None, source_ip: str | None) -> AppPrincipalDTO:
        if not token:
            raise InvalidToken("An application token is required")
        try:
            claims = decode_app_token(token, secret=resolve_jwt_secret(self._settings))
            app_id, secret_id = uuid.UUID(claims["sub"]), uuid.UUID(claims["sid"])
        except (ValueError, KeyError, TypeError) as exc:
            raise InvalidToken("Invalid or expired token") from exc
        app = await self._apps.get(app_id)
        if app is None:
            raise InvalidToken("Invalid or expired token")
        now = utcnow()
        live = {
            s.id
            for s in await self._apps.unrevoked_hashes(app.id)
            if s.expires_at is None or s.expires_at > now
        }
        if not app.enabled or claims.get("tv") != app.token_version or secret_id not in live:
            await self._refuse(app, source_ip, InvalidToken("Invalid or expired token"))
        if not ip_allowed(app, source_ip):
            await self._refuse(
                app,
                source_ip,
                IpNotAllowed("This source address is not allowed for this application"),
            )
        return AppPrincipalDTO(
            id=app.id,
            name=app.name,
            rate_limit_per_minute=app.rate_limit_per_minute,
            source_ip=source_ip,
        )

    async def _refuse(self, app: AppDTO, source_ip: str | None, error: AppError) -> None:
        await self._audit.record(
            app_actor(app, source_ip),
            APP_FETCH_ACTION,
            object_type="app",
            object_id=app.id,
            outcome="failure",
            details={"app_id": str(app.id), "app_name": app.name, "error_code": error.code},
        )
        await self._apps.commit()
        raise error
