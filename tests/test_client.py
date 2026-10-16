import json
import time

import pytest

from nvda_testkit.client import NvdaClient, NvdaVersion
from nvda_testkit.errors import ConnectionLost, ScenarioSyntaxError, TestkitError
from nvda_testkit.process import NvdaProcess
from nvda_testkit.rpcclient import RpcClient
from nvda_testkit.settings import TestkitSettings


@pytest.fixture
def client(fake_nvda):
    proc = NvdaProcess(
        fake_nvda.argv, fake_nvda.out_dir, token=fake_nvda.token, env=fake_nvda.env, quit_via="rpc"
    )
    handshake = proc.start(timeout=20)
    rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
    instance = NvdaClient(proc, rpc)
    yield instance
    instance.close()
    proc.kill()


@pytest.fixture
def make_client(fake_nvda):
    created = []

    def make(*, allow_eval=False, baseline=None):
        proc = NvdaProcess(
            fake_nvda.argv,
            fake_nvda.out_dir,
            token=fake_nvda.token,
            env=fake_nvda.env,
            quit_via="rpc",
        )
        handshake = proc.start(timeout=20)
        rpc = RpcClient.from_handshake(handshake, token=fake_nvda.token)
        if baseline is not None:
            rpc.call("config_set", ["speech", "synth"], baseline)
        instance = NvdaClient(proc, rpc, settings=TestkitSettings(allow_eval=allow_eval))
        created.append(instance)
        return instance

    yield make
    for instance in created:
        instance.close()
        instance.process.kill()


@pytest.fixture
def permissive(make_client):
    return make_client(allow_eval=True)


def _relaunch_payload(handshake, pid):
    return {
        "port": handshake.port,
        "pid": pid,
        "protocolVersion": 1,
        "nvdaVersion": "2026.1.1",
        "apiVersion": "2026.1.1",
        "apiCompatTo": "2026.1.0",
    }


def test_every_namespace_is_present(client):
    for name in ("speech", "braille", "keys", "config", "log", "addons"):
        assert hasattr(client, name), f"nvda.{name} missing"


def test_the_addons_namespace_is_attached(client):
    assert hasattr(client, "addons")
    assert client.addons.state("nothing").value == "NOT_INSTALLED"


def test_version_reports_what_the_handshake_said(client):
    version = client.version
    assert isinstance(version, NvdaVersion)
    assert version.version == "2026.1.1"
    assert version.api_compat_to == "2026.1.0"


def test_wait_until_idle_returns(client):
    client.wait_until_idle(timeout=5)


def test_reset_clears_every_cache(client):
    client.speech.speak("noise")
    client.log._rpc.call("log_emit", "INFO", "noise")
    client.braille._rpc.call("braille_emit", "noise")
    assert client.speech.index() > 0

    client.reset()

    assert client.speech.index() == 0
    assert client.braille.index() == 0
    assert client.log.index() == 0


def test_reset_restores_config_to_the_baseline(client):
    client.config.set(("speech", "synth"), "changed")
    client.reset()
    assert client.config.get(("speech", "synth")) == "espeak"


def test_reset_attempts_every_step_even_if_one_fails(client, monkeypatch):
    client.speech.speak("noise")
    client.log._rpc.call("log_emit", "INFO", "noise")
    client.config.set(("speech", "synth"), "changed")

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(client.braille, "clear", _boom)

    with pytest.raises(TestkitError, match="braille"):
        client.reset()

    assert client.speech.index() == 0
    assert client.log.index() == 0
    assert client.config.get(("speech", "synth")) == "espeak"


def test_restart_harness_rebuilds_namespaces_and_preserves_the_pre_restart_baseline(make_client):
    client = make_client(baseline="custom-baseline")
    old_rpc = client.rpc
    old_pid = client.process.handshake.pid

    client.config.set(("speech", "synth"), "changed-before-restart")

    client.restart_harness(timeout=20)

    assert client.rpc is not old_rpc
    assert client.process.handshake.pid != old_pid
    assert client.speech.index() == 0

    client.reset()
    assert client.config.get(("speech", "synth")) == "custom-baseline"


def test_restart_nvda_requires_eval(client):
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.restart_nvda(timeout=5)


def test_restart_nvda_reports_a_testkiterror_when_nvda_is_not_running(permissive, monkeypatch):
    monkeypatch.setattr(permissive.process, "_handshake", None)
    with pytest.raises(TestkitError, match="nothing to restart"):
        permissive.restart_nvda(timeout=5)
    assert permissive.process.handshake_path.exists()


def test_restart_nvda_refuses_before_touching_the_handshake_file(make_client):
    client = make_client()
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.restart_nvda(timeout=5)
    assert client.process.handshake_path.exists()


def test_restart_nvda_adopts_the_replacement_handshake(relaunched_pid, permissive, monkeypatch):
    proc = permissive.process
    handshake = proc.handshake

    def fake_core_restart(source):
        assert "core" in source
        assert "restart" in source
        payload = _relaunch_payload(handshake, relaunched_pid)
        proc.handshake_path.write_text(json.dumps(payload), encoding="utf-8")
        raise ConnectionLost("connection dropped mid-response, as a real restart would")

    monkeypatch.setattr(permissive, "eval", fake_core_restart)

    permissive.restart_nvda(timeout=5)

    assert permissive.process.handshake.pid == relaunched_pid


def test_restart_nvda_does_not_swallow_a_real_error_from_the_trigger_call(permissive, monkeypatch):
    def fake_core_restart(source):
        raise ScenarioSyntaxError("a real bug in the trigger source, not a dropped connection")

    monkeypatch.setattr(permissive, "eval", fake_core_restart)
    with pytest.raises(ScenarioSyntaxError):
        permissive.restart_nvda(timeout=5)


def test_eval_is_refused_unless_explicitly_allowed(client):
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.eval("1 + 1")


def test_eval_works_when_allowed(permissive):
    assert permissive.eval("2 + 2") == 4


def test_exec_works_when_allowed(permissive):
    assert permissive.exec("x = 2\n__result__ = x * 3") == 6


def test_exec_lets_a_nested_function_see_top_level_names(permissive):
    """The fake must match the real spy's single-namespace exec() semantics
    (tests_spy/test_eval_api.py's equivalent test), or a scoping regression
    here would pass against the fake and fail against real NVDA."""
    result = permissive.exec(
        "vals = [1, 2, 3]\ndef total():\n    return sum(vals)\n__result__ = total()"
    )
    assert result == 6


def test_exec_is_refused_unless_explicitly_allowed(client):
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.exec("x = 1")


def test_exec_nowait_runs_the_scenario_when_allowed(permissive):
    assert permissive.exec_nowait("x = 1") is None


def test_exec_nowait_is_refused_unless_explicitly_allowed(client):
    with pytest.raises(TestkitError, match="--nvda-allow-eval"):
        client.exec_nowait("x = 1")


def test_exec_nowait_does_not_wait_for_a_slow_scenario(permissive):
    """The call returns immediately even though the scenario itself sleeps
    -- proof the fake defers to its background worker rather than running
    inline, which would otherwise block this single-threaded RPC server."""
    started = time.monotonic()
    permissive.exec_nowait("import time\ntime.sleep(2)")
    assert time.monotonic() - started < 1


def test_exec_nowait_records_a_runtime_error_instead_of_raising(permissive):
    permissive.exec_nowait("1 / 0")
    errors = permissive.rpc.poll_until(
        lambda: permissive.rpc.call("nowait_errors"),
        timeout=5,
        description="a recorded exec_nowait error",
    )
    assert errors == ["ZeroDivisionError: division by zero"]


def test_simulate_modal_sends_the_gesture_and_needs_no_eval_flag(client):
    """Unlike exec()/eval(), simulate_modal() runs no arbitrary code -- it
    injects one keystroke, the same trust level as keys.press() -- so it
    works on the plain `client` fixture (allow_eval left at its default)."""
    assert client.simulate_modal("yes", timeout=1) is True
    assert client._rpc.call("modal_calls") == [{"gesture": "yes", "timeout": 1}]


def test_simulate_modal_reports_a_timeout_as_false_not_an_exception(fake_nvda, make_client):
    fake_nvda.script(simulate_modal_result=False)
    assert make_client().simulate_modal("enter", timeout=1) is False


def test_a_syntax_error_in_exec_raises_scenariosyntaxerror(permissive):
    with pytest.raises(ScenarioSyntaxError):
        permissive.exec("def broken(:\n    pass")


def test_a_syntax_error_in_eval_also_raises_scenariosyntaxerror(permissive):
    with pytest.raises(ScenarioSyntaxError):
        permissive.eval("1 +")


def test_an_indentation_error_in_exec_also_raises_scenariosyntaxerror(permissive):
    """IndentationError/TabError are SyntaxError subclasses but have their own
    __name__, so the wire-detection substring check must name them too."""
    with pytest.raises(ScenarioSyntaxError):
        permissive.exec("def f():\nreturn 1")


def test_a_wrapped_handler_permissionerror_is_an_rpcerror_not_an_autherror():
    import xmlrpc.client

    from nvda_testkit.errors import AuthError, RpcError
    from nvda_testkit.rpcclient import _classify_fault

    wrapped = xmlrpc.client.Fault(1, "<class 'RuntimeError'>:PermissionError: not a token failure")
    error = _classify_fault("ping", wrapped)
    assert isinstance(error, RpcError)
    assert not isinstance(error, AuthError)


def test_a_wrapped_handler_syntaxerror_is_a_scenariosyntaxerror():
    import xmlrpc.client

    from nvda_testkit.rpcclient import _classify_fault

    wrapped = xmlrpc.client.Fault(
        1, "<class 'RuntimeError'>:SyntaxError: invalid syntax\nTraceback"
    )
    assert isinstance(_classify_fault("exec_in_nvda", wrapped), ScenarioSyntaxError)
