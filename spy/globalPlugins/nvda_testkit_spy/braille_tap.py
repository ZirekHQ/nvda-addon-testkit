# coding: utf-8
"""Capture what NVDA writes to braille.

Raw text, not dot patterns: dots depend on the active braille table, so
asserting on them turns every test into a translation-table test. The cell
count is pinned too, so expectations do not shift with whatever display NVDA
believes is attached.
"""

import threading
import time

from .registry import rpc_method

_LOCK = threading.RLock()
_WRITES = []
_CELL_COUNT = 40
_INSTALLED = False


# Parameter names match extensions.pre_writeCells' keyword call signature.
def _on_write_cells(cells=None, rawText=None, currentCellCount=None, **kwargs):  # NOSONAR
    with _LOCK:
        _WRITES.append({"text": rawText if rawText is not None else "", "timestamp": time.time()})


def _filter_dimensions(dimensions, **kwargs):
    from braille.display import DisplayDimensions

    with _LOCK:
        columns = _CELL_COUNT
    return DisplayDimensions(1, columns)


def install():
    global _INSTALLED
    if _INSTALLED:
        return
    import braille.extensions as extensions

    extensions.pre_writeCells.register(_on_write_cells)
    extensions.filter_displayDimensions.register(_filter_dimensions)
    _INSTALLED = True


def uninstall():
    global _INSTALLED
    if not _INSTALLED:
        return
    import braille.extensions as extensions

    extensions.pre_writeCells.unregister(_on_write_cells)
    extensions.filter_displayDimensions.unregister(_filter_dimensions)
    _INSTALLED = False


@rpc_method
def braille_index():
    with _LOCK:
        return len(_WRITES)


@rpc_method
def braille_since(index):
    with _LOCK:
        return [dict(entry) for entry in _WRITES[index:]]


@rpc_method
def braille_clear():
    with _LOCK:
        del _WRITES[:]
    return True


@rpc_method
def braille_set_cell_count(count):
    global _CELL_COUNT
    with _LOCK:
        _CELL_COUNT = int(count)
    return True


@rpc_method
def braille_cell_count():
    with _LOCK:
        return _CELL_COUNT
