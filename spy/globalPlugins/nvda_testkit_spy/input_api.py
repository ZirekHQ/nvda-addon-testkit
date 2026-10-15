# coding: utf-8
"""Send gestures through NVDA's own input pipeline.

inputCore.manager.emulateGesture, not SendInput or an external automation tool:
this needs no foreground window, cannot be stolen by whatever else the CI
runner is doing, and exercises exactly the path a real keypress takes.
"""

from __future__ import annotations

import contextlib
import threading
import time
from typing import Any

import inputCore
from keyboardHandler import KeyboardInputGesture

from .mainthread import run_on_main_thread
from .registry import rpc_method

_LOCK = threading.RLock()
_SENT: list[dict[str, Any]] = []

_NAMED_CHARACTERS: dict[str, str] = {
    " ": "space",
    "\t": "tab",
    "\n": "enter",
}


def _emulate(gesture_name: str) -> None:
    try:
        gesture = KeyboardInputGesture.fromName(gesture_name)
    except (LookupError, ValueError) as error:
        raise ValueError(
            "%r is not a gesture NVDA recognises: %s" % (gesture_name, error)
        ) from error
    with contextlib.suppress(inputCore.NoInputGestureAction):
        inputCore.manager.emulateGesture(gesture)


@rpc_method
def keys_press(gesture: str, timeout: float = 10.0) -> bool:
    run_on_main_thread(lambda: _emulate(gesture), timeout=timeout)
    with _LOCK:
        _SENT.append({"gesture": gesture, "timestamp": time.time()})
    return True


@rpc_method
def keys_type(text: str, timeout: float = 30.0) -> bool:
    for character in text:
        keys_press(_NAMED_CHARACTERS.get(character, character), timeout=timeout)
    return True


@rpc_method
def keys_sent() -> list[dict[str, Any]]:
    with _LOCK:
        return [dict(entry) for entry in _SENT]
