# coding: utf-8
"""Capture NVDA's log as structured records.

A logging.Handler rather than tailing nvda.log: the file is buffered, so
reading it races NVDA's own writes, and the artifact bundle wants structured
records regardless.
"""

import logging
import threading
import time

from .registry import rpc_method

_LOCK = threading.RLock()
_RECORDS = []
_HANDLER = None


class _CapturingHandler(logging.Handler):
    def emit(self, record):
        try:
            message = self.format(record)
        except Exception:  
            message = str(record.msg)
        with _LOCK:
            _RECORDS.append(
                {
                    "level": record.levelname,
                    "message": message,
                    "timestamp": time.time(),
                }
            )


def install():
    global _HANDLER
    if _HANDLER is not None:
        return
    from logHandler import log

    _HANDLER = _CapturingHandler()
    _HANDLER.setLevel(logging.DEBUG)
    _HANDLER.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_HANDLER)


def uninstall():
    global _HANDLER
    if _HANDLER is None:
        return
    from logHandler import log

    log.removeHandler(_HANDLER)
    _HANDLER = None


@rpc_method
def log_index():
    with _LOCK:
        return len(_RECORDS)


@rpc_method
def log_since(index):
    with _LOCK:
        return [dict(record) for record in _RECORDS[index:]]


@rpc_method
def log_clear():
    with _LOCK:
        del _RECORDS[:]
    return True
