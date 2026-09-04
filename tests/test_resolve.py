from pathlib import Path

import pytest

from nvda_testkit.errors import LauncherResolutionError
from nvda_testkit.resolve import LauncherInfo, resolve_launcher

FIXTURES = Path(__file__).parent / "fixtures"


def _fetcher(mapping):
    """Return a fetch() that serves canned bytes and records the URLs asked for."""
    calls = []

    def fetch(url):
        calls.append(url)
        for fragment, payload in mapping.items():
            if fragment in url:
                return payload
        raise AssertionError(f"unexpected URL requested: {url}")

    fetch.calls = calls
    return fetch


def test_resolves_stable_from_update_check():
    fetch = _fetcher({"nvdaUpdateCheck": (FIXTURES / "update_check_stable.txt").read_bytes()})
    info = resolve_launcher("stable", fetch=fetch)
    assert isinstance(info, LauncherInfo)
    assert info.channel == "stable"
    assert info.version == "2026.1.1"
    assert info.url == "https://download.nvaccess.org/releases/2026.1.1/nvda_2026.1.1.exe"
    assert info.sha1 == "f35e30cd3c1c6375be52d0acaba701c5f6ddc7bd"
    assert info.api_version == "2026.1.1"
    assert info.api_compat_to == "2026.1.0"
    assert "versionType=stable" in fetch.calls[0]


def test_beta_uses_the_beta_version_type():
    fetch = _fetcher({"nvdaUpdateCheck": (FIXTURES / "update_check_stable.txt").read_bytes()})
    resolve_launcher("beta", fetch=fetch)
    assert "versionType=beta" in fetch.calls[0]


def test_resolves_alpha_by_scraping_the_snapshot_index():
    fetch = _fetcher({"snapshots/alpha": (FIXTURES / "snapshot_index_alpha.html").read_bytes()})
    info = resolve_launcher("alpha", fetch=fetch)
    assert info.channel == "alpha"
    assert info.url.startswith("https://download.nvaccess.org/snapshots/alpha/nvda_snapshot_alpha-")
    assert info.url.endswith(".exe")
    assert info.sha1 is None
    assert info.api_version is None


def test_alpha_picks_the_highest_revision_not_the_first_listed():
    html = b"""
      <a href="nvda_snapshot_alpha-9999,aaaaaaaa.exe">x</a>
      <a href="nvda_snapshot_alpha-57360,6864af60.exe">x</a>
      <a href="nvda_snapshot_alpha-100,cccccccc.exe">x</a>
    """
    info = resolve_launcher("alpha", fetch=_fetcher({"snapshots/alpha": html}))
    assert info.version == "alpha-57360,6864af60"
    assert info.url.endswith("nvda_snapshot_alpha-57360,6864af60.exe")


def test_pinned_version_bypasses_the_network_entirely():
    fetch = _fetcher({})
    info = resolve_launcher("2026.1.1", fetch=fetch)
    assert info.channel == "pinned"
    assert info.version == "2026.1.1"
    assert info.url == "https://download.nvaccess.org/releases/2026.1.1/nvda_2026.1.1.exe"
    assert info.sha1 is None
    assert fetch.calls == []


def test_unknown_channel_is_rejected_before_any_request():
    fetch = _fetcher({})
    with pytest.raises(LauncherResolutionError, match="not a known channel"):
        resolve_launcher("nightly", fetch=fetch)
    assert fetch.calls == []


def test_update_check_without_a_launcher_url_is_an_error():
    fetch = _fetcher({"nvdaUpdateCheck": b"version: 2026.1.1\n"})
    with pytest.raises(LauncherResolutionError, match="launcherUrl"):
        resolve_launcher("stable", fetch=fetch)


def test_empty_snapshot_index_is_an_error():
    fetch = _fetcher({"snapshots/alpha": b"<html><body>nothing here</body></html>"})
    with pytest.raises(LauncherResolutionError, match="no alpha snapshot"):
        resolve_launcher("alpha", fetch=fetch)
