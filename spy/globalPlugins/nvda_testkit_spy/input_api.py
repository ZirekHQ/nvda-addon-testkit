# coding: utf-8
"""Send gestures through NVDA's own input pipeline.

inputCore.manager.emulateGesture, not SendInput or an external automation tool:
this needs no foreground window, cannot be stolen by whatever else the CI
runner is doing, and exercises exactly the path a real keypress takes.
"""

import threading
import time

from .mainthread import run_on_main_thread
from .registry import rpc_method

_LOCK = threading.RLock()
_SENT = []

_NAMED_CHARACTERS = {
    " ": "space",
    "\t": "tab",
    "\n": "enter",
}


def _emulate(gesture_name):
    import inputCore
    from keyboardHandler import KeyboardInputGesture

    try:
        gesture = KeyboardInputGesture.fromName(gesture_name)
    except Exception as error:
        raise ValueError(
            "%r is not a gesture NVDA recognises: %s" % (gesture_name, error)
        ) from error
    try:
        inputCore.manager.emulateGesture(gesture)
    except Exception as error:
        if type(error).__name__ != "NoInputGestureAction":
            raise


@rpc_method
def keys_press(gesture, timeout=10.0):
    run_on_main_thread(lambda: _emulate(gesture), timeout=timeout)
    with _LOCK:
        _SENT.append({"gesture": gesture, "timestamp": time.time()})
    return True


@rpc_method
def keys_type(text, timeout=30.0):
    for character in text:
        keys_press(_NAMED_CHARACTERS.get(character, character), timeout=timeout)
    return True


@rpc_method
def keys_sent():
    with _LOCK:
        return [dict(entry) for entry in _SENT]
