import threading

import logHandler
import nvda_testkit_spy
import nvda_testkit_spy.braille_tap as braille_tap_module
import nvda_testkit_spy.server as server_module
import nvda_testkit_spy.speech_tap as speech_tap_module
import pytest


@pytest.fixture
def session_env(monkeypatch, tmp_path):
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def no_session_env(monkeypatch):
    monkeypatch.delenv("NVDA_TESTKIT_TOKEN", raising=False)
    monkeypatch.delenv("NVDA_TESTKIT_OUTDIR", raising=False)


@pytest.fixture
def failing_start(monkeypatch, session_env, event_queue):
    def fake_start(self):
        raise RuntimeError("handshake write failed")

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)


@pytest.fixture
def uninstall_calls(monkeypatch):
    """Records uninstall order; speech's raises after really uninstalling."""
    calls = []
    real_speech = speech_tap_module.uninstall
    real_braille = braille_tap_module.uninstall

    def speech_uninstall():
        calls.append("speech")
        real_speech()
        raise RuntimeError("speech tap refused to uninstall")

    def braille_uninstall():
        calls.append("braille")
        real_braille()

    monkeypatch.setattr(speech_tap_module, "uninstall", speech_uninstall)
    monkeypatch.setattr(braille_tap_module, "uninstall", braille_uninstall)
    return calls


def test_the_plugin_is_inert_without_session_environment(no_session_env, event_queue):
    logHandler.log.reset_mock()

    plugin = nvda_testkit_spy.GlobalPlugin()

    assert plugin._server is None
    logHandler.log.info.assert_called_once()
    assert "idle" in logHandler.log.info.call_args[0][0]


def test_the_plugin_starts_and_terminates_a_server(session_env, event_queue):
    plugin = nvda_testkit_spy.GlobalPlugin()
    try:
        assert plugin._server is not None
        assert (session_env / "testkit-handshake.json").exists()
    finally:
        plugin.terminate()

    assert plugin._server is None
    assert not (session_env / "testkit-handshake.json").exists()


def test_terminate_is_safe_when_nothing_was_started(no_session_env, event_queue):
    plugin = nvda_testkit_spy.GlobalPlugin()

    plugin.terminate()

    assert plugin._server is None


def test_a_partial_start_failure_stops_the_partially_started_server(
    monkeypatch, session_env, event_queue
):
    stopped = []
    real_stop = server_module.SpyServer.stop

    def tracking_stop(self):
        stopped.append(self)
        real_stop(self)

    def fake_start(self):
        self._server = server_module.SimpleXMLRPCServer(
            ("127.0.0.1", 0), allow_none=True, logRequests=False
        )
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="nvda_testkit_spy", daemon=True
        )
        self._thread.start()
        raise RuntimeError("handshake write failed")

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)
    monkeypatch.setattr(server_module.SpyServer, "stop", tracking_stop)

    plugin = nvda_testkit_spy.GlobalPlugin()

    assert plugin._server is None
    assert len(stopped) == 1


@pytest.mark.parametrize("tap_module", [speech_tap_module, braille_tap_module])
def test_a_partial_start_failure_also_removes_each_tap(monkeypatch, failing_start, tap_module):
    calls = []
    real_uninstall = tap_module.uninstall

    def tracking_uninstall():
        calls.append(True)
        real_uninstall()

    monkeypatch.setattr(tap_module, "uninstall", tracking_uninstall)

    plugin = nvda_testkit_spy.GlobalPlugin()

    assert plugin._server is None
    assert calls == [True], "a failed start must uninstall every tap, not just the server"


def test_a_partial_start_failure_removes_the_other_tap_even_if_one_uninstall_raises(
    failing_start, uninstall_calls
):
    plugin = nvda_testkit_spy.GlobalPlugin()

    assert plugin._server is None
    assert uninstall_calls == ["speech", "braille"]


def test_terminate_removes_the_other_tap_even_if_one_uninstall_raises(
    monkeypatch, session_env, event_queue, uninstall_calls
):
    monkeypatch.setattr(server_module.SpyServer, "start", lambda self: 0)
    plugin = nvda_testkit_spy.GlobalPlugin()

    plugin.terminate()

    assert uninstall_calls == ["speech", "braille"]
    assert plugin._server is None


def test_best_effort_logs_the_failure_with_traceback_and_continues():
    logHandler.log.reset_mock()

    def explode():
        raise OSError("disk gone")

    nvda_testkit_spy._best_effort(explode, "teardown step failed")
    logHandler.log.exception.assert_called_once_with("teardown step failed")
