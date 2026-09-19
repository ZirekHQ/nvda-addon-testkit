import pytest

from nvda_testkit.actionmark import ActionMark


def test_should_hear_sees_speech_caused_by_the_last_action(make_dsl):
    nvda = make_dsl()
    nvda.press("NVDA+t")
    nvda.client.speech.speak("12:00 PM")
    nvda.should_hear("12:00", within=1)


def test_speech_from_before_the_action_never_satisfies_should_hear(make_dsl):
    nvda = make_dsl()
    nvda.client.speech.speak("PM")
    nvda.press("NVDA+t")
    nvda.should_not_hear("PM", for_seconds=0.2)
    with pytest.raises(AssertionError, match="Expected to hear"):
        nvda.should_hear("PM", within=0.2)


def test_should_hear_accepts_a_regex_through_matching(make_dsl):
    nvda = make_dsl()
    nvda.press("a")
    nvda.client.speech.speak("12:00 PM")
    nvda.should_hear(matching=r"\d+:\d+", within=1)


def test_should_hear_rejects_both_or_neither_argument(make_dsl):
    nvda = make_dsl()
    with pytest.raises(ValueError, match="exactly one"):
        nvda.should_hear()
    with pytest.raises(ValueError, match="exactly one"):
        nvda.should_hear("a", matching="b")


def test_the_default_wait_comes_from_the_settings(make_dsl):
    nvda = make_dsl(timeout=0.2)
    with pytest.raises(AssertionError, match=r"within 0\.2 seconds"):
        nvda.should_hear("never")


def test_type_marks_the_action_and_sends_the_text(make_dsl):
    nvda = make_dsl()
    nvda.type("hi")
    assert nvda.client.last_action.label == 'typing "hi"'
    assert [entry["gesture"] for entry in nvda.keys.sent()] == ["h", "i"]


def test_relaunch_moves_the_mark_to_the_new_process_and_keeps_properties_live(make_dsl):
    nvda = make_dsl()
    before = nvda.speech
    nvda.client.speech.speak("old process")
    nvda.press("a")
    assert nvda.client.last_action.index == 1
    nvda.relaunch(timeout=20)
    assert nvda.client.last_action == ActionMark(0, "relaunching NVDA")
    assert nvda.speech is nvda.client.speech
    assert nvda.speech is not before


def test_the_existing_client_api_is_still_reachable(make_dsl):
    nvda = make_dsl(allow_eval=True)
    assert nvda.version.version == "2026.1.1"
    assert nvda.process.handshake.pid > 0
    assert nvda.eval("1 + 1") == 2
    nvda.wait_until_idle(timeout=5)


def test_exec_nowait_forwards_the_label(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.exec_nowait("pass", label="opening a dialog")
    assert nvda.client.last_action.label == "opening a dialog"


def test_simulate_modal_forwards_gesture_and_timeout(make_dsl):
    nvda = make_dsl()
    nvda.simulate_modal("escape", timeout=3.0)
    assert nvda.rpc.call("modal_calls") == [{"gesture": "escape", "timeout": 3.0}]


def test_namespace_properties_are_the_clients_objects(make_dsl):
    nvda = make_dsl()
    assert nvda.braille is nvda.client.braille
    assert nvda.config is nvda.client.config
    assert nvda.log is nvda.client.log
    assert nvda.addons is nvda.client.addons
    assert nvda.rpc is nvda.client.rpc
