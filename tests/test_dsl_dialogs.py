import pytest

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
