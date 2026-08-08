"""A scriptable stand-in for a real NVDA running the spy add-on.

This exists so the host side of the kit can be built and tested on Linux. It
speaks the same handshake and the same XML-RPC dialect as the real spy, and it
can be told to misbehave in the specific ways a real NVDA does: handshake
slowly, never hand shake at all, die on startup, or ignore a quit request.

Deliberately standalone -- it imports nothing from nvda_testkit, so a bug in the
package under test cannot make the double lie.
"""

from __future__ import annotations

import builtins
import hmac
import json
import os
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path
from xmlrpc.server import SimpleXMLRPCServer

HANDSHAKE_FILENAME = "testkit-handshake.json"
ADDONS_STATE_FILENAME = "testkit-addons.json"

_SCALARS = (str, int, float, bool, type(None))


def _marshallable(value):
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, dict):
        return {str(key): _marshallable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_marshallable(item) for item in value]
    return repr(value)


class FakeSpy:
    def __init__(self, token: str, script: dict, out_dir: str | None = None) -> None:
        self._token = token
        self._script = script
        self._lock = threading.RLock()
        self._addons_file = Path(out_dir) / ADDONS_STATE_FILENAME if out_dir else None
        self._speech: list[dict] = []
        for canned in script.get("speech", []):
            self._speech.append({"items": canned, "timestamp": 0.0})
        self._braille: list[dict] = []
        self._cells = 40
        self._gestures: list[dict] = []
        self._config = {
            "speech": {"synth": "espeak", "espeak": {"rate": 50}},
            "braille": {"display": "noBraille"},
        }
        self._log: list[dict] = []
        self._addons: dict[str, dict] = {}
        self._load_addons()
        self.stop_requested = threading.Event()

    def _load_addons(self) -> None:
        """Mirror NVDA's own .pendingInstall handling: state survives a real
        process restart because it lives in a file, not in this instance."""
        if self._addons_file is not None and self._addons_file.is_file():
            self._addons = json.loads(self._addons_file.read_text(encoding="utf-8"))
        else:
            for name, state in (self._script.get("installed_addons") or {}).items():
                self._addons[name] = {"name": name, "version": "1.0.0", "state": state}
        for name in [n for n, entry in self._addons.items() if entry["state"] == "PENDING_REMOVE"]:
            del self._addons[name]
        for entry in self._addons.values():
            if entry["state"] == "PENDING_INSTALL":
                entry["state"] = "ENABLED"
        self._save_addons()

    def _save_addons(self) -> None:
        if self._addons_file is None:
            return
        self._addons_file.parent.mkdir(parents=True, exist_ok=True)
        self._addons_file.write_text(json.dumps(self._addons), encoding="utf-8")

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

    def rpc_braille_index(self):
        with self._lock:
            return len(self._braille)

    def rpc_braille_since(self, index):
        with self._lock:
            return self._braille[index:]

    def rpc_braille_clear(self):
        with self._lock:
            self._braille.clear()
        return True

    def rpc_braille_emit(self, text):
        with self._lock:
            self._braille.append({"text": text, "timestamp": time.time()})
        return len(self._braille)

    def rpc_braille_set_cell_count(self, count):
        self._cells = int(count)
        return True

    def rpc_braille_cell_count(self):
        return self._cells

    def rpc_keys_press(self, gesture, timeout=10.0):
        if "notakey" in gesture:
            raise ValueError(f"{gesture!r} is not a gesture NVDA recognises")
        with self._lock:
            self._gestures.append({"gesture": gesture, "timestamp": time.time()})
        return True

    def rpc_keys_type(self, text, timeout=30.0):
        named = {" ": "space", "\t": "tab", "\n": "enter"}
        for character in text:
            self.rpc_keys_press(named.get(character, character))
        return True

    def rpc_keys_sent(self):
        with self._lock:
            return list(self._gestures)

    def rpc_config_get(self, path):
        with self._lock:
            node = self._config
            for key in path:
                node = node[key]
            return node

    def rpc_config_set(self, path, value):
        with self._lock:
            node = self._config
            for key in path[:-1]:
                node = node.setdefault(key, {})
            node[path[-1]] = value
        return True

    def rpc_config_snapshot(self):
        import copy as _copy

        with self._lock:
            return _copy.deepcopy(self._config)

    def rpc_config_restore(self, snapshot):
        import copy as _copy

        with self._lock:
            self._config = _copy.deepcopy(snapshot)
        return True

    def rpc_log_index(self):
        with self._lock:
            return len(self._log)

    def rpc_log_since(self, index):
        with self._lock:
            return self._log[index:]

    def rpc_log_clear(self):
        with self._lock:
            self._log.clear()
        return True

    def rpc_log_emit(self, level, message):
        with self._lock:
            self._log.append({"level": level, "message": message, "timestamp": time.time()})
        return len(self._log)

    def rpc_quit(self):
        if not self._script.get("ignore_quit"):
            self.stop_requested.set()
        return True

    def rpc_eval_in_nvda(self, source, timeout=30.0):
        # Same contract as the real spy's eval_api: full builtins, and anything
        # xmlrpc cannot carry comes back as its repr. A stricter double here
        # would pass tests that the real NVDA then fails.
        return _marshallable(eval(source, {"__builtins__": builtins}, {}))

    def rpc_addons_install(self, bundle_path, timeout=120.0):
        entry = {"name": "demo-addon", "version": "1.0.0", "state": "PENDING_INSTALL"}
        with self._lock:
            self._addons[entry["name"]] = entry
            self._save_addons()
        return dict(entry)

    def rpc_addons_list(self):
        with self._lock:
            return [dict(entry) for entry in self._addons.values()]

    def rpc_addons_state(self, name):
        with self._lock:
            entry = self._addons.get(name)
        return entry["state"] if entry else "NOT_INSTALLED"

    def rpc_addons_remove(self, name, timeout=60.0):
        with self._lock:
            if name not in self._addons:
                raise LookupError(f"Add-on {name!r} is not installed")
            self._addons[name]["state"] = "PENDING_REMOVE"
            self._save_addons()
        return True


def main() -> int:
    # Real NVDA runs os.chdir(appDir) at startup (source/nvda.pyw), so the double
    # must not inherit the host's cwd either: a relative NVDA_TESTKIT_OUTDIR that
    # only works because both sides share a directory is a bug, not a pass.
    scratch = tempfile.mkdtemp(prefix="fake-nvda-cwd-")
    os.chdir(scratch)
    try:
        return _serve()
    finally:
        os.chdir(tempfile.gettempdir())
        shutil.rmtree(scratch, ignore_errors=True)


def _serve() -> int:
    token = os.environ.get("NVDA_TESTKIT_TOKEN")
    out_dir = os.environ.get("NVDA_TESTKIT_OUTDIR")
    if not token or not out_dir:
        print("NVDA_TESTKIT_TOKEN and NVDA_TESTKIT_OUTDIR are required", file=sys.stderr)
        return 2

    script = json.loads(os.environ.get("FAKE_NVDA_SCRIPT") or "{}")

    exit_code = script.get("exit_immediately")
    if exit_code is not None:
        return int(exit_code)

    spy = FakeSpy(token, script, out_dir)
    server = SimpleXMLRPCServer(("127.0.0.1", 0), allow_none=True, logRequests=False)
    server.register_instance(spy, allow_dotted_names=False)
    port = server.server_address[1]

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    if not script.get("never_handshake"):
        delay = float(script.get("handshake_delay", 0.0))
        if delay:
            time.sleep(delay)
        if script.get("bad_handshake"):
            # Missing "pid": valid JSON, but Handshake.from_payload raises
            # KeyError on it. Exercises the "malformed payload" leak path.
            payload = {"port": port}
        else:
            # The handshake file uses "nvdaVersion"; the nvda_version RPC
            # returns "version". Deliberate -- the real spy maps between
            # them the same way.
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
