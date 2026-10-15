import hashlib

import pytest

import nvda_testkit
from nvda_testkit.download import ensure_launcher
from nvda_testkit.errors import LauncherResolutionError, SettingsError
from nvda_testkit.portable import render_nvda_ini
from nvda_testkit.resolve import LauncherInfo, _resolve_released
from nvda_testkit.settings import load_settings

PAYLOAD = b"launcher"


def _info(sha1=None):
    return LauncherInfo("alpha", "a-1", "https://download.nvaccess.org/x.exe", sha1, None, None)


def test_package_root_exports_public_types():
    for name in nvda_testkit.__all__:
        assert getattr(nvda_testkit, name) is not None


def test_cached_launcher_swapped_after_first_download_is_refetched(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return PAYLOAD

    path = ensure_launcher(_info(), tmp_path, fetch=fetch)
    path.write_bytes(b"poisoned")
    again = ensure_launcher(_info(), tmp_path, fetch=fetch)
    assert again.read_bytes() == PAYLOAD
    assert len(calls) == 2


def test_uppercase_published_digest_matches(tmp_path):
    digest = hashlib.sha1(PAYLOAD).hexdigest().upper()
    path = ensure_launcher(_info(digest), tmp_path, fetch=lambda url: PAYLOAD)
    assert path.read_bytes() == PAYLOAD


def test_launcher_url_must_be_https_nvaccess():
    body = "launcherUrl: http://evil.example/n.exe\nversion: 1"
    with pytest.raises(LauncherResolutionError, match="Refusing launcher URL"):
        _resolve_released("stable", lambda url: body.encode())


def test_string_false_is_not_true(tmp_path):
    cfg = tmp_path / "pyproject.toml"
    cfg.write_text('[tool.nvda-testkit]\nallow-eval = "false"\n')
    assert load_settings(cfg).allow_eval is False


def test_invalid_boolean_raises_settings_error(tmp_path):
    cfg = tmp_path / "pyproject.toml"
    cfg.write_text('[tool.nvda-testkit]\nallow-eval = "maybe"\n')
    with pytest.raises(SettingsError):
        load_settings(cfg)


def test_unknown_key_warns(tmp_path):
    cfg = tmp_path / "pyproject.toml"
    cfg.write_text("[tool.nvda-testkit]\nallow_eval = true\n")
    with pytest.warns(UserWarning, match="allow_eval"):
        load_settings(cfg)


def test_ini_quotes_special_strings_and_renders_lists():
    ini = render_nvda_ini({"x": {"a": "one, two", "b": ["p", "q"], "c": True}})
    assert 'a = "one, two"' in ini
    assert "b = p, q" in ini
    assert "c = True" in ini
