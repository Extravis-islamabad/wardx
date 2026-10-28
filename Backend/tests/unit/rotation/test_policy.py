"""Password policy resolution and generator compliance (ROTATION.md §3)."""

from __future__ import annotations

import random
from dataclasses import replace

import pytest

from src.core.enums import Platform
from src.rotation.passwords import generate, violations, wrong_password
from src.rotation.policy import (
    ALL_CLASSES,
    PLATFORM_DEFAULTS,
    SAFE_SYMBOLS,
    CharClass,
    PasswordPolicy,
    PolicyError,
    apply_overrides,
    platform_default,
    resolve,
    validate,
)


@pytest.mark.parametrize("platform", list(PLATFORM_DEFAULTS))
def test_platform_defaults_are_valid_and_match_the_spec(platform):
    policy = validate(platform_default(platform))
    expected = {
        Platform.LINUX: (24, 12, 128),
        Platform.WINDOWS: (24, 14, 127),
        Platform.CISCO_IOS: (24, 12, 25),
        Platform.HUAWEI_VRP: (20, 12, 32),
        Platform.MIKROTIK_ROUTEROS: (24, 12, 64),
    }[platform]
    assert (policy.length, policy.min_length, policy.max_length) == expected
    assert "?" not in policy.symbols and policy.symbols == SAFE_SYMBOLS


def test_account_length_only_lengthens_and_is_clamped():
    assert resolve("linux", {}, 40).length == 40
    assert resolve("linux", {}, 12).length == 24  # shorter would be weaker: ignored
    assert resolve("cisco_ios", {}, 40).length == 25  # the device cap wins
    assert resolve("huawei_vrp", {}, None).length == 20


def test_target_override_caps_pull_the_length_down():
    policy = resolve("linux", {"max_length": 16}, 24)
    assert policy.max_length == 16 and policy.length == 16


@pytest.mark.parametrize(
    "overrides",
    [
        {"symbols": "-_?"},  # '?' is CLI help on network devices
        {"symbols": "$"},
        {"min_length": 8},
        {"min_length": 30, "max_length": 20},
        {"max_length": 200},
        {"min_classes": 5},
        {"max_repeat": 1},
        {"classes": ["lower", "emoji"]},
        {"classes": ["symbol"], "symbols": "-_"},  # too few characters
        {"classes": ["symbol"]},  # cannot start with a letter or digit
        {"unknown_rule": 1},
    ],
)
def test_unsafe_or_unsatisfiable_overrides_are_refused(overrides):
    with pytest.raises(PolicyError):
        apply_overrides(platform_default("linux"), overrides)


def _random_policy(rng: random.Random) -> PasswordPolicy:
    while True:
        try:
            return _try_policy(rng)
        except PolicyError:
            continue


def _try_policy(rng: random.Random) -> PasswordPolicy:
    classes = frozenset(rng.sample(sorted(ALL_CLASSES), rng.randint(1, 4)))
    min_length = rng.randint(12, 40)
    max_length = rng.randint(min_length, 128)
    symbols = "".join(rng.sample(SAFE_SYMBOLS, rng.randint(1, len(SAFE_SYMBOLS))))
    return validate(
        PasswordPolicy(
            length=rng.randint(min_length, max_length),
            min_length=min_length,
            max_length=max_length,
            classes=classes,
            min_classes=rng.randint(1, len(classes)),
            symbols=symbols,
            forbid_leading_symbol=rng.random() < 0.8,
            forbid_username_substring=rng.random() < 0.5,
            max_repeat=rng.randint(2, 4),
        )
    )


def test_generated_passwords_comply_with_random_policies():
    rng = random.Random(20261028)  # noqa: S311 - reproducible policies, not secrets
    for _ in range(150):
        policy = _random_policy(rng)
        for _ in range(20):
            pw = generate(policy, "admin")
            assert violations(policy, pw, "admin") == [], (policy, pw)
            assert len(pw) == policy.length


def test_generator_rules_are_actually_checked():
    policy = replace(platform_default("huawei_vrp"), max_repeat=2)
    assert "repeat" in violations(policy, "aaaB1-xxxxxxxxxxxx")
    assert "leading_symbol" in violations(policy, "-abcDEF123456789")
    assert "username" in violations(policy, "xxAdminxx12-Q", "admin")
    assert "username" in violations(policy, "xxNIMDAxx12-Q", "admin")  # reversed (VRP)
    assert "alphabet" in violations(policy, "abcDEF123456?78")
    only_lower = replace(policy, classes=frozenset({CharClass.LOWER}), min_classes=1)
    validate(only_lower)
    assert violations(only_lower, "abcdefghijkl") == []


def test_wrong_password_is_fresh_every_time():
    seen = {wrong_password() for _ in range(50)}
    assert len(seen) == 50
