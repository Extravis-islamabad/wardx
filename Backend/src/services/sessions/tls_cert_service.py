"""TLS certificate pins per target, for drivers that change over API-SSL (ROTATION.md §15).

The same flow as SSH host keys (host_key_service.py), for the certificate a MikroTik
device presents on API-SSL:

- Probe: read the certificate the device presents now (the TLS handshake only, no API
  word and no credential is sent) and show its SHA-256 fingerprint (over the DER
  encoding) next to the pinned one. Nothing is pinned.
- Accept: re-read the certificate and pin it only if it still has exactly the
  fingerprint the administrator compared with the device. Accepting replaces an
  existing pin and clears a recorded mismatch.
- Reset clears the pin but never a recorded mismatch.
- A rotation or verify that meets another certificate records it on the target
  (one high alert per new certificate) and blocks rotation and verify until a
  certificate is accepted again. Nothing is ever accepted automatically.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from cryptography import x509

from src.contracts.dto.inventory.target_dto import TargetDTO
from src.contracts.dto.sessions.host_key_dto import TlsCertProbeDTO
from src.core.config import get_settings
from src.core.context import Actor
from src.errors.exceptions import ConflictError
from src.models import utcnow
from src.rotation.drivers.mikrotik import API_SSL_DEFAULT_PORT
from src.rotation.drivers.registry import uses_tls_identity
from src.services.sessions.target_identity import TargetIdentityService
from src.transport.routeros_api import Unavailable, fetch_certificate, normalise_fingerprint

MISMATCH_ALERT = "target.tls_cert_changed"


def _describe(pem: str) -> tuple[str, datetime | None]:
    """Subject and expiry of a PEM certificate, for the administrator to read."""
    try:
        cert = x509.load_pem_x509_certificate(pem.encode())
    except ValueError:
        return "(unreadable certificate)", None
    return cert.subject.rfc4514_string() or "(no subject)", cert.not_valid_after_utc


class TlsCertService(TargetIdentityService):
    @staticmethod
    async def _read_cert(target: TargetDTO) -> tuple[str, str]:
        if not uses_tls_identity(target.platform):
            raise ConflictError(
                "Only targets rotated over a TLS API (MikroTik API-SSL) have a certificate pin"
            )
        if not target.api_tls:
            raise ConflictError(
                f"{target.name} offers only the cleartext API; there is no certificate to pin"
            )
        port = target.api_port or API_SSL_DEFAULT_PORT
        timeout = get_settings().target_connect_timeout_seconds
        try:
            return await fetch_certificate(target.address, port, timeout)
        except Unavailable as exc:
            raise ConflictError(
                f"Could not read the API-SSL certificate of {target.name} on port {port}: "
                f"API-SSL not enabled on device ({exc})"
            ) from exc

    async def probe(self, actor: Actor, target_id: uuid.UUID) -> TlsCertProbeDTO:
        """The certificate the target presents now, for comparison. Changes nothing."""
        target = await self._target(target_id)
        await self._require_manage(actor, target_id)
        pem, fingerprint = await self._read_cert(target)
        subject, not_after = _describe(pem)
        return TlsCertProbeDTO(
            target_id=target.id,
            presented_fingerprint=fingerprint,
            subject=subject,
            not_after=not_after,
            pinned_fingerprint=target.tls_cert_fingerprint,
            matches_pin=fingerprint == target.tls_cert_fingerprint,
            mismatch_at=target.tls_cert_mismatch_at,
            mismatch_fingerprint=target.tls_cert_mismatch_fingerprint,
        )

    async def accept(self, actor: Actor, target_id: uuid.UUID, fingerprint: str) -> TargetDTO:
        """Pin the presented certificate, only if it still has the fingerprint the
        administrator compared with the device."""
        target = await self._target(target_id)
        safe_ids = await self._require_manage(actor, target_id)
        expected = normalise_fingerprint(fingerprint)
        pem, presented = await self._read_cert(target)
        if presented != expected:
            await self._audit_per_safe(
                actor,
                "target.tls_cert_accept",
                target_id,
                safe_ids,
                {"expected": expected or fingerprint[:128], "presented": presented},
                outcome="failure",
            )
            await self._targets.commit()
            raise ConflictError(
                "The device now presents a different certificate than the one you compared. "
                "Read it again and compare before accepting.",
                {"presented_fingerprint": presented},
            )
        previous = target.tls_cert_fingerprint
        if previous == presented and target.tls_cert_mismatch_at is None:
            raise ConflictError("This certificate is already pinned")
        await self._targets.accept_tls_cert(
            target_id, pem=pem, fingerprint=presented, learned_at=utcnow()
        )
        action = "target.tls_cert_learned" if previous is None else "target.tls_cert_changed"
        await self._audit_per_safe(
            actor,
            action,
            target_id,
            safe_ids,
            {
                "fingerprint": presented,
                "previous_fingerprint": previous,
                "cleared_mismatch": target.tls_cert_mismatch_fingerprint,
                "via": "accept",
            },
        )
        await self._targets.commit()
        return await self._target(target_id)

    async def reset(self, actor: Actor, target_id: uuid.UUID) -> TargetDTO:
        """Clear the pin. A recorded mismatch stays: only an accept clears it, and
        rotation is refused until a certificate is pinned again."""
        target = await self._target(target_id)
        safe_ids = await self._require_manage(actor, target_id)
        updated = await self._targets.update(
            target_id,
            {"tls_cert_pem": None, "tls_cert_fingerprint": None, "tls_cert_learned_at": None},
        )
        await self._audit_per_safe(
            actor,
            "target.tls_cert_reset",
            target_id,
            safe_ids,
            {"previous_fingerprint": target.tls_cert_fingerprint},
        )
        await self._targets.commit()
        return updated

    async def record_mismatch(
        self, actor: Actor, target_id: uuid.UUID, *, presented: str | None, source: str
    ) -> bool:
        """A device presented a certificate other than the pinned one: record it (which
        blocks rotation and verify), audit it per safe, and raise one high alert per new
        presented certificate. True when this was a new mismatch."""
        target = await self._targets.get(target_id)
        if target is None:
            return False
        new = await self._targets.record_tls_cert_mismatch(
            target_id, presented=presented, seen_at=utcnow()
        )
        details = {
            "pinned_fingerprint": target.tls_cert_fingerprint,
            "presented_fingerprint": presented,
            "source": source,
        }
        await self._audit_per_safe(
            actor,
            "target.tls_cert_mismatch",
            target_id,
            await self._safe_ids(target_id),
            details,
            outcome="failure",
        )
        if new:
            await self._alerts.raise_alert(
                actor,
                kind=MISMATCH_ALERT,
                message=(
                    f"{target.name} presented API-SSL certificate {presented or '(unreadable)'} "
                    f"instead of the pinned {target.tls_cert_fingerprint}. Rotation and verify "
                    "are blocked until an administrator compares and accepts a certificate."
                ),
                object_type="target",
                object_id=target_id,
                details=details,
            )
        await self._targets.commit()
        return new
