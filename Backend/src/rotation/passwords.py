"""New passwords for rotation.

The symbol set leaves out characters that device CLIs treat specially:
``?`` (help on Cisco/Huawei), quotes and ``\\`` (quoting), ``$`` and backtick
(expansion), ``!`` (comments / history), and space. Every class appears at
least once so complexity rules on the device are met.
"""

from __future__ import annotations

import secrets
import string

SYMBOLS = "-_.,:+=@#%^*"
_CLASSES = (string.ascii_lowercase, string.ascii_uppercase, string.digits, SYMBOLS)
_ALPHABET = "".join(_CLASSES)


def generate(length: int = 24) -> str:
    if length < 12:
        raise ValueError("rotation passwords are at least 12 characters")
    while True:
        chars = [secrets.choice(c) for c in _CLASSES]
        chars += [secrets.choice(_ALPHABET) for _ in range(length - len(chars))]
        # Shuffle so the guaranteed characters are not always first.
        for i in range(len(chars) - 1, 0, -1):
            j = secrets.randbelow(i + 1)
            chars[i], chars[j] = chars[j], chars[i]
        candidate = "".join(chars)
        # Some CLIs mishandle a leading symbol (e.g. '#' or '-' read as a flag).
        if candidate[0].isalnum():
            return candidate
