"""XML-RPC transport to the spy add-on.

Standard library only, on both ends: NVDA's bundled Python has xmlrpc, so the
spy add-on can be dependency-free. Every call carries the session token as its
first argument, which is what stops a stale NVDA from a previous run quietly
answering this run's questions.
"""

from __future__ import annotations

import http.client
import re
import threading
import time
import xmlrpc.client
from collections.abc import Callable
from typing import Any

from .errors import AuthError, ConnectionLost, RpcError, ScenarioSyntaxError, WaitTimeout
from .handshake import Handshake
from .wire import TOKEN_HEADER

_DEFAULT_INTERVAL = 0.05

_SOCKET_TIMEOUT = 300.0

_UNAVAILABLE = "(unavailable: NVDA unreachable)"


_REMOTE_TYPE = re.compile(r"^<class '(?:[\w.]+\.)?(\w+)'>:")

_SYNTAX_TYPES = frozenset({"SyntaxError", "IndentationError", "TabError"})
_AUTH_TYPES = frozenset({"PermissionError"})
_WRAPPED_TYPE = re.compile(r"^\s*(\w+):")
_COMPILING_METHODS = frozenset({"eval_in_nvda", "exec_in_nvda", "exec_in_nvda_nowait"})


def remote_exception_type(fault_string: str) -> str | None:
    """The exception class name the spy's XML-RPC layer prefixed to the fault."""
    match = _REMOTE_TYPE.match(fault_string)
    return match.group(1) if match else None


def _handler_exception_type(fault_string: str, remote: str | None) -> str | None:
    """The type of the exception a handler raised, read through the spy's RuntimeError wrapper."""
    if remote != "RuntimeError":
        return remote
    match = _WRAPPED_TYPE.match(fault_string.partition(":")[2])
    return match.group(1) if match else remote


def _classify_fault(method: str, fault: xmlrpc.client.Fault) -> RpcError:
    message = fault.faultString
    remote = remote_exception_type(message)
    if remote in _AUTH_TYPES:
        return AuthError(
            f"The spy rejected our token calling {method!r}. "
            "A stale NVDA from a previous run is the usual cause. "
            f"Remote said: {message}"
        )
    if method in _COMPILING_METHODS and _handler_exception_type(message, remote) in _SYNTAX_TYPES:
        return ScenarioSyntaxError(f"{method}() was given source that doesn't compile: {message}")
    return RpcError(f"{method}() failed inside NVDA: {message}")


def _classify_protocol_error(method: str, error: xmlrpc.client.ProtocolError) -> RpcError:
    if error.errcode == 401:
        return AuthError(
            f"The spy rejected our token header calling {method!r} (HTTP 401). "
            "A stale NVDA from a previous run is the usual cause."
        )
    return ConnectionLost(
        f"The spy answered {method!r} with HTTP {error.errcode} {error.errmsg} at {error.url}."
    )


def _observe(last_seen: Callable[[], Any] | None) -> Any:
    if last_seen is None:
        return None
    try:
        return last_seen()
    except RpcError:
        return _UNAVAILABLE


class _TimeoutTransport(xmlrpc.client.Transport):
    def __init__(self, timeout: float, header_token: str | None = None) -> None:
        super().__init__(use_builtin_types=True)
        self._timeout = timeout
        self._header_token = header_token

    def get_host_info(
        self, host: str | tuple[str, dict[str, str]]
    ) -> tuple[str, list[tuple[str, str]], dict[str, str]]:
        chost, extra, x509 = super().get_host_info(host)
        extra = list(extra or [])
        if self._header_token:
            extra.append((TOKEN_HEADER, self._header_token))
        return chost, extra, x509

    def make_connection(self, host: str | tuple[str, dict[str, str]]) -> http.client.HTTPConnection:
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
        header_token: str | None = None,
    ) -> None:
        self.port = port
        self.token = token
        self.timeout_scale = timeout_scale
        self._transport = _TimeoutTransport(socket_timeout * timeout_scale, header_token)
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://127.0.0.1:{port}",
            allow_none=True,
            use_builtin_types=True,
            transport=self._transport,
        )
        self._lock = threading.Lock()

    @classmethod
    def from_handshake(
        cls, handshake: Handshake, *, token: str, timeout_scale: float = 1.0
    ) -> RpcClient:
        return cls(handshake.port, token, timeout_scale=timeout_scale, header_token=handshake.token)

    def call(self, method: str, *args: Any) -> Any:
        try:
            with self._lock:
                return getattr(self._proxy, method)(self.token, *args)
        except xmlrpc.client.Fault as fault:
            raise _classify_fault(method, fault) from fault
        except xmlrpc.client.ProtocolError as error:
            raise _classify_protocol_error(method, error) from error
        except (OSError, http.client.HTTPException) as error:
            raise ConnectionLost(
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
                raise WaitTimeout(description, scaled, _observe(last_seen))
            time.sleep(interval)

    def close(self) -> None:
        self._transport.close()
