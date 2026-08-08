# coding: utf-8
"""Evaluate an expression inside NVDA's own process.

The host refuses to call this unless the session opted in, so the spy does not
second-guess it: the point is to reach NVDA's live state, which means full
builtins and real imports. It runs on the main thread for the same reason every
other mutation does.
"""

import builtins

from .mainthread import run_on_main_thread
from .registry import rpc_method

_SCALARS = (str, int, float, bool, type(None))


def _marshallable(value):
    """xmlrpc carries scalars and containers of scalars; everything else is a repr."""
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, dict):
        return {str(key): _marshallable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_marshallable(item) for item in value]
    return repr(value)


def _evaluate(source):
    return eval(source, {"__builtins__": builtins}, {})


@rpc_method
def eval_in_nvda(source, timeout=30.0):
    return _marshallable(run_on_main_thread(lambda: _evaluate(source), timeout=timeout))
