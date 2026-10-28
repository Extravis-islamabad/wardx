"""New passwords for rotation, generated to a PasswordPolicy.

The symbol set leaves out characters that device CLIs treat specially:
``?`` (help on Cisco/Huawei), quotes and ``\\`` (quoting), ``$`` and backtick
(expansion), ``!`` (comments / history), and space. Every allowed class appears at
least once so complexity rules on the device are met.
"""

from __future__ import annotations

import secrets

from src.rotation.policy import PasswordPolicy, platform_default, validate

_MAX_TRIES = 1000


def violations(policy: PasswordPolicy, password: str, username: str | None = None) -> list[str]:
    """Every rule of the policy the password breaks (empty = compliant)."""
    found: list[str] = []
    if not policy.min_length <= len(password) <= policy.max_length:
        found.append("length")
    present = {c for c in policy.classes if any(ch in policy.alphabet(c) for ch in password)}
    if len(present) < policy.min_classes:
        found.append("classes")
    allowed = "".join(policy.alphabet(c) for c in policy.classes)
    if any(ch not in allowed for ch in password):
        found.append("alphabet")
    if policy.forbid_leading_symbol and password and not password[0].isalnum():
        found.append("leading_symbol")
    run = 1
    for prev, ch in zip(password, password[1:], strict=False):
        run = run + 1 if ch == prev else 1
        if run > policy.max_repeat:
            found.append("repeat")
            break
    if policy.forbid_username_substring and username and len(username) >= 3:
        low = password.lower()
        if username.lower() in low or username.lower()[::-1] in low:
            found.append("username")
    return found


def generate(policy: PasswordPolicy | None = None, username: str | None = None) -> str:
    """A random password that satisfies ``policy`` (Linux default when omitted)."""
    policy = validate(policy or platform_default("linux"))
    classes = sorted(policy.classes)
    alphabet = "".join(policy.alphabet(c) for c in classes)
    for _ in range(_MAX_TRIES):
        chars = [secrets.choice(policy.alphabet(c)) for c in classes]
        chars += [secrets.choice(alphabet) for _ in range(policy.length - len(chars))]
        # Shuffle so the guaranteed characters are not always first.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        candidate = "".join(chars)
        if not violations(policy, candidate, username):
            return candidate
    raise ValueError("could not generate a password for this policy")  # pragma: no cover


def wrong_password(policy: PasswordPolicy | None = None) -> str:
    """A fresh random password for the negative verify check. Never stored or logged."""
    return generate(policy)
