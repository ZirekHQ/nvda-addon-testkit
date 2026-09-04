# coding: utf-8
"""Method registration and the token-checking dispatcher.

Runs inside NVDA's bundled Python. Standard library only.
"""

import hmac
import traceback

METHODS = {}


def rpc_method(fn):
    """Register `fn` as callable over XML-RPC under its own name."""
    METHODS[fn.__name__] = fn
    return fn


class Dispatcher:
    """SimpleXMLRPCServer instance whose every method takes the token first.

    Faults are raised as plain exceptions; SimpleXMLRPCServer turns them into
    Faults whose faultString is "<Type>: <message>". The host matches on the
    "AUTH:" prefix, so those two strings are a wire contract -- do not reword
    them without changing rpcclient.py.
    """

    def __init__(self, token):
        self._token = token

    def _dispatch(self, method, params):
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
