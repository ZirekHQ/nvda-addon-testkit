"""XML-RPC transport to the spy add-on.

Standard library only, on both ends: NVDA's bundled Python has xmlrpc, so the
spy add-on can be dependency-free. Every call carries the session token as its
first argument, which is what stops a stale NVDA from a previous run quietly
answering this run's questions.
"""

from __future__ import annotations

import time
import xmlrpc.client
from collections.abc import Callable
from typing import Any

from .errors import AuthError, RpcError, WaitTimeout
from .process import Handshake

_DEFAULT_INTERVAL = 0.05

#: Ceiling on any single call. Must exceed the longest server-side operation
#: (addons_install allows 120s). Finite matters more than the exact value: a
#: wedged NVDA would otherwise block forever and hang CI with no diagnostic.
_SOCKET_TIMEOUT = 300.0


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float) -> None:
        super().__init__(use_builtin_types=True)
        self._timeout = timeout

    def make_connection(self, host):
        connection = super().make_connection(host)
        connection.timeout = self._timeout
        return connection


class RpcClient:
    def __init__(
        self,
        port: int,
        token: str,
        *,
        timeout_scale: float = 1.0,
        socket_timeout: float = _SOCKET_TIMEOUT,
    ) -> None:
        self.port = port
        self.token = token
        self.timeout_scale = timeout_scale
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://127.0.0.1:{port}",
            allow_none=True,
            use_builtin_types=True,
            transport=_TimeoutTransport(socket_timeout * timeout_scale),
        )

    @classmethod
    def from_handshake(
        cls, handshake: Handshake, *, token: str, timeout_scale: float = 1.0
    ) -> RpcClient:
        return cls(handshake.port, token, timeout_scale=timeout_scale)

    def call(self, method: str, *args: Any) -> Any:
        try:
            return getattr(self._proxy, method)(self.token, *args)
        except xmlrpc.client.Fault as fault:
            message = fault.faultString
            if "AUTH:" in message:
                raise AuthError(
                    f"The spy rejected our token calling {method!r}. "
                    "A stale NVDA from a previous run is the usual cause. "
                    f"Remote said: {message}"
                ) from fault
            raise RpcError(f"{method}() failed inside NVDA: {message}") from fault
        except xmlrpc.client.ProtocolError as error:
            # Not an OSError, so it would otherwise escape untranslated.
            raise RpcError(
                f"The spy answered {method!r} with HTTP {error.errcode} "
                f"{error.errmsg} at {error.url}."
            ) from error
        except OSError as error:
            raise RpcError(
                f"Could not reach the spy on 127.0.0.1:{self.port} calling {method!r}. "
                "NVDA has probably died. "
                f"Transport error: {error}"
            ) from error

    def poll_until(
        self,
        fn: Callable[[], Any],
        *,
        timeout: float,
        description: str,
        interval: float = _DEFAULT_INTERVAL,
        last_seen: Callable[[], Any] | None = None,
    ) -> Any:
        """Poll `fn` until it returns something truthy, or the deadline passes."""
        scaled = timeout * self.timeout_scale
        deadline = time.monotonic() + scaled
        while True:
            result = fn()
            if result:
                return result
            if time.monotonic() >= deadline:
                observed = None
                if last_seen is not None:
                    try:
                        observed = last_seen()
                    except RpcError:
                        observed = "(unavailable: NVDA unreachable)"
                raise WaitTimeout(description, scaled, observed)
            time.sleep(interval)

    def close(self) -> None:
        transport = getattr(self._proxy, "_ServerProxy__transport", None)
        if transport is not None:
            transport.close()
