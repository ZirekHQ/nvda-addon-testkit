import pytest

from nvda_testkit.dsl import Nvda
from nvda_testkit.errors import RpcError, TestkitError

SCENARIO = "pass"


def _modal_calls(nvda):
    return nvda.rpc.call("modal_calls")


def test_open_then_close_sends_the_gesture(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    nvda.close_dialog("escape")
    assert [call["gesture"] for call in _modal_calls(nvda)] == ["escape"]


def test_closing_a_dialog_that_never_appeared_says_so(fake_nvda, make_dsl):
    fake_nvda.script(simulate_modal_result=False)
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    with pytest.raises(AssertionError, match=r"No dialog took the foreground within 0\.2 seconds"):
        nvda.close_dialog("enter", within=0.2)


def test_actions_are_refused_while_a_dialog_is_open(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    for attempt in (
        lambda: nvda.press("a"),
        lambda: nvda.type("a"),
        lambda: nvda.relaunch(),
        lambda: nvda.open_dialog(SCENARIO),
    ):
        with pytest.raises(TestkitError, match=r"A dialog is open\. Call close_dialog"):
            attempt()


def test_assertions_still_work_while_a_dialog_is_open(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    nvda.client.speech.speak("confirm?")
    nvda.should_hear("confirm", within=1)


def test_the_dialog_block_closes_on_exit(make_dsl):
    nvda = make_dsl(allow_eval=True)
    with nvda.dialog(SCENARIO, close_with="escape"):
        pass
    assert [call["gesture"] for call in _modal_calls(nvda)] == ["escape"]
    nvda.press("a")


def test_finish_closes_a_leaked_dialog_and_fails_the_test(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    with pytest.raises(AssertionError, match="still open at the end"):
        nvda.finish()
    assert [call["gesture"] for call in _modal_calls(nvda)] == ["escape"]


def test_finish_relaunches_when_escape_does_not_free_the_main_thread(make_dsl, monkeypatch):
    nvda = make_dsl(allow_eval=True)
    old_pid = nvda.process.handshake.pid
    nvda.open_dialog(SCENARIO)

    def stuck(*, timeout=10.0):
        raise RpcError("main thread did not respond")

    monkeypatch.setattr(nvda.client, "wait_until_idle", stuck)
    with pytest.raises(AssertionError, match="still open at the end"):
        nvda.finish()
    assert nvda.process.handshake.pid != old_pid


def test_finish_is_quiet_when_no_dialog_was_left_open(make_dsl):
    nvda = make_dsl(allow_eval=True)
    with nvda.dialog(SCENARIO):
        pass
    nvda.finish()


def test_finish_relaunches_when_the_escape_cannot_be_delivered(make_dsl, monkeypatch):
    nvda = make_dsl(allow_eval=True)
    old_pid = nvda.process.handshake.pid
    nvda.open_dialog(SCENARIO)

    def unreachable(gesture="enter", *, timeout=10.0):
        raise RpcError("main thread did not respond")

    monkeypatch.setattr(nvda.client, "simulate_modal", unreachable)
    with pytest.raises(AssertionError, match="still open at the end"):
        nvda.finish()
    assert nvda.process.handshake.pid != old_pid
    assert not nvda._dialogs.is_open


def _install_and_leak_a_dialog(make_client, tmp_path, **settings):
    bundle = tmp_path / "demo.nvda-addon"
    bundle.write_bytes(b"")
    nvda = Nvda(make_client(allow_eval=True, **settings), bundle=lambda: bundle)
    nvda.install_addon()
    nvda.open_dialog(SCENARIO)
    return nvda


def test_a_non_assertion_error_in_one_step_does_not_skip_the_others(
    make_client, tmp_path, monkeypatch
):
    nvda = _install_and_leak_a_dialog(make_client, tmp_path, fail_on_log_errors=True)
    boom = RpcError("boom")

    def broken():
        raise boom

    monkeypatch.setattr(nvda._logs, "check_at_teardown", broken)
    with pytest.raises(AssertionError, match="RpcError: boom") as raised:
        nvda.finish()
    assert raised.value.__cause__ is boom
    assert "still open at the end" in str(raised.value)
    assert not nvda._dialogs.is_open
    nvda.should_have_addon("demo-addon", "not installed")


def test_finish_joins_the_log_and_dialog_problems(make_client, tmp_path):
    nvda = _install_and_leak_a_dialog(make_client, tmp_path, fail_on_log_errors=True)
    nvda.rpc.call("log_emit", "ERROR", "boom")
    with pytest.raises(AssertionError) as raised:
        nvda.finish()
    message = str(raised.value)
    assert "unexpected error" in message
    assert "still open at the end" in message
    assert message.index("unexpected error") < message.index("still open at the end")
    assert message.startswith("Teardown problem 1: ")
    assert "\nTeardown problem 2: " in message


def test_the_dialog_block_closes_even_when_the_body_raises(make_dsl):
    nvda = make_dsl(allow_eval=True)
    with pytest.raises(ZeroDivisionError), nvda.dialog(SCENARIO, close_with="escape"):
        raise ZeroDivisionError
    assert [call["gesture"] for call in _modal_calls(nvda)] == ["escape"]
    assert not nvda._dialogs.is_open


def test_the_dialog_block_sends_its_default_gesture(make_dsl):
    nvda = make_dsl(allow_eval=True)
    with nvda.dialog(SCENARIO):
        pass
    assert [call["gesture"] for call in _modal_calls(nvda)] == ["enter"]


@pytest.mark.parametrize(
    "attempt",
    [
        lambda nvda, bundle: nvda.restart_nvda(),
        lambda nvda, bundle: nvda.restart_harness(),
        lambda nvda, bundle: nvda.install_addon(bundle),
        lambda nvda, bundle: nvda.remove_addon("demo-addon"),
    ],
    ids=["restart_nvda", "restart_harness", "install_addon", "remove_addon"],
)
def test_every_action_is_refused_while_a_dialog_is_open(make_client, tmp_path, attempt):
    bundle = tmp_path / "demo.nvda-addon"
    bundle.write_bytes(b"")
    nvda = Nvda(make_client(allow_eval=True))
    nvda.open_dialog(SCENARIO)
    with pytest.raises(TestkitError, match=r"A dialog is open\. Call close_dialog"):
        attempt(nvda, bundle)


def test_should_have_addon_is_refused_while_a_dialog_is_open(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog(SCENARIO)
    try:
        with pytest.raises(TestkitError, match=r"A dialog is open"):
            nvda.should_have_addon("demo-addon", "enabled")
    finally:
        nvda.close_dialog("escape")
