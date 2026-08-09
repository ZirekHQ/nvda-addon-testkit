"""The nvda-testkit CLI: provision, doctor, and error/exit-code handling."""

from __future__ import annotations

import pytest

from nvda_testkit import cli
from nvda_testkit.errors import LauncherResolutionError
from nvda_testkit.portable import PortableNvda
from nvda_testkit.resolve import LauncherInfo


def _info(channel="stable", version="2026.1.1") -> LauncherInfo:
    return LauncherInfo(
        channel=channel,
        version=version,
        url=f"https://example.invalid/{channel}.exe",
        sha1="deadbeef",
        api_version="2026.1.0",
        api_compat_to="2026.1.0",
    )


def test_provision_prints_channel_info_and_returns_0(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: _info(channel))
    launcher = tmp_path / "nvda_stable.exe"
    monkeypatch.setattr(cli, "ensure_launcher", lambda info: launcher)

    result = cli.main(["provision", "--channel", "stable"])

    assert result == 0
    out = capsys.readouterr().out
    assert "channel:     stable" in out
    assert f"launcher:    {launcher}" in out


def test_provision_reports_no_published_digest(monkeypatch, capsys, tmp_path):
    info = LauncherInfo(
        channel="alpha",
        version="alpha-1,abc",
        url="https://example.invalid/a.exe",
        sha1=None,
        api_version=None,
        api_compat_to=None,
    )
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: info)
    monkeypatch.setattr(cli, "ensure_launcher", lambda info: tmp_path / "a.exe")

    cli.main(["provision", "--channel", "alpha"])

    assert "sha1:        (none published)" in capsys.readouterr().out


def test_provision_with_portable_path_creates_a_portable_copy(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: _info())
    monkeypatch.setattr(cli, "ensure_launcher", lambda info: tmp_path / "nvda.exe")
    portable_root = tmp_path / "portable"
    monkeypatch.setattr(
        cli,
        "create_portable",
        lambda launcher, dest: PortableNvda(
            root=portable_root,
            exe=portable_root / "nvda.exe",
            user_config=portable_root / "userConfig",
            addons_dir=portable_root / "userConfig" / "addons",
        ),
    )

    result = cli.main(["provision", "--portable-path", str(portable_root)])

    assert result == 0
    assert f"portable:    {portable_root}" in capsys.readouterr().out


def test_provision_surfaces_a_testkit_error_as_exit_1(monkeypatch, capsys):
    def explode(channel):
        raise LauncherResolutionError("no launcherUrl in response")

    monkeypatch.setattr(cli, "resolve_launcher", explode)

    result = cli.main(["provision"])

    assert result == 1
    assert "error: no launcherUrl in response" in capsys.readouterr().err


def test_doctor_reports_missing_spy_bundle_as_a_failure(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "spy_bundle_path", lambda: tmp_path / "missing.nvda-addon")
    monkeypatch.setattr(cli, "default_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: _info(channel))

    result = cli.main(["doctor"])

    assert result == 1
    out = capsys.readouterr().out
    assert "MISSING" in out
    assert "problem(s) found" in out


def test_doctor_reports_ok_when_everything_resolves(monkeypatch, capsys, tmp_path):
    bundle = tmp_path / "nvda-testkit-spy.nvda-addon"
    bundle.write_bytes(b"fake bundle")
    monkeypatch.setattr(cli, "spy_bundle_path", lambda: bundle)
    monkeypatch.setattr(cli, "default_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: _info(channel))

    result = cli.main(["doctor"])

    assert result == 0
    assert capsys.readouterr().out.strip().endswith("OK")


def test_doctor_counts_a_failed_channel_resolution(monkeypatch, capsys, tmp_path):
    bundle = tmp_path / "nvda-testkit-spy.nvda-addon"
    bundle.write_bytes(b"fake bundle")
    monkeypatch.setattr(cli, "spy_bundle_path", lambda: bundle)
    monkeypatch.setattr(cli, "default_cache_dir", lambda: tmp_path / "cache")

    def resolve(channel):
        if channel == "beta":
            raise LauncherResolutionError("update-check returned nothing usable")
        return _info(channel)

    monkeypatch.setattr(cli, "resolve_launcher", resolve)

    result = cli.main(["doctor"])

    assert result == 1
    out = capsys.readouterr().out
    assert "beta    -> FAILED: update-check returned nothing usable" in out
    assert "1 problem(s) found" in out


def test_doctor_full_skips_the_portable_copy_off_windows(monkeypatch, capsys, tmp_path):
    """--full only creates a real portable copy on Windows; elsewhere it is a no-op."""
    bundle = tmp_path / "nvda-testkit-spy.nvda-addon"
    bundle.write_bytes(b"fake bundle")
    monkeypatch.setattr(cli, "spy_bundle_path", lambda: bundle)
    monkeypatch.setattr(cli, "default_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(cli, "resolve_launcher", lambda channel: _info(channel))
    monkeypatch.setattr(cli.sys, "platform", "linux")

    def unexpected_create_portable(launcher, dest):
        raise AssertionError("create_portable must not run off Windows")

    monkeypatch.setattr(cli, "create_portable", unexpected_create_portable)

    result = cli.main(["doctor", "--full"])

    assert result == 0


def test_main_requires_a_subcommand(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main([])
    assert excinfo.value.code != 0


def test_version_flag_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--version"])
    assert excinfo.value.code == 0
