import hashlib

import pytest

from nvda_testkit.download import default_cache_dir, ensure_launcher, sha1_file
from nvda_testkit.errors import HashMismatchError
from nvda_testkit.resolve import LauncherInfo

PAYLOAD = b"pretend this is nvda_2026.1.1.exe"
PAYLOAD_SHA1 = hashlib.sha1(PAYLOAD).hexdigest()


def _info(sha1=PAYLOAD_SHA1, channel="stable", version="2026.1.1"):
    return LauncherInfo(
        channel=channel,
        version=version,
        url="https://example.invalid/nvda.exe",
        sha1=sha1,
        api_version="2026.1.1",
        api_compat_to="2026.1.0",
    )


def _counting_fetch(payload=PAYLOAD):
    calls = []

    def fetch(url):
        calls.append(url)
        return payload

    fetch.calls = calls
    return fetch


def test_downloads_and_verifies(tmp_path):
    fetch = _counting_fetch()
    path = ensure_launcher(_info(), tmp_path, fetch=fetch)
    assert path.read_bytes() == PAYLOAD
    assert sha1_file(path) == PAYLOAD_SHA1
    assert len(fetch.calls) == 1


def test_second_call_is_a_cache_hit(tmp_path):
    fetch = _counting_fetch()
    first = ensure_launcher(_info(), tmp_path, fetch=fetch)
    second = ensure_launcher(_info(), tmp_path, fetch=fetch)
    assert first == second
    assert len(fetch.calls) == 1, "cache hit must not re-download"


def test_digest_mismatch_refuses_and_leaves_nothing_executable(tmp_path):
    fetch = _counting_fetch(b"tampered payload")
    info = _info()
    with pytest.raises(HashMismatchError) as excinfo:
        ensure_launcher(info, tmp_path, fetch=fetch)
    assert excinfo.value.expected == PAYLOAD_SHA1
    assert list(tmp_path.glob("*.exe")) == [], "a bad download must not be left in the cache"


def test_a_corrupted_cache_entry_is_re_downloaded(tmp_path):
    fetch = _counting_fetch()
    path = ensure_launcher(_info(), tmp_path, fetch=fetch)
    path.write_bytes(b"corrupted on disk")
    again = ensure_launcher(_info(), tmp_path, fetch=fetch)
    assert again.read_bytes() == PAYLOAD
    assert len(fetch.calls) == 2


def test_unverifiable_channels_still_cache_and_record_their_digest(tmp_path):
    fetch = _counting_fetch()
    info = _info(sha1=None, channel="alpha", version="alpha-57360,6864af60")
    path = ensure_launcher(info, tmp_path, fetch=fetch)
    assert path.exists()
    digest_note = path.with_suffix(".sha1")
    assert digest_note.read_text().strip() == PAYLOAD_SHA1
    ensure_launcher(info, tmp_path, fetch=fetch)
    assert len(fetch.calls) == 1


def test_partial_downloads_are_never_visible_under_the_final_name(tmp_path):
    def exploding_fetch(url):
        raise OSError("connection reset")

    info = _info()
    with pytest.raises(OSError, match="connection reset"):
        ensure_launcher(info, tmp_path, fetch=exploding_fetch)
    assert list(tmp_path.iterdir()) == []


def test_default_cache_dir_honours_the_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("NVDA_TESTKIT_CACHE", str(tmp_path / "somewhere"))
    assert default_cache_dir() == tmp_path / "somewhere"
    monkeypatch.delenv("NVDA_TESTKIT_CACHE")
    assert default_cache_dir().name == "nvda-testkit"
