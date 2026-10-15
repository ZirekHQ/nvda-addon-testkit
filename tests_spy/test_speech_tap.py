import pytest
import speech
import speech.extensions as extensions
from nvda_testkit_spy import speech_tap
from nvda_testkit_spy.capped_log import DEFAULT_CAPACITY


@pytest.fixture
def tap(tmp_path):
    speech_tap.install()
    speech_tap.speech_clear()
    yield speech_tap
    speech_tap.uninstall()


def _emit(text_or_items):
    extensions.pre_speechQueued.notify(speechSequence=text_or_items)


def test_a_queued_sequence_is_captured(tap):
    assert tap.speech_index() == 0
    _emit(["hello"])
    assert tap.speech_index() == 1
    (captured,) = tap.speech_since(0)
    assert captured["items"][0]["text"] == "hello"
    assert captured["cancelled"] is False
    assert captured["timestamp"] > 0


def test_since_returns_only_what_came_after_the_index(tap):
    _emit(["first"])
    boundary = tap.speech_index()
    _emit(["second"])
    _emit(["third"])
    after = tap.speech_since(boundary)
    assert [seq["items"][0]["text"] for seq in after] == ["second", "third"]


def test_clear_resets_the_index(tap):
    _emit(["something"])
    tap.speech_clear()
    assert tap.speech_index() == 0
    assert tap.speech_since(0) == []


def test_cancellation_marks_the_latest_sequence_and_bumps_the_counter(tap):
    _emit(["being spoken"])
    assert tap.speech_cancel_count() == 0
    extensions.speechCanceled.notify()
    assert tap.speech_cancel_count() == 1
    (captured,) = tap.speech_since(0)
    assert captured["cancelled"] is True


def test_cancellation_with_nothing_in_flight_is_harmless(tap):
    extensions.speechCanceled.notify()
    assert tap.speech_cancel_count() == 1
    assert tap.speech_since(0) == []


def test_uninstall_unregisters_so_a_second_install_does_not_double_capture(tap):
    tap.uninstall()
    tap.install()
    tap.speech_clear()
    _emit(["once"])
    assert tap.speech_index() == 1, "a re-install must not leave two handlers attached"


def test_speak_hands_the_text_to_nvda(tap, event_queue):
    speech.speak.reset_mock()

    assert tap.speech_speak("hello") is True

    speech.speak.assert_called_once_with(["hello"])


def test_cancel_asks_nvda_to_cancel_speech(tap, event_queue):
    speech.cancelSpeech.reset_mock()

    assert tap.speech_cancel() is True

    speech.cancelSpeech.assert_called_once_with()


def test_the_buffer_is_capped_so_a_long_session_cannot_grow_without_bound(tap):
    limit = DEFAULT_CAPACITY
    for number in range(limit + 5):
        _emit([str(number)])

    captured = tap.speech_since(0)

    assert len(captured) == limit
    assert tap.speech_index() == limit + 5
