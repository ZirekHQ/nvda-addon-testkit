import re

import pytest

from nvda_testkit.actionmark import START
from nvda_testkit.dsl.hearing import Hearing
from nvda_testkit.dsl.matching import build_matcher
from nvda_testkit.dsl.waiting import wait_until


def test_plain_text_matches_case_insensitively_as_a_substring():
    assert build_matcher("12:00 pm", None).matches("It is 12:00 PM now")


def test_plain_text_treats_regex_characters_literally():
    matcher = build_matcher("(PM)", None)
    assert matcher.matches("time (pm)")
    assert not matcher.matches("PM")


def test_regex_is_opt_in_and_case_insensitive():
    matcher = build_matcher(None, r"\d+:\d+ pm")
    assert matcher.matches("12:00 PM")
    assert "regular expression" in matcher.hint


def test_a_compiled_pattern_is_accepted():
    assert build_matcher(None, re.compile("ready")).matches("ready")


@pytest.mark.parametrize("text,matching", [(None, None), ("a", "b")])
def test_exactly_one_of_text_or_matching_is_required(text, matching):
    with pytest.raises(ValueError, match="exactly one"):
        build_matcher(text, matching)


def test_wait_until_reports_success_and_elapsed_time():
    outcome = wait_until(lambda: True, within=1, scale=1.0)
    assert outcome.found is True
    assert outcome.elapsed < 0.5


def test_wait_until_checks_once_even_with_zero_seconds():
    calls = []
    outcome = wait_until(lambda: calls.append(1) or False, within=0, scale=1.0)
    assert outcome.found is False
    assert len(calls) == 1


@pytest.fixture
def hearing(make_client):
    client = make_client()
    return client, Hearing(client, client.settings)


def test_should_hear_passes_for_speech_after_the_mark(hearing):
    client, steps = hearing
    client.keys.press("NVDA+t")
    client.speech.speak("12:00 PM")
    steps.should_hear(build_matcher("12:00", None), within=1, mark=client.last_action)


def test_should_hear_ignores_speech_from_before_the_mark(hearing):
    client, steps = hearing
    client.speech.speak("PM")
    client.keys.press("NVDA+t")
    matcher = build_matcher("PM", None)
    with pytest.raises(AssertionError, match=r'Expected to hear "PM" within 0.2 seconds'):
        steps.should_hear(matcher, within=0.2, mark=client.last_action)


def test_should_hear_failure_lists_what_was_heard(hearing):
    client, steps = hearing
    client.speech.speak("Tuesday")
    matcher = build_matcher("PM", None)
    with pytest.raises(AssertionError) as failure:
        steps.should_hear(matcher, within=0.2, mark=START)
    assert '1. "Tuesday"' in str(failure.value)


def test_should_hear_scales_the_wait_by_the_timeout_scale(make_client):
    client = make_client(timeout_scale=0.5)
    steps = Hearing(client, client.settings)
    matcher = build_matcher("PM", None)
    with pytest.raises(AssertionError, match=r"within 0.1 seconds"):
        steps.should_hear(matcher, within=0.2, mark=START)


def test_should_not_hear_passes_when_the_speech_never_comes(hearing):
    client, steps = hearing
    client.speech.speak("all fine")
    steps.should_not_hear(build_matcher("error", None), for_seconds=0.2, mark=START)


def test_should_not_hear_fails_with_the_offending_speech(hearing):
    client, steps = hearing
    client.speech.speak("an error occurred")
    matcher = build_matcher("error", None)
    with pytest.raises(AssertionError, match='Expected not to hear "error"'):
        steps.should_not_hear(matcher, for_seconds=0.2, mark=START)


def test_empty_text_is_rejected():
    with pytest.raises(ValueError, match="text must not be empty"):
        build_matcher("", None)


@pytest.mark.parametrize("matching", ["", re.compile("")])
def test_empty_matching_is_rejected(matching):
    with pytest.raises(ValueError, match="matching must not be empty"):
        build_matcher(None, matching)
