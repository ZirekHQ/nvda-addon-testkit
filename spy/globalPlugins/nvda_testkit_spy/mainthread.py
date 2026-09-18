# coding: utf-8
"""Marshal work onto NVDA's main thread.

XML-RPC handlers run on the server's thread. Reading a lock-protected cache
from there is safe; calling into NVDA is not. Anything that mutates NVDA state
goes through run_on_main_thread, or you get failures that read as flakes.
"""

import threading

import queueHandler
from logHandler import log

DEFAULT_TIMEOUT = 10.0

_MISSING = object()


def run_on_main_thread(fn, timeout=DEFAULT_TIMEOUT):
    """Run `fn` on NVDA's main thread and return its value.

    Re-raises whatever `fn` raised, on the calling thread.
    """
    outcome = {"value": _MISSING, "error": None}
    finished = threading.Event()
    timed_out = threading.Event()
    started = threading.Event()

    def runner():
        started.set()
        try:
            outcome["value"] = fn()
        except BaseException as error:  # NOSONAR -- forwarded verbatim, see raise below
            outcome["error"] = error
            if timed_out.is_set():
                log.exception("nvda-testkit: %r failed after its caller timed out", fn)
        finally:
            finished.set()

    queueHandler.queueFunction(queueHandler.eventQueue, runner)
    if not finished.wait(timeout):
        timed_out.set()
        if started.is_set():
            raise TimeoutError(
                "%r started on NVDA's main thread but did not return "
                "within %.1fs. It's hung, not queued behind something else."
                % (getattr(fn, "__name__", fn), timeout)
            )
        raise TimeoutError(
            "%r never started on NVDA's main thread within %.1fs. "
            "The queue is backed up or NVDA is unresponsive to "
            "queueFunction()." % (getattr(fn, "__name__", fn), timeout)
        )
    if outcome["error"] is not None:
        raise outcome["error"]
    return outcome["value"]
