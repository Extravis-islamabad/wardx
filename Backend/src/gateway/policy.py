"""Command rules, and reconstructing typed command lines from raw keystrokes.

The gateway passes keystrokes straight through, so device features keep
working: ``?`` help, tab completion, ``--More--`` pagers that want a single
space. The command a user runs is rebuilt from what they type, and checked
when they press Enter; a denied line is erased on the device before it runs.

Keys that edit the line where the gateway cannot follow (arrow keys, history
recall, tab completion, cursor movement) would let a denied command run
unseen. When the session has deny rules (``restricted``) those keys are
dropped and the user hears a bell; otherwise they pass and the logged line is
marked ``edited``.
"""

from __future__ import annotations

import codecs
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

MAX_PATTERN_LENGTH = 500

CR, LF, TAB, ESC, DEL, BS = 0x0D, 0x0A, 0x09, 0x1B, 0x7F, 0x08
CTRL_C, CTRL_D, CTRL_L, CTRL_U, CTRL_W, CTRL_Z = 0x03, 0x04, 0x0C, 0x15, 0x17, 0x1A
# Control keys that leave the line in a state we can still follow.
_CLEARS_LINE = {CTRL_C, CTRL_U, CTRL_Z}
_HARMLESS = {CTRL_D, CTRL_L}


# ── Rules ──


@dataclass(frozen=True)
class Rule:
    id: uuid.UUID | None
    regex: re.Pattern[str]
    description: str | None


def compile_pattern(pattern: str) -> re.Pattern[str]:
    if not pattern or len(pattern) > MAX_PATTERN_LENGTH:
        raise ValueError(f"pattern must be 1-{MAX_PATTERN_LENGTH} characters")
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"invalid regular expression: {exc}") from exc


def normalise(command: str) -> str:
    """Collapse whitespace, so ``reload  in 5`` cannot dodge ``^reload in``."""
    return " ".join(command.split())


@dataclass(frozen=True)
class CommandPolicy:
    rules: tuple[Rule, ...] = ()

    @classmethod
    def build(cls, rules: Iterable[tuple[uuid.UUID | None, str, str | None]]) -> CommandPolicy:
        return cls(tuple(Rule(rid, compile_pattern(p), d) for rid, p, d in rules))

    @property
    def restricted(self) -> bool:
        return bool(self.rules)

    def check(self, command: str) -> Rule | None:
        line = normalise(command)
        if not line:
            return None
        for rule in self.rules:
            if rule.regex.search(line):
                return rule
        return None


# ── Keystroke tracking ──


@dataclass(frozen=True)
class Forward:
    data: bytes


@dataclass(frozen=True)
class Submit:
    line: str
    edited: bool
    # Bytes to send to remove this line from the device's input before it runs.
    erase: bytes
    enter: bytes


@dataclass(frozen=True)
class Bell:
    pass


Event = Forward | Submit | Bell


@dataclass
class LineTracker:
    restricted: bool
    _chars: list[str] = field(default_factory=list)
    _edited: bool = False
    _decoder: codecs.IncrementalDecoder = field(
        default_factory=lambda: codecs.getincrementaldecoder("utf-8")(errors="replace")
    )
    _erase_key: bytes = bytes([DEL])
    _escape: bytearray | None = None
    _last_was_cr: bool = False

    def feed(self, data: bytes) -> list[Event]:
        events: list[Event] = []
        pending = bytearray()

        def flush() -> None:
            if pending:
                events.append(Forward(bytes(pending)))
                pending.clear()

        for b in data:
            if self._escape is not None:
                self._escape.append(b)
                if self._escape_complete():
                    seq, self._escape = bytes(self._escape), None
                    if self.restricted:
                        flush()
                        events.append(Bell())
                    else:
                        self._edited = True
                        pending += seq
                continue

            if b == LF and self._last_was_cr:
                # CR LF from the client is one Enter; the CR already submitted.
                self._last_was_cr = False
                continue
            self._last_was_cr = b == CR

            if b in (CR, LF):
                flush()
                events.append(self._submit(bytes([b])))
            elif b == ESC:
                self._escape = bytearray([b])
            elif b in (DEL, BS):
                self._erase_key = bytes([b])
                if self._chars:
                    self._chars.pop()
                pending.append(b)
            elif b in _CLEARS_LINE:
                self._reset()
                pending.append(b)
            elif b == CTRL_W:
                while self._chars and self._chars[-1] == " ":
                    self._chars.pop()
                while self._chars and self._chars[-1] != " ":
                    self._chars.pop()
                pending.append(b)
            elif b in _HARMLESS:
                pending.append(b)
            elif b < 0x20 or b == TAB:
                if self.restricted:
                    flush()
                    events.append(Bell())
                else:
                    self._edited = True
                    pending.append(b)
            else:
                self._chars.extend(self._decoder.decode(bytes([b])))
                pending.append(b)
        flush()
        return events

    def _escape_complete(self) -> bool:
        seq = self._escape
        if len(seq) < 2:
            return False
        if seq[1] == ord("["):  # CSI: parameters, then a final byte 0x40-0x7E
            return len(seq) > 2 and 0x40 <= seq[-1] <= 0x7E
        if seq[1] == ord("O"):  # SS3: one more byte
            return len(seq) == 3
        return True  # ESC + one character (Alt-key)

    def _submit(self, enter: bytes) -> Submit:
        line = "".join(self._chars)
        submit = Submit(line, self._edited, self._erase_key * len(self._chars), enter)
        self._reset()
        return submit

    def _reset(self) -> None:
        self._chars.clear()
        self._edited = False
