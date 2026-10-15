from __future__ import annotations

import sys
import zipfile
from pathlib import Path

import pytest

from nvda_testkit import provisioning, spybundle
from nvda_testkit.errors import ProvisionError
from nvda_testkit.portable import PortableNvda
from nvda_testkit.process import NvdaProcess, Ownership, nvda_argv
from nvda_testkit.settings import load_settings


class _Closable:
    def __init__(self, order, name):
        self.order, self.name = order, name

    def close(self):
        self.order.append(self.name)

    def quit(self, timeout):
        self.order.append(self.name)


def test_teardown_closes_rpc_then_quits_process_then_removes_workdir(tmp_path):
    order: list[str] = []
    workdir = tmp_path / "w"
    workdir.mkdir()
    prov = provisioning.Provisioned(
        _Closable(order, "process"), _Closable(order, "rpc"), workdir, keep=False
    )
    prov.teardown()
    assert order == ["rpc", "process"]
    assert not workdir.exists()


def test_teardown_keeps_workdir_when_asked_and_still_quits_after_rpc_failure(tmp_path):
    order: list[str] = []

    class Boom(_Closable):
        def close(self):
            raise RuntimeError("close failed")

    prov = provisioning.Provisioned(
        _Closable(order, "process"), Boom(order, "rpc"), tmp_path, keep=True
    )
    with pytest.raises(RuntimeError):
        prov.teardown()
    assert order == ["process"]
    assert tmp_path.exists()


def test_provision_fake_start_helper_builds_a_scaled_client(monkeypatch):
    class Process:
        token = "tok"

        def start(self, timeout):
            from nvda_testkit.handshake import Handshake

            return Handshake(7, 1, "v", None, None, token="hdr")

    from nvda_testkit.settings import TestkitSettings

    rpc = provisioning._start(Process(), TestkitSettings(timeout_scale=2.0), timeout=1)
    assert (rpc.port, rpc.token, rpc.timeout_scale) == (7, "tok", 2.0)


def test_require_spy_bundle_reports_a_missing_bundle(monkeypatch, tmp_path):
    monkeypatch.setattr(spybundle, "spy_bundle_path", lambda: tmp_path / "missing.nvda-addon")
    with pytest.raises(ProvisionError, match="build_spy"):
        spybundle.require_spy_bundle()


def test_require_spy_bundle_returns_an_existing_bundle(monkeypatch, tmp_path):
    bundle = tmp_path / spybundle.BUNDLE_NAME
    bundle.write_bytes(b"")
    monkeypatch.setattr(spybundle, "spy_bundle_path", lambda: bundle)
    assert spybundle.require_spy_bundle() == bundle


def test_spy_bundle_path_ends_with_the_bundle_name():
    assert spybundle.spy_bundle_path().name == spybundle.BUNDLE_NAME


def test_nvda_argv_minimal_and_extra_flags(tmp_path):
    portable = PortableNvda(tmp_path, tmp_path / "nvda.exe", tmp_path / "cfg", tmp_path / "a")
    argv = nvda_argv(portable, tmp_path / "l.log", minimal=True, extra=["--x"])
    assert argv[-2:] == ["--minimal", "--x"]


def test_log_tail_without_a_log_file_says_so(tmp_path):
    proc = NvdaProcess([sys.executable], tmp_path)
    assert proc.log_tail() == "(no NVDA log available)"


def test_log_tail_returns_only_the_last_lines(tmp_path):
    log = tmp_path / "n.log"
    log.write_text("\n".join(f"line{n}" for n in range(10)), encoding="utf-8")
    proc = NvdaProcess([sys.executable], tmp_path, log_file=log)
    proc.log_file = log
    assert proc.log_tail(lines=2) == "line8\nline9"


def test_a_new_process_is_not_running_and_owns_its_process(tmp_path):
    proc = NvdaProcess([sys.executable], tmp_path)
    assert proc.is_running is False
    assert proc._ownership is Ownership.SPAWNED
    proc.quit()
    proc.kill()


def test_environment_carries_token_and_out_dir(tmp_path):
    proc = NvdaProcess([sys.executable], tmp_path, token="abc", env={"X": "1"})
    env = proc._environment()
    assert (env["NVDA_TESTKIT_TOKEN"], env["X"]) == ("abc", "1")
    assert env["NVDA_TESTKIT_OUTDIR"] == str(tmp_path.resolve())


def test_extract_addon_requires_manifest_name_in_bundle(tmp_path):
    bundle = tmp_path / "b.nvda-addon"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("manifest.ini", "name = x\n")
    from nvda_testkit.portable import extract_addon

    extract_addon(bundle, tmp_path / "out")
    assert (tmp_path / "out" / "manifest.ini").is_file()


def test_cache_dir_comes_from_the_environment_when_unset_in_pyproject(tmp_path):
    settings = load_settings(tmp_path / "none.toml", environ={"NVDA_TESTKIT_CACHE": "/c"})
    assert settings.cache_dir == Path("/c")


def test_pyproject_cache_dir_beats_the_environment(tmp_path):
    toml = tmp_path / "pyproject.toml"
    toml.write_text('[tool.nvda-testkit]\ncache-dir = "/p"\n', encoding="utf-8")
    settings = load_settings(toml, environ={"NVDA_TESTKIT_CACHE": "/c"})
    assert settings.cache_dir == Path("/p")
