import threading


def test_the_plugin_is_inert_without_session_environment(monkeypatch, event_queue):
    import logHandler
    import nvda_testkit_spy

    monkeypatch.delenv("NVDA_TESTKIT_TOKEN", raising=False)
    monkeypatch.delenv("NVDA_TESTKIT_OUTDIR", raising=False)
    logHandler.log.reset_mock()

    plugin = nvda_testkit_spy.GlobalPlugin()

    assert plugin._server is None
    logHandler.log.info.assert_called_once()
    assert "idle" in logHandler.log.info.call_args[0][0]


def test_the_plugin_starts_and_terminates_a_server(monkeypatch, tmp_path, event_queue):
    import nvda_testkit_spy

    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()
    try:
        assert plugin._server is not None
        assert (tmp_path / "testkit-handshake.json").exists()
    finally:
        plugin.terminate()

    assert plugin._server is None


def test_terminate_is_safe_when_nothing_was_started(monkeypatch, event_queue):
    import nvda_testkit_spy

    monkeypatch.delenv("NVDA_TESTKIT_TOKEN", raising=False)
    monkeypatch.delenv("NVDA_TESTKIT_OUTDIR", raising=False)

    plugin = nvda_testkit_spy.GlobalPlugin()
    plugin.terminate()  # must not raise


def test_a_partial_start_failure_stops_the_partially_started_server(
    monkeypatch, tmp_path, event_queue
):
    import nvda_testkit_spy
    from nvda_testkit_spy import server as server_module

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
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()  # must not propagate fake_start's exception

    assert plugin._server is None
    assert len(stopped) == 1


def test_a_partial_start_failure_also_removes_the_speech_tap(monkeypatch, tmp_path, event_queue):
    import nvda_testkit_spy
    from nvda_testkit_spy import server as server_module
    from nvda_testkit_spy import speech_tap as speech_tap_module

    calls = []
    real_uninstall = speech_tap_module.uninstall

    def tracking_uninstall():
        calls.append(True)
        real_uninstall()

    def fake_start(self):
        raise RuntimeError("handshake write failed")

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)
    monkeypatch.setattr(speech_tap_module, "uninstall", tracking_uninstall)
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()  # must not propagate fake_start's exception

    assert plugin._server is None
    assert calls == [True], "a failed start must uninstall the speech tap, not just the server"


def test_a_partial_start_failure_also_removes_the_braille_tap(monkeypatch, tmp_path, event_queue):
    import nvda_testkit_spy
    from nvda_testkit_spy import braille_tap as braille_tap_module
    from nvda_testkit_spy import server as server_module

    calls = []
    real_uninstall = braille_tap_module.uninstall

    def tracking_uninstall():
        calls.append(True)
        real_uninstall()

    def fake_start(self):
        raise RuntimeError("handshake write failed")

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)
    monkeypatch.setattr(braille_tap_module, "uninstall", tracking_uninstall)
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()  # must not propagate fake_start's exception

    assert plugin._server is None
    assert calls == [True], "a failed start must uninstall the braille tap, not just the server"


def test_a_partial_start_failure_removes_the_other_tap_even_if_one_uninstall_raises(
    monkeypatch, tmp_path, event_queue
):
    import nvda_testkit_spy
    from nvda_testkit_spy import braille_tap as braille_tap_module
    from nvda_testkit_spy import server as server_module
    from nvda_testkit_spy import speech_tap as speech_tap_module

    calls = []
    real_speech_uninstall = speech_tap_module.uninstall
    real_braille_uninstall = braille_tap_module.uninstall

    def failing_speech_uninstall():
        calls.append("speech")
        real_speech_uninstall()
        raise RuntimeError("speech tap refused to uninstall")

    def tracking_braille_uninstall():
        calls.append("braille")
        real_braille_uninstall()

    def fake_start(self):
        raise RuntimeError("handshake write failed")

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)
    monkeypatch.setattr(speech_tap_module, "uninstall", failing_speech_uninstall)
    monkeypatch.setattr(braille_tap_module, "uninstall", tracking_braille_uninstall)
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()  # must not propagate either uninstall's exception

    assert plugin._server is None
    assert calls == ["speech", "braille"], (
        "the speech tap's uninstall failing must not skip the braille tap's"
    )


def test_terminate_removes_the_other_tap_even_if_one_uninstall_raises(
    monkeypatch, tmp_path, event_queue
):
    import nvda_testkit_spy
    from nvda_testkit_spy import braille_tap as braille_tap_module
    from nvda_testkit_spy import server as server_module
    from nvda_testkit_spy import speech_tap as speech_tap_module

    calls = []
    real_speech_uninstall = speech_tap_module.uninstall
    real_braille_uninstall = braille_tap_module.uninstall

    def failing_speech_uninstall():
        calls.append("speech")
        real_speech_uninstall()
        raise RuntimeError("speech tap refused to uninstall")

    def tracking_braille_uninstall():
        calls.append("braille")
        real_braille_uninstall()

    def fake_start(self):
        pass

    monkeypatch.setattr(server_module.SpyServer, "start", fake_start)
    monkeypatch.setenv("NVDA_TESTKIT_TOKEN", "tok")
    monkeypatch.setenv("NVDA_TESTKIT_OUTDIR", str(tmp_path))

    plugin = nvda_testkit_spy.GlobalPlugin()
    monkeypatch.setattr(speech_tap_module, "uninstall", failing_speech_uninstall)
    monkeypatch.setattr(braille_tap_module, "uninstall", tracking_braille_uninstall)

    plugin.terminate()  # must not raise, and must not skip the braille tap

    assert calls == ["speech", "braille"]
