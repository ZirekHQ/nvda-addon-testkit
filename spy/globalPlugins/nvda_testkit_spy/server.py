# coding: utf-8
"""The loopback XML-RPC server, and the handful of core methods.

Binds 127.0.0.1 only, on an ephemeral port, and publishes that port through a
handshake file written with write-then-rename so the host never reads a
half-written one.

The transport is plain HTTP: both tokens travel in cleartext over loopback.
They keep out other local processes that cannot read the handshake file,
which is owner-only on POSIX; on Windows it inherits the output directory's
ACL, which the spy does not tighten. They do not stop a same-host attacker
able to capture loopback traffic, so run the spy only on a machine dedicated
to the test session.
"""

from __future__ import annotations

import contextlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Any, Optional
from xmlrpc.server import SimpleXMLRPCRequestHandler, SimpleXMLRPCServer

import addonAPIVersion
import core
import queueHandler
import versionInfo
from logHandler import log

from .mainthread import run_on_main_thread
from .registry import Dispatcher, rpc_method

HANDSHAKE_FILENAME = "testkit-handshake.json"
STOP_TIMEOUT = 5.0
PROTOCOL_VERSION = 1
TOKEN_HEADER = "X-Testkit-Token"
MAX_DISCARD_BYTES = 16 * 1024 * 1024
_DISCARD_CHUNK = 64 * 1024
DISCARD_DEADLINE = 2.0


def _handler_for(session_token: str) -> type[SimpleXMLRPCRequestHandler]:
    class TokenCheckingHandler(SimpleXMLRPCRequestHandler):
        def do_POST(self) -> None:
            supplied = self.headers.get(TOKEN_HEADER, "")
            if not hmac.compare_digest(supplied.encode("utf-8"), session_token.encode("utf-8")):
                self._discard_body()
                self.send_response(401)
                self.send_header("Content-Length", "0")
                self.end_headers()
                self.close_connection = True
                return
            super().do_POST()

        def _discard_body(self) -> None:
            """Read the unread request body, up to MAX_DISCARD_BYTES and DISCARD_DEADLINE.

            Closing a socket with unread input makes the OS send a reset,
            which can destroy the 401 before the client reads it. The server
            is single-threaded, so a client that declares more than it sends
            must not be able to hold it past the deadline.
            """
            try:
                remaining = min(int(self.headers.get("Content-Length", 0)), MAX_DISCARD_BYTES)
            except ValueError:
                return
            deadline = time.monotonic() + DISCARD_DEADLINE
            try:
                while remaining > 0:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return
                    self.connection.settimeout(left)
                    chunk = self.rfile.read1(min(remaining, _DISCARD_CHUNK))
                    if not chunk:
                        return
                    remaining -= len(chunk)
            except OSError:
                return

    return TokenCheckingHandler


def _nvda_versions() -> dict[str, str]:
    return {
        "version": versionInfo.version,
        "apiVersion": addonAPIVersion.formatForGUI(addonAPIVersion.CURRENT),
        "apiCompatTo": addonAPIVersion.formatForGUI(addonAPIVersion.BACK_COMPAT_TO),
    }


@rpc_method
def ping() -> str:
    return "pong"


@rpc_method
def echo(value: Any) -> Any:
    return value


@rpc_method
def nvda_version() -> dict[str, str]:
    return _nvda_versions()


@rpc_method
def wait_until_idle(timeout: float = 10.0) -> bool:
    """Return once NVDA's event queue has drained past this point.

    Queueing a no-op and waiting for it to run proves the queue reached here;
    checking the queue is then empty proves nothing new arrived behind it.
    """
    run_on_main_thread(lambda: None, timeout=timeout)
    return queueHandler.eventQueue.empty()


@rpc_method
def quit() -> bool:
    run_on_main_thread(core.triggerNVDAExit)
    return True


class SpyServer:
    def __init__(self, token: str, out_dir: Any, stop_timeout: float = STOP_TIMEOUT) -> None:
        self._token = token
        self._session_token = secrets.token_urlsafe(32)
        self._out_dir = out_dir
        self._stop_timeout = stop_timeout
        self._server: Optional[SimpleXMLRPCServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> int:
        self._server = SimpleXMLRPCServer(
            ("127.0.0.1", 0),
            requestHandler=_handler_for(self._session_token),
            allow_none=True,
            logRequests=False,
        )
        self._server.register_instance(Dispatcher(self._token), allow_dotted_names=False)
        port = self._server.server_address[1]

        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="nvda_testkit_spy",
            daemon=True,
        )
        self._thread.start()
        self._write_handshake(port)
        log.info("nvda-testkit spy listening on 127.0.0.1:%d" % port)
        return port

    def _handshake_path(self) -> str:
        return os.path.join(self._out_dir, HANDSHAKE_FILENAME)

    def _write_handshake(self, port: int) -> None:
        versions = _nvda_versions()
        payload = {
            "port": port,
            "pid": os.getpid(),
            "token": self._session_token,
            "protocolVersion": PROTOCOL_VERSION,
            "nvdaVersion": versions["version"],
            "apiVersion": versions["apiVersion"],
            "apiCompatTo": versions["apiCompatTo"],
        }
        if not os.path.isdir(self._out_dir):
            os.makedirs(self._out_dir)
        final = self._handshake_path()
        temporary = final + ".part"
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        os.replace(temporary, final)

    def _remove_handshake(self) -> None:
        final = self._handshake_path()
        for path in (final, final + ".part"):
            with contextlib.suppress(FileNotFoundError):
                os.remove(path)

    def _shutdown(self, server: SimpleXMLRPCServer) -> None:
        """Stop serve_forever without blocking the caller past the stop timeout.

        shutdown() waits for the serve loop to exit, and the loop can be inside
        a handler waiting on NVDA's main thread, which is the thread calling
        stop(). A helper thread bounds that wait; the socket is closed either
        way, so the stuck handler fails on its own.
        """
        stopper = threading.Thread(
            target=server.shutdown, name="nvda_testkit_spy_stop", daemon=True
        )
        stopper.start()
        stopper.join(self._stop_timeout)
        if stopper.is_alive():
            log.warning(
                "nvda-testkit spy: server loop did not stop within %.1fs" % self._stop_timeout
            )

    def stop(self) -> None:
        server, self._server = self._server, None
        self._thread = None
        if server is not None:
            self._shutdown(server)
            server.server_close()
        self._remove_handshake()
