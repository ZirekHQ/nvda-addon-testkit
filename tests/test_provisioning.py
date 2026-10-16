"""Guards around the start-and-connect sequence in provision_fake/provision."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from nvda_testkit import provisioning
from nvda_testkit.errors import NvdaStartupError, UnsupportedPlatformError
from nvda_testkit.portable import PortableNvda
from nvda_testkit.settings import TestkitSettings

FAKE = Path(__file__).parent / "fake_nvda.py"


def test_provision_refuses_off_windows(monkeypatch):
    monkeypatch.setattr(provisioning.sys, "platform", "linux")

    settings = TestkitSettings()
    with pytest.raises(UnsupportedPlatformError, match="needs Windows"):
        provisioning.provision(settings)


def test_a_malformed_handshake_does_not_leak_the_process(monkeypatch):
    """A handshake payload that is valid JSON but missing a required key must
    surface as an NvdaStartupError and not leave the FakeNvda subprocess running.
    """
    monkeypatch.setenv("FAKE_NVDA_SCRIPT", json.dumps({"bad_handshake": True}))

    created: list[provisioning.NvdaProcess] = []
    real_process_class = provisioning.NvdaProcess

    class RecordingProcess(real_process_class):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(provisioning, "NvdaProcess", RecordingProcess)

    settings = TestkitSettings()
    with pytest.raises(NvdaStartupError, match="not a valid handshake"):
        provisioning.provision_fake(settings, FAKE)

    assert created, "expected an NvdaProcess to have been constructed"
    assert created[0].is_running is False, "the leaked subprocess must be killed on failure"


def _portable(launcher: Path, dest: Path) -> PortableNvda:
    return PortableNvda(
        dest, dest / "nvda.exe", dest / "userConfig", dest / "userConfig" / "addons"
    )


def _stub_windows_provisioning(monkeypatch, tmp_path, fail_at: str) -> tuple[Path, list[Path]]:
    workdir = tmp_path / "work"
    extracted: list[Path] = []
    monkeypatch.setattr(provisioning.sys, "platform", "win32")
    monkeypatch.setattr(provisioning, "resolve_launcher", lambda channel: object())
    monkeypatch.setattr(provisioning, "ensure_launcher", lambda info, cache: tmp_path / "l.exe")
    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix: str(workdir))
    monkeypatch.setattr(provisioning, "create_portable", _portable)
    monkeypatch.setattr(provisioning, "require_spy_bundle", lambda: tmp_path / "spy.nvda-addon")
    monkeypatch.setattr(provisioning, "extract_addon", lambda bundle, dest: extracted.append(dest))

    def boom(*args, **kwargs):
        raise NvdaStartupError(f"{fail_at} failed")

    monkeypatch.setattr(provisioning, fail_at, boom)
    workdir.mkdir()
    return workdir, extracted


@pytest.mark.parametrize("fail_at", ["create_portable", "require_spy_bundle", "extract_addon"])
def test_provision_removes_its_workdir_when_preparing_the_copy_fails(
    monkeypatch, tmp_path, fail_at
):
    workdir, _ = _stub_windows_provisioning(monkeypatch, tmp_path, fail_at)
    settings = TestkitSettings(out_dir=tmp_path / "out")

    with pytest.raises(NvdaStartupError, match=fail_at):
        provisioning.provision(settings)

    assert not workdir.exists()


def test_provision_kills_and_cleans_up_when_nvda_never_starts(monkeypatch, tmp_path):
    workdir, extracted = _stub_windows_provisioning(monkeypatch, tmp_path, "_start")
    killed = []
    monkeypatch.setattr(provisioning.NvdaProcess, "kill", lambda self: killed.append(self))
    settings = TestkitSettings(out_dir=tmp_path / "out")

    with pytest.raises(NvdaStartupError, match="_start failed"):
        provisioning.provision(settings)

    addons = workdir / "nvda" / "userConfig" / "addons"
    assert extracted == [addons / provisioning.SPY_ADDON_DIRNAME]
    assert len(killed) == 1
    assert not workdir.exists()
