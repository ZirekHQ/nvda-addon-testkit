"""Start, watch and stop the NVDA under test.

The handshake protocol: we generate a token, hand it to NVDA in the
environment, delete any stale handshake file, then poll for a new one while
also watching for the process dying. Watching both matters -- an NVDA that
crashes on startup must fail in seconds, not at the handshake deadline.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .errors import HandshakeTimeout, NvdaStartupError
from .portable import PortableNvda

HANDSHAKE_FILENAME = "testkit-handshake.json"

_POLL_INTERVAL = 0.05


def new_token() -> str:
    return secrets.token_hex(16)


@dataclass(frozen=True)
class Handshake:
    port: int
    pid: int
    nvda_version: str
    api_version: str | None
    api_compat_to: str | None

    @classmethod
    def from_payload(cls, payload: dict) -> Handshake:
        return cls(
            port=int(payload["port"]),
            pid=int(payload["pid"]),
            nvda_version=str(payload.get("nvdaVersion", "unknown")),
            api_version=payload.get("apiVersion"),
            api_compat_to=payload.get("apiCompatTo"),
        )


def nvda_argv(
    portable: PortableNvda,
    log_file: Path,
    *,
    log_level: str = "DEBUG",
    minimal: bool = False,
    extra: Iterable[str] = (),
) -> list[str]:
    argv = [
        str(portable.exe),
        f"--log-file={log_file}",
        f"--log-level={log_level}",
        f"--config-path={portable.user_config}",
        # Leave the system screen-reader flag alone: the runner may be shared,
        # and flipping it has effects that outlive the test session.
        "--no-sr-flag",
    ]
    if minimal:
        argv.append("--minimal")
    argv.extend(extra)
    return argv


class NvdaProcess:
    """Owns one NVDA (or FakeNvda) process and its handshake."""

    def __init__(
        self,
        argv: Sequence[str],
        out_dir: Path,
        *,
        token: str | None = None,
        env: dict[str, str] | None = None,
        log_file: Path | None = None,
        quit_via: str = "exe",
        timeout_scale: float = 1.0,
    ) -> None:
        self.argv = list(argv)
        self.out_dir = Path(out_dir)
        self.token = token or new_token()
        self.log_file = Path(log_file) if log_file else None
        self.timeout_scale = timeout_scale
        self._quit_via = quit_via
        self._extra_env = dict(env or {})
        self._proc: subprocess.Popen | None = None
        self._handshake: Handshake | None = None

    @property
    def handshake_path(self) -> Path:
        return self.out_dir / HANDSHAKE_FILENAME

    @property
    def handshake(self) -> Handshake | None:
        return self._handshake

    @property
    def is_running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def _environment(self) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(self._extra_env)
        environment["NVDA_TESTKIT_TOKEN"] = self.token
        environment["NVDA_TESTKIT_OUTDIR"] = str(self.out_dir)
        return environment

    def log_tail(self, lines: int = 80) -> str:
        if self.log_file is None or not self.log_file.is_file():
            return "(no NVDA log available)"
        content = self.log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(content[-lines:])

    def start(self, timeout: float = 60) -> Handshake:
        deadline_seconds = timeout * self.timeout_scale
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.handshake_path.unlink(missing_ok=True)
        self._handshake = None

        self._proc = subprocess.Popen(self.argv, env=self._environment())

        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            exit_code = self._proc.poll()
            if exit_code is not None:
                raise NvdaStartupError(
                    f"NVDA exited with code {exit_code} before handshaking.\n"
                    f"Command: {' '.join(self.argv)}\n"
                    f"Log tail:\n{self.log_tail()}"
                )
            if self.handshake_path.is_file():
                try:
                    payload = json.loads(self.handshake_path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    time.sleep(_POLL_INTERVAL)
                    continue
                self._handshake = Handshake.from_payload(payload)
                return self._handshake
            time.sleep(_POLL_INTERVAL)

        self.kill()
        raise HandshakeTimeout(
            f"NVDA started but never announced itself within {deadline_seconds:.1f}s. "
            f"Expected {self.handshake_path}. Is the spy add-on installed and enabled?\n"
            f"Log tail:\n{self.log_tail()}"
        )

    def _request_quit(self) -> None:
        if self._quit_via == "rpc":
            if self._handshake is None:
                return
            import xmlrpc.client

            proxy = xmlrpc.client.ServerProxy(
                f"http://127.0.0.1:{self._handshake.port}", allow_none=True
            )
            with contextlib.suppress(Exception):  # any failure here just falls through to kill
                proxy.quit(self.token)
            return
        # Both branches must fall through to kill(). A --quit that itself
        # hangs is exactly the case that guarantee exists for.
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [self.argv[0], "--quit"],
                capture_output=True,
                check=False,
                timeout=30 * self.timeout_scale,
            )

    def quit(self, timeout: float = 30) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is not None:
            self._proc = None
            return

        self._request_quit()

        deadline = time.monotonic() + timeout * self.timeout_scale
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                self._proc = None
                return
            time.sleep(_POLL_INTERVAL)
        # An NVDA that will not leave is still an NVDA holding the desktop
        # session hostage for every later test. Kill it.
        self.kill()

    def kill(self) -> None:
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.kill()
            self._proc.wait(timeout=30)
        self._proc = None
        self._handshake = None

    def restart(self, timeout: float = 60) -> Handshake:
        self.quit(timeout=timeout)
        return self.start(timeout=timeout)
