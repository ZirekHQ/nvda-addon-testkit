import pytest


@pytest.fixture
def api(event_queue):
    import inputCore
    from keyboardHandler import KeyboardInputGesture
    from nvda_testkit_spy import input_api

    inputCore.manager.reset_mock()
    KeyboardInputGesture.created.clear()
    input_api._SENT.clear()
    return input_api


def test_a_press_builds_a_gesture_and_emulates_it(api):
    import inputCore
    from keyboardHandler import KeyboardInputGesture

    assert api.keys_press("NVDA+n") is True
    assert KeyboardInputGesture.created == ["NVDA+n"]
    assert inputCore.manager.emulateGesture.call_count == 1


def test_presses_are_recorded_for_the_replay_trace(api):
    api.keys_press("downArrow")
    api.keys_press("enter")
    assert [entry["gesture"] for entry in api.keys_sent()] == ["downArrow", "enter"]
    assert all(entry["timestamp"] > 0 for entry in api.keys_sent())


def test_typing_sends_one_gesture_per_character(api):
    from keyboardHandler import KeyboardInputGesture

    api.keys_type("ab c")
    assert KeyboardInputGesture.created == ["a", "b", "space", "c"]


def test_an_unknown_gesture_name_surfaces_as_a_clear_error(api, monkeypatch):
    from keyboardHandler import KeyboardInputGesture

    def explode(name):
        raise LookupError(f"no such key {name}")

    monkeypatch.setattr(
        KeyboardInputGesture, "fromName", classmethod(lambda cls, name: explode(name))
    )
    with pytest.raises(ValueError, match="not a gesture NVDA recognises"):
        api.keys_press("NVDA+notakey")


def test_a_press_runs_on_the_main_thread_not_the_server_thread(api, event_queue):
    import threading

    event_queue.auto_drain = False
    done = threading.Event()
    thread = threading.Thread(target=lambda: (api.keys_press("a"), done.set()))
    thread.start()
    thread.join(timeout=0.3)
    assert not done.is_set(), "the press must wait for NVDA's main thread"
    event_queue.drain()
    thread.join(timeout=5)
    assert done.is_set()
