import io
import json

import pytest

from src.gateway.naming import parse_login
from src.gateway.policy import Bell, CommandPolicy, Forward, LineTracker, Submit, compile_pattern
from src.gateway.recorder import AsciicastRecorder, file_sha256
from src.gateway.target import host_key_algs


def _submits(events):
    return [e for e in events if isinstance(e, Submit)]


def _forwarded(events) -> bytes:
    return b"".join(e.data for e in events if isinstance(e, Forward))


# ── Rules ──


def test_rule_matching_ignores_case_and_extra_spaces():
    policy = CommandPolicy.build([(None, r"^reload\b", "no reloads")])
    assert policy.check("RELOAD") is not None
    assert policy.check("  reload   in 5") is not None
    assert policy.check("show reload") is None
    assert policy.check("") is None


def test_invalid_or_huge_patterns_rejected():
    with pytest.raises(ValueError):
        compile_pattern("(unclosed")
    with pytest.raises(ValueError):
        compile_pattern("a" * 501)


# ── Line tracking ──


def test_typed_line_with_backspace_and_enter():
    t = LineTracker(restricted=False)
    events = t.feed(b"shox\x7fw ver\r")
    (sub,) = _submits(events)
    assert sub.line == "show ver" and not sub.edited and sub.enter == b"\r"
    assert _forwarded(events) == b"shox\x7fw ver"


def test_line_split_across_chunks_and_crlf_is_one_enter():
    t = LineTracker(restricted=False)
    assert _submits(t.feed(b"rel")) == []
    subs = _submits(t.feed(b"oad\r\n"))
    assert [s.line for s in subs] == ["reload"]


def test_erase_bytes_match_line_length_and_users_backspace_key():
    t = LineTracker(restricted=True)
    t.feed(b"x\x08")  # user's terminal sends ^H
    (sub,) = _submits(t.feed(b"reload\r"))
    assert sub.erase == b"\x08" * 6


def test_ctrl_u_and_ctrl_c_clear_the_line():
    t = LineTracker(restricted=True)
    (sub,) = _submits(t.feed(b"rm -rf /\x15ls\r"))
    assert sub.line == "ls"
    (sub,) = _submits(t.feed(b"reload\x03show run\r"))
    assert sub.line == "show run"


def test_ctrl_w_deletes_a_word():
    t = LineTracker(restricted=False)
    (sub,) = _submits(t.feed(b"show running\x17ip\r"))
    assert sub.line == "show ip"


def test_restricted_mode_drops_arrows_tab_and_history_keys():
    t = LineTracker(restricted=True)
    events = t.feed(b"\x1b[Ash\tow\x10\r")
    assert sum(isinstance(e, Bell) for e in events) == 3
    assert b"\x1b" not in _forwarded(events) and b"\t" not in _forwarded(events)
    (sub,) = _submits(events)
    assert sub.line == "show" and not sub.edited


def test_escape_sequence_split_across_reads_is_still_dropped():
    t = LineTracker(restricted=True)
    first = t.feed(b"\x1b[")
    second = t.feed(b"1;5D")
    assert not _forwarded(first + second)
    assert sum(isinstance(e, Bell) for e in second) == 1


def test_unrestricted_mode_passes_editing_keys_and_flags_the_line():
    t = LineTracker(restricted=False)
    events = t.feed(b"\x1b[Ash run\r")
    assert _forwarded(events).startswith(b"\x1b[A")
    (sub,) = _submits(events)
    assert sub.edited


def test_utf8_input_is_reassembled():
    t = LineTracker(restricted=False)
    data = "echo héllo\r".encode()
    events = []
    for i in range(len(data)):
        events += t.feed(data[i : i + 1])
    assert _submits(events)[0].line == "echo héllo"


# ── Login names ──


def test_login_name_forms():
    full = parse_login("alice%root%core-sw-1")
    assert (full.wardx_user, full.account, full.target) == ("alice", "root", "core-sw-1")
    short = parse_login("alice%core-sw-1")
    assert short.account is None and short.target == "core-sw-1"
    for bad in ("alice", "a%%b", "a%b%c%d", "%root%x"):
        with pytest.raises(ValueError):
            parse_login(bad)


# ── Recording ──


def test_recording_is_valid_asciicast_and_hash_matches_file(tmp_path):
    sink = io.BytesIO()
    rec = AsciicastRecorder(sink, width=100, height=30, term="xterm", title="t")
    rec.output("héllo".encode()[:2])  # split UTF-8 sequence
    rec.output("héllo".encode()[2:])
    rec.resize(120, 40)
    rec.marker("blocked: reload")
    sha, size = rec.close()
    (tmp_path / "s.cast").write_bytes(sink.getvalue())
    lines = (tmp_path / "s.cast").read_text().splitlines()
    header = json.loads(lines[0])
    assert header["version"] == 2 and header["width"] == 100
    events = [json.loads(line) for line in lines[1:]]
    assert "".join(e[2] for e in events if e[1] == "o") == "héllo"
    assert [e[1] for e in events][-2:] == ["r", "m"]
    assert sha == file_sha256(tmp_path / "s.cast")
    assert size == (tmp_path / "s.cast").stat().st_size


def test_pinned_rsa_key_offers_sha2_signatures_first():
    # Regression: offering only "ssh-rsa" (SHA-1) made OpenSSH 8.8+ refuse pinned RSA hosts.
    import asyncssh

    rsa = asyncssh.generate_private_key("ssh-rsa")
    assert host_key_algs(rsa)[:2] == ["rsa-sha2-256", "rsa-sha2-512"]
    assert host_key_algs(asyncssh.generate_private_key("ssh-ed25519")) == ["ssh-ed25519"]
