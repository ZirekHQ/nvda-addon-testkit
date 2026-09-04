import json
import logging
from pathlib import Path

import pytest

from nvda_testkit.errors import HandshakeTimeout, NvdaStartupError
from nvda_testkit.portable import PortableNvda
from nvda_testkit.process import HANDSHAKE_FILENAME, Handshake, NvdaProcess, new_token, nvda_argv


@pytest.fixture
def process(fake_nvda):
    started = []

    def build(**kwargs):
        proc = NvdaProcess(
            fake_nvda.argv,
            fake_nvda.out_dir,
            token=fake_nvda.token,
            env=fake_nvda.env,
            quit_via="rpc",
            **kwargs,
        )
        started.append(proc)
        return proc

    yield build
    for proc in started:
        proc.kill()


def test_tokens_are_unique_and_hex():
    first, second = new_token(), new_token()
    assert first != second
    assert len(first) == 32
    int(first, 16)


def test_start_returns_a_populated_handshake(process):
    proc = process()
    handshake = proc.start(timeout=20)
    assert isinstance(handshake, Handshake)
    assert handshake.port > 0
    assert handshake.pid > 0
    assert handshake.nvda_version == "2026.1.1"
    assert handshake.api_compat_to == "2026.1.0"
    assert proc.is_running


def test_a_stale_handshake_file_is_deleted_before_starting(process, fake_nvda):
    stale = fake_nvda.out_dir / HANDSHAKE_FILENAME
    stale.write_text(json.dumps({"port": 1, "pid": 1, "nvdaVersion": "old"}))
    proc = process()
    handshake = proc.start(timeout=20)
    assert handshake.port != 1, "must not adopt a previous run's handshake"


def test_a_missing_handshake_times_out_with_a_useful_message(process, fake_nvda):
    fake_nvda.script(never_handshake=True)
    proc = process()
    with pytest.raises(HandshakeTimeout, match="never announced itself"):
        proc.start(timeout=1.5)


def test_a_process_that_dies_on_startup_fails_fast(process, fake_nvda):
    fake_nvda.script(exit_immediately=4)
    proc = process()
    with pytest.raises(NvdaStartupError, match="exited with code 4"):
        proc.start(timeout=20)


def test_dying_early_does_not_wait_out_the_whole_timeout(process, fake_nvda):
    import time

    fake_nvda.script(exit_immediately=1)
    proc = process()
    started = time.monotonic()
    with pytest.raises(NvdaStartupError):
        proc.start(timeout=30)
    assert time.monotonic() - started < 15, "must notice the exit, not poll to the deadline"


def test_quit_stops_the_process(process):
    import time

    proc = process()
    proc.start(timeout=20)
    started = time.monotonic()
    proc.quit(timeout=20)
    elapsed = time.monotonic() - started
    assert not proc.is_running
    assert elapsed < 10, f"quit took {elapsed:.1f}s, so it likely fell back to kill()"


def test_quit_falls_back_to_kill_when_ignored(process, fake_nvda):
    fake_nvda.script(ignore_quit=True)
    proc = process()
    proc.start(timeout=20)
    proc.quit(timeout=2)
    assert not proc.is_running, "an unresponsive NVDA must still be cleaned up"


def test_restart_yields_a_fresh_handshake(process):
    proc = process()
    first = proc.start(timeout=20)
    second = proc.restart(timeout=20)
    assert second.pid != first.pid
    assert proc.is_running


def test_timeout_scale_stretches_deadlines(process, fake_nvda):
    fake_nvda.script(handshake_delay=1.5)
    proc = process(timeout_scale=10.0)
    handshake = proc.start(timeout=0.5)
    assert handshake.port > 0


def test_nvda_argv_builds_the_documented_flags(tmp_path):
    portable = PortableNvda(
        root=tmp_path,
        exe=tmp_path / "nvda.exe",
        user_config=tmp_path / "userConfig",
        addons_dir=tmp_path / "userConfig" / "addons",
    )
    argv = nvda_argv(portable, tmp_path / "nvda.log")
    assert argv[0] == str(tmp_path / "nvda.exe")
    assert f"--log-file={tmp_path / 'nvda.log'}" in argv
    assert f"--log-level={logging.DEBUG}" in argv
    assert f"--config-path={tmp_path / 'userConfig'}" in argv
    assert "--no-sr-flag" in argv
    assert "--minimal" not in argv
    assert "--minimal" in nvda_argv(portable, tmp_path / "nvda.log", minimal=True)


def test_out_dir_is_resolved_so_a_chdiring_nvda_finds_it():
    """NVDA does os.chdir(appDir) on startup, so a relative out_dir strands the handshake."""
    proc = NvdaProcess(["nvda.exe"], Path("testOutput"))
    assert proc.out_dir.is_absolute()
    assert proc.out_dir == Path.cwd() / "testOutput"


def test_a_relative_out_dir_still_reaches_the_double(fake_nvda, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proc = NvdaProcess(
        fake_nvda.argv,
        Path("testOutput"),
        token=fake_nvda.token,
        quit_via="rpc",
    )
    try:
        proc.start(timeout=15)
        assert (tmp_path / "testOutput" / HANDSHAKE_FILENAME).is_file()
    finally:
        proc.kill()


def test_log_file_is_resolved_too(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    proc = NvdaProcess(["nvda.exe"], tmp_path / "out", log_file=Path("testOutput/nvda.log"))
    assert proc.log_file is not None
    assert proc.log_file.is_absolute()


def test_each_start_gets_its_own_numbered_log_file(fake_nvda, tmp_path):
    log_file = tmp_path / "out" / "nvda.log"
    proc = NvdaProcess(
        [*fake_nvda.argv, f"--log-file={log_file}"],
        fake_nvda.out_dir,
        token=fake_nvda.token,
        log_file=log_file,
        quit_via="rpc",
    )
    try:
        proc.start(timeout=20)
        first = proc.log_file
        proc.restart(timeout=20)
        second = proc.log_file
    finally:
        proc.kill()
    assert first == tmp_path / "out" / "nvda-1.log"
    assert second == tmp_path / "out" / "nvda-2.log"
    assert f"--log-file={second}" in proc.argv
    assert f"--log-file={first}" not in proc.argv


def test_a_restart_does_not_point_nvda_back_at_the_first_log(tmp_path):
    log_file = tmp_path / "nvda.log"
    proc = NvdaProcess(["nvda.exe", f"--log-file={log_file}"], tmp_path, log_file=log_file)
    proc._start_count = 1
    proc._number_log_file()
    first_argv = list(proc.argv)
    proc._start_count = 2
    proc._number_log_file()
    assert first_argv != proc.argv
    assert sum(arg.startswith("--log-file=") for arg in proc.argv) == 1
