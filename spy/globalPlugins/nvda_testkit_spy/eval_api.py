# coding: utf-8
"""Run code inside NVDA's own process: one expression, or a scenario.

The host refuses to call either unless the session opted in, so the spy does
not second-guess it: the point is to reach NVDA's live state, which means
full builtins and real imports. Both run on the main thread for the same
reason every other mutation does.

eval_in_nvda evaluates a single expression and returns its value.
exec_in_nvda runs one or more statements and returns whatever the code bound
to a name called __result__, or None if it bound nothing -- multi-statement
scenarios (e.g. "import core; core.restart()") do not compile under eval()
and previously needed an unreadable immediately-invoked-lambda workaround.

exec_in_nvda_nowait queues a scenario onto the main thread like exec_in_nvda
does, but does not wait for it to finish before returning. Use it for a
scenario that opens a real modal dialog: exec_in_nvda would block this
process's single-threaded RPC server for the dialog's whole lifetime, so a
paired simulate_modal call (see modal_api.py) could never even be
dispatched to close it.
"""

import builtins

import queueHandler
from logHandler import log

from .mainthread import run_on_main_thread
from .modal_api import remember_foreground_baseline
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
    return eval(source, {"__builtins__": builtins})


@rpc_method
def eval_in_nvda(source, timeout=30.0):
    return _marshallable(run_on_main_thread(lambda: _evaluate(source), timeout=timeout))


def _execute(source):
    scope = {"__builtins__": builtins}
    exec(compile(source, "<nvda-testkit>", "exec"), scope)
    return scope.get("__result__")


@rpc_method
def exec_in_nvda(source, timeout=30.0):
    return _marshallable(run_on_main_thread(lambda: _execute(source), timeout=timeout))


@rpc_method
def exec_in_nvda_nowait(source):
    # Compiled here, synchronously, so a SyntaxError still surfaces on this
    # call the same way exec_in_nvda's does -- only *running* the scenario
    # (which may never return, if it opens a modal dialog) gets queued.
    code = compile(source, "<nvda-testkit>", "exec")

    def _run():
        try:
            exec(code, {"__builtins__": builtins})
        except Exception:
            log.error("nvda-testkit: exec_in_nvda_nowait scenario raised", exc_info=True)

    remember_foreground_baseline()
    queueHandler.queueFunction(queueHandler.eventQueue, _run)
    return True
