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

    def runner():
        try:
            outcome["value"] = fn()
        except BaseException as error:  # NOSONAR -- forwarded verbatim, see raise below
            outcome["error"] = error
            if timed_out.is_set():
                # The caller already gave up, so nothing will re-raise this.
                # The NVDA log is the maintainer's only artefact -- do not
                # let the real cause vanish behind a bare "timed out".
                log.exception("nvda-testkit: %r failed after its caller timed out", fn)
        finally:
            finished.set()

    queueHandler.queueFunction(queueHandler.eventQueue, runner)
    if not finished.wait(timeout):
        timed_out.set()
        raise TimeoutError(
            "Timed out after %.1fs waiting for NVDA's main thread to run %r. "
            "NVDA is wedged or busy." % (timeout, getattr(fn, "__name__", fn))
        )
    if outcome["error"] is not None:
        raise outcome["error"]
    return outcome["value"]
