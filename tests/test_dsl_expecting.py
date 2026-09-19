import pytest

from nvda_testkit.errors import TestkitError


def test_speech_caused_inside_the_block_satisfies_it(make_dsl):
    nvda = make_dsl()
    with nvda.expecting_speech("ready", within=1):
        nvda.press("a")
        nvda.client.speech.speak("ready")


def test_speech_before_a_later_action_in_the_block_still_counts(make_dsl):
    nvda = make_dsl()
    with nvda.expecting_speech("ready", within=1):
        nvda.client.speech.speak("ready")
        nvda.press("a")


def test_speech_from_before_the_block_does_not_count(make_dsl):
    nvda = make_dsl()
    nvda.client.speech.speak("ready")
    with (
        pytest.raises(AssertionError, match='Expected to hear "ready"'),
        nvda.expecting_speech("ready", within=0.2),
    ):
        nvda.press("a")


def test_a_relaunch_inside_the_block_searches_the_new_process(make_dsl):
    nvda = make_dsl()
    nvda.client.speech.speak("old process noise")
    with nvda.expecting_speech("ready", within=1):
        nvda.relaunch(timeout=20)
        nvda.client.speech.speak("ready")


def test_startup_speech_before_a_later_action_after_a_relaunch_still_counts(make_dsl):
    nvda = make_dsl()
    with nvda.expecting_speech("ready", within=1):
        nvda.relaunch(timeout=20)
        nvda.client.speech.speak("ready")
        nvda.press("a")


def test_a_regex_can_be_expected(make_dsl):
    nvda = make_dsl()
    with nvda.expecting_speech(matching=r"\d+ items", within=1):
        nvda.press("a")
        nvda.client.speech.speak("3 items")


def test_an_exception_in_the_block_propagates_without_the_assertion(make_dsl):
    nvda = make_dsl()
    with (
        pytest.raises(RuntimeError, match="boom"),
        nvda.expecting_speech("ready", within=0.2),
    ):
        raise RuntimeError("boom")


def test_entering_the_block_while_a_dialog_is_open_is_refused(make_dsl):
    nvda = make_dsl(allow_eval=True)
    nvda.open_dialog("pass")
    with (
        pytest.raises(TestkitError, match="A dialog is open"),
        nvda.expecting_speech("ready", within=0.2),
    ):
        pass
    nvda.close_dialog("escape")
