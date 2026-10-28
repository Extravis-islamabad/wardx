"""Ticket numbers on access requests, per the safe's ``ticket_mode`` and ``ticket_pattern``.

Patterns are checked when the policy is saved: at most ``MAX_PATTERN_LENGTH`` characters,
must compile, and constructs that can backtrack catastrophically (nested quantifiers,
backreferences) are refused. Tickets themselves are capped at 100 characters by the
request schema, which bounds matching time further.

Seam for SupportX: ``TicketValidator`` is the interface; ``RegexTicketValidator`` checks
format only. A SupportX validator (does the ticket exist, is it open, is it assigned to
the requester) implements the same ``validate`` and is wired in
``src/dependencies/access.py`` without touching the request service.
"""

from __future__ import annotations

import re
from typing import Protocol

from src.contracts.dto.safes.approval_policy_dto import ApprovalPolicyDTO
from src.core.enums import TicketMode
from src.errors.exceptions import AppError

MAX_PATTERN_LENGTH = 200
# A quantified group that itself contains a quantifier, e.g. (a+)+ or (\w*)*{2,}.
_NESTED_QUANTIFIER = re.compile(r"\((?:[^()\\]|\\.)*[+*}](?:[^()\\]|\\.)*\)\s*[+*{]")
_BACKREFERENCE = re.compile(r"\\[1-9]|\(\?P=")


class InvalidTicket(AppError):
    status_code = 422
    code = "invalid_ticket"


class InvalidTicketPattern(AppError):
    status_code = 422
    code = "invalid_ticket_pattern"


def check_pattern(pattern: str) -> str:
    """The pattern if it is safe to store; InvalidTicketPattern otherwise."""
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise InvalidTicketPattern(f"Ticket pattern is longer than {MAX_PATTERN_LENGTH} characters")
    try:
        re.compile(pattern)
    except re.error as exc:
        raise InvalidTicketPattern(
            f"Ticket pattern is not a valid regular expression: {exc}"
        ) from exc
    if _NESTED_QUANTIFIER.search(pattern) or _BACKREFERENCE.search(pattern):
        raise InvalidTicketPattern(
            "Ticket pattern uses nested quantifiers or backreferences, which can make "
            "matching very slow; simplify it"
        )
    return pattern


class TicketValidator(Protocol):
    async def validate(self, policy: ApprovalPolicyDTO, ticket: str | None) -> str | None:
        """The ticket to store (normalised), or InvalidTicket."""


class RegexTicketValidator:
    async def validate(self, policy: ApprovalPolicyDTO, ticket: str | None) -> str | None:
        ticket = (ticket or "").strip() or None
        mode = TicketMode(policy.ticket_mode)
        if mode == TicketMode.OFF:
            return ticket  # not asked for; kept as given, never validated
        if ticket is None:
            if mode == TicketMode.REQUIRED:
                raise InvalidTicket("This safe requires a ticket number")
            return None
        if policy.ticket_pattern and not re.fullmatch(policy.ticket_pattern, ticket):
            raise InvalidTicket(
                f"Ticket '{ticket}' does not match this safe's format ({policy.ticket_pattern})"
            )
        return ticket
