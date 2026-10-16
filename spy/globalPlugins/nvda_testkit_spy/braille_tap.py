# coding: utf-8
"""Capture what NVDA writes to braille.

Raw text, not dot patterns: dots depend on the active braille table, so
asserting on them turns every test into a translation-table test. The cell
count is pinned too, so expectations do not shift with whatever display NVDA
believes is attached.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from logHandler import log

from .capped_log import CappedLog
from .registry import rpc_method

_LOCK = threading.RLock()
_WRITES = CappedLog()
_CELL_COUNT = 40
_INSTALLED = False


def _on_write_cells(**kwargs: Any) -> None:
    """NVDA calls this with keyword arguments; the text arrives as `rawText`."""
    raw_text = kwargs.get("rawText")
    _WRITES.append({"text": raw_text if raw_text is not None else "", "timestamp": time.time()})


def _filter_dimensions(dimensions: Any, **kwargs: Any) -> Any:
    from braille.display import DisplayDimensions

    with _LOCK:
        columns = _CELL_COUNT
    return DisplayDimensions(1, columns)


def install() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    try:
        import braille.extensions as extensions
    except ImportError:
        log.info(
            "nvda-testkit spy: braille extension points unavailable on this NVDA; "
            "braille capture disabled"
        )
        return

    extensions.pre_writeCells.register(_on_write_cells)
    extensions.filter_displayDimensions.register(_filter_dimensions)
    _INSTALLED = True


def uninstall() -> None:
    global _INSTALLED
    if not _INSTALLED:
        return
    import braille.extensions as extensions

    extensions.pre_writeCells.unregister(_on_write_cells)
    extensions.filter_displayDimensions.unregister(_filter_dimensions)
    _INSTALLED = False


@rpc_method
def braille_index() -> int:
    return _WRITES.index()


@rpc_method
def braille_since(index: int) -> list[dict[str, Any]]:
    return _WRITES.since(index)


@rpc_method
def braille_clear() -> bool:
    _WRITES.clear()
    return True


@rpc_method
def braille_set_cell_count(count: int) -> bool:
    global _CELL_COUNT
    with _LOCK:
        _CELL_COUNT = int(count)
    return True


@rpc_method
def braille_cell_count() -> int:
    with _LOCK:
        return _CELL_COUNT
