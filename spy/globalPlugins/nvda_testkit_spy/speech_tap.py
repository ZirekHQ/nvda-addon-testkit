# coding: utf-8
"""Capture what NVDA asks to speak, without displacing the synthesizer.

NVDA's own system-test spy captures speech by installing a fake synth driver.
That is unusable when the add-on under test *is* the synth, so this taps
speech.extensions instead: pre_speechQueued observes, speechCanceled marks.

pre_speechQueued and not filter_speechSequence: a Filter is expected to return
a transformed value and sits in NVDA's real speech path. Observing through it
risks changing what the user hears.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import speech

from .capped_log import CappedLog
from .mainthread import run_on_main_thread
from .registry import rpc_method
from .serialise import serialise_sequence

_LOCK = threading.RLock()
_SEQUENCES = CappedLog()
_CANCELLATIONS = 0
_INSTALLED = False


def _on_speech_queued(speechSequence: Any = None, **kwargs: Any) -> None:  # NOSONAR
    if not speechSequence:
        return
    _SEQUENCES.append(
        {
            "items": serialise_sequence(speechSequence),
            "timestamp": time.time(),
            "cancelled": False,
        }
    )


def _on_speech_canceled(**kwargs: Any) -> None:
    global _CANCELLATIONS
    with _LOCK:
        _CANCELLATIONS += 1
    _SEQUENCES.mark_last(cancelled=True)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    import speech.extensions as extensions

    extensions.pre_speechQueued.register(_on_speech_queued)
    extensions.speechCanceled.register(_on_speech_canceled)
    _INSTALLED = True


def uninstall() -> None:
    global _INSTALLED
    if not _INSTALLED:
        return
    import speech.extensions as extensions

    extensions.pre_speechQueued.unregister(_on_speech_queued)
    extensions.speechCanceled.unregister(_on_speech_canceled)
    _INSTALLED = False


@rpc_method
def speech_index() -> int:
    return _SEQUENCES.index()


@rpc_method
def speech_since(index: int) -> list[dict[str, Any]]:
    return _SEQUENCES.since(index)


@rpc_method
def speech_clear() -> bool:
    global _CANCELLATIONS
    with _LOCK:
        _SEQUENCES.clear()
        _CANCELLATIONS = 0
    return True


@rpc_method
def speech_cancel_count() -> int:
    with _LOCK:
        return _CANCELLATIONS


@rpc_method
def speech_speak(text: str) -> bool:
    run_on_main_thread(lambda: speech.speak([text]))
    return True


@rpc_method
def speech_cancel() -> bool:
    run_on_main_thread(speech.cancelSpeech)
    return True
