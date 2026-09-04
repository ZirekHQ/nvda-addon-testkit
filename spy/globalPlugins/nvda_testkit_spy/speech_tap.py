# coding: utf-8
"""Capture what NVDA asks to speak, without displacing the synthesizer.

NVDA's own system-test spy captures speech by installing a fake synth driver.
That is unusable when the add-on under test *is* the synth, so this taps
speech.extensions instead: pre_speechQueued observes, speechCanceled marks.

pre_speechQueued and not filter_speechSequence: a Filter is expected to return
a transformed value and sits in NVDA's real speech path. Observing through it
risks changing what the user hears.
"""

import threading
import time

from .registry import rpc_method
from .serialise import serialise_sequence

_LOCK = threading.RLock()
_SEQUENCES = []
_CANCELLATIONS = 0
_INSTALLED = False

def _on_speech_queued(speechSequence=None, **kwargs):  # NOSONAR
    if not speechSequence:
        return
    entry = {
        "items": serialise_sequence(speechSequence),
        "timestamp": time.time(),
        "cancelled": False,
    }
    with _LOCK:
        _SEQUENCES.append(entry)


def _on_speech_canceled(**kwargs):
    global _CANCELLATIONS
    with _LOCK:
        _CANCELLATIONS += 1
        if _SEQUENCES:
            _SEQUENCES[-1]["cancelled"] = True


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    import speech.extensions as extensions

    extensions.pre_speechQueued.register(_on_speech_queued)
    extensions.speechCanceled.register(_on_speech_canceled)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    import speech.extensions as extensions

    extensions.pre_speechQueued.unregister(_on_speech_queued)
    extensions.speechCanceled.unregister(_on_speech_canceled)
    _INSTALLED = False


@rpc_method
def speech_index():
    with _LOCK:
        return len(_SEQUENCES)


@rpc_method
def speech_since(index):
    with _LOCK:
        return [dict(entry) for entry in _SEQUENCES[index:]]


@rpc_method
def speech_clear():
    global _CANCELLATIONS
    with _LOCK:
        del _SEQUENCES[:]
        _CANCELLATIONS = 0
    return True


@rpc_method
def speech_cancel_count():
    with _LOCK:
        return _CANCELLATIONS


@rpc_method
def speech_speak(text):
    import speech

    from .mainthread import run_on_main_thread

    run_on_main_thread(lambda: speech.speak([text]))
    return True


@rpc_method
def speech_cancel():
    import speech

    from .mainthread import run_on_main_thread

    run_on_main_thread(speech.cancelSpeech)
    return True
