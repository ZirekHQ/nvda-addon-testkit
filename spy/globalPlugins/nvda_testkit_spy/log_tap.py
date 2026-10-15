# coding: utf-8
"""Capture NVDA's log as structured records.

A logging.Handler rather than tailing nvda.log: the file is buffered, so
reading it races NVDA's own writes, and the artifact bundle wants structured
records regardless.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from logHandler import log

from .capped_log import CappedLog
from .registry import rpc_method

_RECORDS = CappedLog()
_HANDLER: logging.Handler | None = None


def _message_of(handler: logging.Handler, record: logging.LogRecord) -> str:
    try:
        return handler.format(record)
    except Exception:
        try:
            return str(record.msg)
        except Exception:
            return "<unformattable log message>"


class _CapturingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        message = _message_of(self, record)
        _RECORDS.append(
            {
                "level": record.levelname,
                "message": message,
                "timestamp": time.time(),
            }
        )


def install() -> None:
    global _HANDLER
    if _HANDLER is not None:
        return
    _HANDLER = _CapturingHandler()
    _HANDLER.setLevel(logging.DEBUG)
    _HANDLER.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(_HANDLER)


def uninstall() -> None:
    global _HANDLER
    if _HANDLER is None:
        return
    log.removeHandler(_HANDLER)
    _HANDLER = None


@rpc_method
def log_index() -> int:
    return _RECORDS.index()


@rpc_method
def log_since(index: int) -> list[dict[str, Any]]:
    return _RECORDS.since(index)


@rpc_method
def log_clear() -> bool:
    _RECORDS.clear()
    return True
