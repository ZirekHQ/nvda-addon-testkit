"""Start, watch and stop the NVDA under test.

The handshake protocol: we generate a token, hand it to NVDA in the
environment, delete any stale handshake file, then poll for a new one while
also watching for the process dying. Watching both matters -- an NVDA that
crashes on startup must fail in seconds, not at the handshake deadline.
"""

from __future__ import annotations

import contextlib
import enum
import json
import logging
import os
import secrets
import signal
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from pathlib import Path

from .errors import HandshakeTimeout, NvdaStartupError, ProtocolMismatchError
from .handshake import Handshake
from .portable import PortableNvda
from .rpcclient import RpcClient

HANDSHAKE_FILENAME = "testkit-handshake.json"

_POLL_INTERVAL = 0.05


class Ownership(enum.Enum):
    """Whether the tracked NVDA is a process we spawned or one NVDA relaunched itself."""

    SPAWNED = "spawned"
    ADOPTED = "adopted"


def new_token() -> str:
    return secrets.token_hex(16)


def nvda_argv(
    portable: PortableNvda,
    log_file: Path,
    *,
    log_level: int = logging.DEBUG,
    minimal: bool = False,
    extra: Iterable[str] = (),
) -> list[str]:
    argv = [
        str(portable.exe),
        f"--log-file={log_file}",
        f"--log-level={log_level}",
        f"--config-path={portable.user_config}",
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
        self.out_dir = Path(out_dir).resolve()
        self.token = token or new_token()
        self._log_file_base = Path(log_file).resolve() if log_file else None
        self.log_file = self._log_file_base
        self._start_count = 0
        self.timeout_scale = timeout_scale
        self._quit_via = quit_via
        self._extra_env = dict(env or {})
        self._proc: subprocess.Popen[bytes] | None = None
        self._handshake: Handshake | None = None
        self._ownership = Ownership.SPAWNED

    @property
    def handshake_path(self) -> Path:
        return self.out_dir / HANDSHAKE_FILENAME

    @property
    def handshake(self) -> Handshake | None:
        return self._handshake

    @property
    def is_running(self) -> bool:
        if self._ownership is Ownership.SPAWNED:
            return self._proc is not None and self._proc.poll() is None
        return self._handshake is not None

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

    def _hang_diagnostics(self) -> str:
        """Best-effort Windows process/AV snapshot, captured *before* kill().

        A real NVDA that never even opens its own log file points at something
        blocking before Python starts -- Defender's on-access scan of a
        freshly-extracted .exe is the leading suspect on GH runners. Never
        raises: a diagnostic that itself fails must not replace the original
        HandshakeTimeout.
        """
        if sys.platform != "win32":
            return ""
        pid = self._proc.pid if self._proc is not None else None
        sections = []
        try:
            tasklist = subprocess.run(
                ["tasklist", "/V", "/FO", "CSV"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            needles = [needle for needle in ("nvda", "werfault", f'"{pid}"') if needle]
            matches = [
                line
                for line in tasklist.stdout.splitlines()
                if any(needle in line.lower() for needle in needles)
            ]
            sections.append(
                "tasklist (nvda/WerFault/our pid):\n" + ("\n".join(matches) or "(none found)")
            )
        except Exception as error:
            sections.append(f"tasklist failed: {error}")
        try:
            defender = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-MpComputerStatus).RealTimeProtectionEnabled",
                ],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            status = defender.stdout.strip() or defender.stderr.strip() or "(unknown)"
            sections.append(f"Defender real-time protection enabled: {status}")
        except Exception as error:
            sections.append(f"Defender status check failed: {error}")
        return "\n\n".join(sections)

    def _number_log_file(self) -> None:
        """Point --log-file at a fresh numbered file: NVDA truncates it on every start."""
        if self._log_file_base is None:
            return
        base = self._log_file_base
        self.log_file = base.with_name(f"{base.stem}-{self._start_count}{base.suffix}")
        flag = f"--log-file={self.log_file}"
        self.argv = [flag if arg.startswith("--log-file=") else arg for arg in self.argv]

    def _read_handshake(self) -> Handshake | None:
        """The published handshake, or None while absent or still being written."""
        if not self.handshake_path.is_file():
            return None
        try:
            payload = json.loads(self.handshake_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return None
        return Handshake.from_payload(payload)

    def start(self, timeout: float = 60) -> Handshake:
        deadline_seconds = timeout * self.timeout_scale
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.handshake_path.unlink(missing_ok=True)
        self._handshake = None
        self._ownership = Ownership.SPAWNED
        self._start_count += 1
        self._number_log_file()

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
            try:
                candidate = self._read_handshake()
            except (KeyError, ValueError, TypeError, ProtocolMismatchError):
                self.kill()
                raise
            if candidate is not None:
                self._handshake = candidate
                return candidate
            time.sleep(_POLL_INTERVAL)

        diagnostics = self._hang_diagnostics()
        self.kill()
        raise HandshakeTimeout(
            f"NVDA started but never announced itself within {deadline_seconds:.1f}s. "
            f"Expected {self.handshake_path}. Is the spy add-on installed and enabled?\n"
            f"Log tail:\n{self.log_tail()}" + (f"\n\n{diagnostics}" if diagnostics else "")
        )

    def adopt_relaunched_handshake(self, *, exclude_pid: int, timeout: float = 60) -> Handshake:
        """Wait for NVDA's own replacement process to announce itself.

        Unlike start(), this owns no subprocess handle to watch for an early
        exit -- the process being waited for was not spawned by us, it was
        spawned by the NVDA we are about to stop tracking via self._proc.
        """
        deadline_seconds = timeout * self.timeout_scale
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            candidate = self._read_handshake()
            if candidate is not None and candidate.pid != exclude_pid:
                self._handshake = candidate
                self._ownership = Ownership.ADOPTED
                return candidate
            time.sleep(_POLL_INTERVAL)
        raise HandshakeTimeout(
            f"NVDA never announced a replacement process within {deadline_seconds:.1f}s of "
            f"restarting (still waiting on a pid other than {exclude_pid}). "
            f"Expected {self.handshake_path}."
        )

    def _kill_pid(self, pid: int) -> None:
        """Best-effort: terminate a process we did not spawn ourselves."""
        if sys.platform != "win32":
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGTERM)
            return
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                check=False,
                timeout=30,
            )

    def _request_quit(self) -> None:
        if self._quit_via == "rpc":
            if self._handshake is None:
                return
            client = RpcClient.from_handshake(self._handshake, token=self.token)
            with contextlib.suppress(Exception):
                client.call("quit")
            client.close()
            return
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [self.argv[0], "--quit"],
                capture_output=True,
                check=False,
                timeout=30 * self.timeout_scale,
            )

    def _release_adopted(self) -> None:
        """Stop the relaunched process and reap the original handle."""
        if self._handshake is not None:
            self._kill_pid(self._handshake.pid)
        self._handshake = None
        original, self._proc = self._proc, None
        if original is not None:
            if original.poll() is None:
                original.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                original.wait(timeout=30)
        self._ownership = Ownership.SPAWNED

    def quit(self, timeout: float = 30) -> None:
        if self._ownership is Ownership.ADOPTED:
            self._release_adopted()
            return
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
        self.kill()

    def kill(self) -> None:
        if self._ownership is Ownership.ADOPTED:
            self._release_adopted()
            return
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=30)
        self._proc = None
        self._handshake = None

    def restart(self, timeout: float = 60) -> Handshake:
        self.quit(timeout=timeout)
        return self.start(timeout=timeout)
