# coding: utf-8
"""Method registration and the token-checking dispatcher.

Runs inside NVDA's bundled Python. Standard library only.
"""

from __future__ import annotations

import hmac
import traceback
from typing import Any, Callable

METHODS: dict[str, Callable[..., Any]] = {}


def rpc_method[F: Callable[..., Any]](fn: F) -> F:
    """Register `fn` as callable over XML-RPC under its own name."""
    METHODS[fn.__name__] = fn
    return fn


class Dispatcher:
    """SimpleXMLRPCServer instance whose every method takes the token first.

    Token failures raise PermissionError, which SimpleXMLRPCServer turns into a
    Fault whose faultString starts "<class 'PermissionError'>:"; rpcclient.py
    maps that to AuthError. Handler exceptions are wrapped in a RuntimeError
    whose message starts "<TypeName>: ", and rpcclient.py reads that inner type
    to recognise a SyntaxError as ScenarioSyntaxError. Both shapes are a wire
    contract: do not change them without changing rpcclient.py.
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def _dispatch(self, method: str, params: tuple[Any, ...]) -> Any:
        handler = METHODS.get(method)
        if handler is None:
            raise LookupError("UNKNOWN: no such method %r" % (method,))
        if not params or not isinstance(params[0], str):
            raise PermissionError("AUTH: first argument must be the session token")
        if not hmac.compare_digest(params[0], self._token):
            raise PermissionError("AUTH: token rejected; is a stale NVDA still running?")
        try:
            return handler(*params[1:])
        except Exception as error:
            raise RuntimeError(
                "%s: %s\n%s" % (type(error).__name__, error, traceback.format_exc())
            ) from error
