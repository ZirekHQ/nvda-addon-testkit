"""A scriptable stand-in for a real NVDA running the spy add-on.

This exists so the host side of the kit can be built and tested on Linux. It
speaks the same handshake and the same XML-RPC dialect as the real spy, and it
can be told to misbehave in the specific ways a real NVDA does: handshake
slowly, never hand shake at all, die on startup, or ignore a quit request.

Deliberately standalone -- it imports nothing from nvda_testkit, so a bug in the
package under test cannot make the double lie.
"""

from __future__ import annotations

import hmac
import json
import os
import sys
import threading
import time
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCServer

HANDSHAKE_FILENAME = "testkit-handshake.json"


class FakeSpy:
    def __init__(self, token: str, script: dict) -> None:
        self._token = token
        self._script = script
        self._lock = threading.RLock()
        self._speech: list[dict] = []
        for canned in script.get("speech", []):
            self._speech.append({"items": canned, "timestamp": 0.0})
        self.stop_requested = threading.Event()

    def _dispatch(self, method: str, params: tuple):
        # Method lookup before auth, matching the real spy's registry.Dispatcher.
        # The token guards against a stale NVDA from a previous run answering,
        # not against a local attacker, so leaking which methods exist over a
        # loopback port costs nothing. Both sides must agree -- do not reorder
        # one without the other.
        handler = getattr(self, f"rpc_{method}", None)
        if handler is None:
            raise Exception(f"UNKNOWN: no such method {method!r}")
        if not params or not isinstance(params[0], str):
            raise Exception("AUTH: first argument must be the session token")
        if not hmac.compare_digest(params[0], self._token):
            raise Exception("AUTH: token rejected; is a stale NVDA still running?")
        return handler(*params[1:])

    def rpc_ping(self):
        return "pong"

    def rpc_echo(self, value):
        return value

    def rpc_nvda_version(self):
        return {
            "version": self._script.get("nvda_version", "2026.1.1"),
            "apiVersion": self._script.get("api_version", "2026.1.1"),
            "apiCompatTo": self._script.get("api_compat_to", "2026.1.0"),
        }

    def rpc_wait_until_idle(self, timeout=10.0):
        return True

    def rpc_speech_index(self):
        with self._lock:
            return len(self._speech)

    def rpc_speech_since(self, index):
        with self._lock:
            return self._speech[index:]

    def rpc_speech_emit(self, items):
        with self._lock:
            self._speech.append({"items": items, "timestamp": time.time()})
        return len(self._speech)

    def rpc_speech_clear(self):
        with self._lock:
            self._speech.clear()
        return True

    def rpc_speech_cancel_count(self):
        return self._script.get("cancel_count", 0)

    def rpc_speech_speak(self, text):
        return self.rpc_speech_emit([{"kind": "text", "text": text}])

    def rpc_speech_cancel(self):
        return True

    def rpc_quit(self):
        if not self._script.get("ignore_quit"):
            self.stop_requested.set()
        return True


def main() -> int:
    token = os.environ.get("NVDA_TESTKIT_TOKEN")
    out_dir = os.environ.get("NVDA_TESTKIT_OUTDIR")
    if not token or not out_dir:
        print("NVDA_TESTKIT_TOKEN and NVDA_TESTKIT_OUTDIR are required", file=sys.stderr)
        return 2

    script = json.loads(os.environ.get("FAKE_NVDA_SCRIPT") or "{}")

    exit_code = script.get("exit_immediately")
    if exit_code is not None:
        return int(exit_code)

    spy = FakeSpy(token, script)
    server = SimpleXMLRPCServer(("127.0.0.1", 0), allow_none=True, logRequests=False)
    server.register_instance(spy, allow_dotted_names=False)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    if not script.get("never_handshake"):
        delay = float(script.get("handshake_delay", 0.0))
        if delay:
            time.sleep(delay)
        # The handshake file uses "nvdaVersion"; the nvda_version RPC returns
        # "version". Deliberate -- the real spy maps between them the same way.
        payload = {
            "port": port,
            "pid": os.getpid(),
            "nvdaVersion": script.get("nvda_version", "2026.1.1"),
            "apiVersion": script.get("api_version", "2026.1.1"),
            "apiCompatTo": script.get("api_compat_to", "2026.1.0"),
        }
        # Write-then-rename, so a poller never reads a half-written file.
        directory = Path(out_dir)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / (HANDSHAKE_FILENAME + ".part")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        os.replace(temporary, directory / HANDSHAKE_FILENAME)

    spy.stop_requested.wait()
    server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
