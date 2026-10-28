"""Password policy per platform, and how a policy is resolved (ROTATION.md section 3).

Resolution: platform default → target override (device caps, e.g. an old IOS) →
account ``password_length``. An account can only make the policy stricter (longer),
and the result is clamped to the target's min and max. Every policy is validated, so
it is always satisfiable.
"""

from __future__ import annotations

import string
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from src.core.enums import Platform

# Characters device CLIs do not treat specially (see passwords.py). A policy may only
# narrow this set, never widen it.
SAFE_SYMBOLS = "-_.,:+=@#%^*"
# No rotated password is ever shorter than this, whatever a target says.
FLOOR_LENGTH = 12
CEILING_LENGTH = 128
# Fewer distinct characters than this makes too weak (or unsatisfiable) a password.
MIN_ALPHABET = 10


class CharClass(StrEnum):
    LOWER = "lower"
    UPPER = "upper"
    DIGIT = "digit"
    SYMBOL = "symbol"


ALL_CLASSES = frozenset(CharClass)


class PolicyError(ValueError):
    """The policy cannot be satisfied or breaks a safety rule; the message is user-facing."""


@dataclass(frozen=True)
class PasswordPolicy:
    length: int
    min_length: int
    max_length: int
    classes: frozenset[CharClass] = ALL_CLASSES
    min_classes: int = 4
    symbols: str = SAFE_SYMBOLS
    forbid_leading_symbol: bool = True
    forbid_username_substring: bool = False
    max_repeat: int = 3

    def alphabet(self, cls: CharClass) -> str:
        return {
            CharClass.LOWER: string.ascii_lowercase,
            CharClass.UPPER: string.ascii_uppercase,
            CharClass.DIGIT: string.digits,
            CharClass.SYMBOL: self.symbols,
        }[cls]

    def as_dict(self) -> dict[str, Any]:
        return {
            "length": self.length,
            "min_length": self.min_length,
            "max_length": self.max_length,
            "classes": sorted(c.value for c in self.classes),
            "min_classes": self.min_classes,
            "symbols": self.symbols,
            "forbid_leading_symbol": self.forbid_leading_symbol,
            "forbid_username_substring": self.forbid_username_substring,
            "max_repeat": self.max_repeat,
        }


def validate(policy: PasswordPolicy) -> PasswordPolicy:
    """Raise PolicyError unless the policy is safe and satisfiable."""
    if policy.min_length < FLOOR_LENGTH:
        raise PolicyError(f"Minimum length must be at least {FLOOR_LENGTH}")
    if policy.max_length > CEILING_LENGTH:
        raise PolicyError(f"Maximum length must be at most {CEILING_LENGTH}")
    if not policy.min_length <= policy.length <= policy.max_length:
        raise PolicyError("Length must lie between the minimum and maximum length")
    if not policy.classes:
        raise PolicyError("At least one character class is needed")
    if not 1 <= policy.min_classes <= len(policy.classes):
        raise PolicyError("Required classes must be between 1 and the classes allowed")
    if len(policy.classes) > policy.min_length:
        raise PolicyError("Minimum length is too short for every class to appear")
    if set(policy.symbols) - set(SAFE_SYMBOLS):
        raise PolicyError(f"Symbols may only come from {SAFE_SYMBOLS}")
    if CharClass.SYMBOL in policy.classes and not policy.symbols:
        raise PolicyError("The symbol class needs at least one symbol")
    if policy.max_repeat < 2:
        raise PolicyError("Allowed repeats must be at least 2")
    if policy.forbid_leading_symbol and policy.classes == {CharClass.SYMBOL}:
        raise PolicyError("A password of symbols only cannot start with a letter or digit")
    alphabet = set("".join(policy.alphabet(c) for c in policy.classes))
    if len(alphabet) < MIN_ALPHABET:
        raise PolicyError(f"The allowed characters must number at least {MIN_ALPHABET}")
    return policy


_BASE = PasswordPolicy(length=24, min_length=12, max_length=128)

PLATFORM_DEFAULTS: dict[str, PasswordPolicy] = {
    Platform.LINUX: _BASE,
    Platform.WINDOWS: replace(
        _BASE, min_length=14, max_length=127, min_classes=3, forbid_username_substring=True
    ),
    Platform.CISCO_IOS: replace(_BASE, max_length=25),
    Platform.HUAWEI_VRP: replace(
        _BASE, length=20, max_length=32, min_classes=3, forbid_username_substring=True
    ),
    Platform.MIKROTIK_ROUTEROS: replace(_BASE, max_length=64),
}


def platform_default(platform: str) -> PasswordPolicy:
    return PLATFORM_DEFAULTS.get(platform, _BASE)


_OVERRIDE_INT = ("length", "min_length", "max_length", "min_classes", "max_repeat")
_OVERRIDE_BOOL = ("forbid_leading_symbol", "forbid_username_substring")
OVERRIDE_KEYS = frozenset((*_OVERRIDE_INT, *_OVERRIDE_BOOL, "symbols", "classes"))


def apply_overrides(base: PasswordPolicy, overrides: dict[str, Any] | None) -> PasswordPolicy:
    """A target's device-specific overrides on top of the platform default."""
    overrides = overrides or {}
    unknown = set(overrides) - OVERRIDE_KEYS
    if unknown:
        raise PolicyError(f"Unknown policy overrides: {', '.join(sorted(unknown))}")
    changes: dict[str, Any] = {}
    for key in _OVERRIDE_INT:
        if overrides.get(key) is not None:
            changes[key] = int(overrides[key])
    for key in _OVERRIDE_BOOL:
        if overrides.get(key) is not None:
            changes[key] = bool(overrides[key])
    if overrides.get("symbols") is not None:
        changes["symbols"] = str(overrides["symbols"])
    if overrides.get("classes") is not None:
        try:
            changes["classes"] = frozenset(CharClass(c) for c in overrides["classes"])
        except ValueError as exc:
            raise PolicyError("Classes are lower, upper, digit and symbol") from exc
    policy = replace(base, **changes)
    # A lowered cap pulls the generated length down with it.
    if "length" not in changes:
        policy = replace(
            policy, length=max(policy.min_length, min(policy.length, policy.max_length))
        )
    return validate(policy)


def resolve(
    platform: str, target_overrides: dict[str, Any] | None, account_length: int | None
) -> PasswordPolicy:
    """The effective policy for one account (account length only ever lengthens)."""
    policy = apply_overrides(platform_default(platform), target_overrides)
    if account_length:
        wanted = max(policy.length, account_length)
        policy = replace(policy, length=min(wanted, policy.max_length))
    return validate(policy)
