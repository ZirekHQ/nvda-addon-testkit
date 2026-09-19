import itertools
import time

import pytest

from nvda_testkit.actionmark import START, ActionMark
from nvda_testkit.errors import ConnectionLost, RpcError


def test_a_new_client_marks_the_start_of_the_test(make_client):
    client = make_client()
    assert client.last_action == START
    assert client.last_action_index == 0


def test_a_press_marks_the_speech_cursor_before_the_gesture(make_client):
    client = make_client()
    client.speech.speak("earlier")
    client.keys.press("NVDA+t")
    assert client.last_action == ActionMark(1, "pressing NVDA+t")


def test_speech_after_the_action_lies_after_the_mark(make_client):
    client = make_client()
    client.speech.speak("earlier")
    client.keys.press("NVDA+t")
    client.speech.speak("caused by the press")
    heard = [sequence.text for sequence in client.speech.since(client.last_action_index)]
    assert heard == ["caused by the press"]


def test_press_all_marks_once_before_the_first_gesture(make_client):
    client = make_client()
    client.speech.speak("earlier")
    client.keys.press_all("a", "b")
    assert client.last_action == ActionMark(1, "pressing a, b")


def test_typing_labels_the_mark_with_the_text(make_client):
    client = make_client()
    client.keys.type_text("hi")
    assert client.last_action.label == 'typing "hi"'


def test_exec_nowait_marks_with_its_label(make_client):
    client = make_client(allow_eval=True)
    client.exec_nowait("pass", label="opening a dialog")
    assert client.last_action.label == "opening a dialog"


def test_a_relaunch_resets_the_mark_to_the_new_process(make_client):
    client = make_client()
    client.speech.speak("earlier")
    client.keys.press("a")
    client.restart_harness(timeout=20)
    assert client.last_action == ActionMark(0, "relaunching NVDA")


def test_reset_returns_the_mark_to_the_start(make_client):
    client = make_client()
    client.keys.press("a")
    client.reset()
    assert client.last_action == START


def test_the_client_exposes_its_settings(make_client):
    assert make_client(timeout=3).settings.timeout == 3.0


def test_labels_read_naturally_in_messages():
    assert ActionMark(2, "pressing NVDA+t").after() == "after pressing NVDA+t"
    assert ActionMark(2, "pressing NVDA+t").since() == "since that action"
    assert START.after() == "from the start of the test"
    assert START.since() == "since the start of the test"


def _script_wait_until_idle(client, monkeypatch, answers):
    real_call = client.rpc.call
    idle_calls = []

    def call(method, *args, **kwargs):
        if method != "wait_until_idle":
            return real_call(method, *args, **kwargs)
        idle_calls.append(args)
        return next(answers)

    monkeypatch.setattr(client.rpc, "call", call)
    return idle_calls


def test_the_mark_waits_until_the_idle_check_reports_idle(make_client, monkeypatch):
    client = make_client()
    client.speech.speak("earlier")
    idle_calls = _script_wait_until_idle(client, monkeypatch, iter([False, False, True]))
    mark = client.mark_action("acting")
    assert len(idle_calls) == 3
    assert mark == ActionMark(1, "acting")


def test_the_mark_is_still_recorded_when_nvda_never_reports_idle(make_client, monkeypatch):
    client = make_client()
    idle_calls = _script_wait_until_idle(client, monkeypatch, itertools.repeat(False))
    started = time.monotonic()
    mark = client.mark_action("acting")
    assert time.monotonic() - started < 3
    assert idle_calls
    assert mark == ActionMark(0, "acting")


def test_each_idle_probe_gets_only_the_remaining_budget(make_client, monkeypatch):
    client = make_client()
    idle_calls = _script_wait_until_idle(client, monkeypatch, iter([False, True]))
    client.mark_action("acting")
    assert all(0 < timeout <= 1.0 for (timeout,) in idle_calls)
    assert len(idle_calls) == 2


def test_an_idle_probe_timeout_counts_as_not_idle_and_the_mark_is_recorded(
    make_client, monkeypatch
):
    client = make_client()
    real_call = client.rpc.call

    def call(method, *args, **kwargs):
        if method == "wait_until_idle":
            raise RpcError("wait_until_idle() failed inside NVDA: never started")
        return real_call(method, *args, **kwargs)

    monkeypatch.setattr(client.rpc, "call", call)
    started = time.monotonic()
    assert client.mark_action("acting") == ActionMark(0, "acting")
    assert time.monotonic() - started < 3


def test_a_lost_connection_is_not_swallowed_by_the_idle_probe(make_client, monkeypatch):
    client = make_client()

    def call(method, *args, **kwargs):
        raise ConnectionLost("NVDA has died")

    monkeypatch.setattr(client.rpc, "call", call)
    with pytest.raises(ConnectionLost):
        client.mark_action("acting")
