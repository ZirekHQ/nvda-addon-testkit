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
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import NoReturn

from .errors import HandshakeTimeout, NvdaStartupError
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


def _tasklist_section(pid: int | None) -> str:
    try:
        tasklist = subprocess.run(
            ["tasklist", "/V", "/FO", "CSV"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception as error:
        return f"tasklist failed: {error}"
    needles = ("nvda", "werfault", f'"{pid}"')
    matches = [
        line
        for line in tasklist.stdout.splitlines()
        if any(needle in line.lower() for needle in needles)
    ]
    return "tasklist (nvda/WerFault/our pid):\n" + ("\n".join(matches) or "(none found)")


def _exited_within(proc: subprocess.Popen[bytes], seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return True
        time.sleep(_POLL_INTERVAL)
    return False


_DEFENDER_QUERY = "(Get-MpComputerStatus).RealTimeProtectionEnabled"


def _defender_section() -> str:
    try:
        defender = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _DEFENDER_QUERY],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except Exception as error:
        return f"Defender status check failed: {error}"
    status = defender.stdout.strip() or defender.stderr.strip() or "(unknown)"
    return f"Defender real-time protection enabled: {status}"


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
        return "\n\n".join((_tasklist_section(pid), _defender_section()))

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
        try:
            return Handshake.from_payload(payload)
        except (KeyError, ValueError, TypeError) as error:
            raise NvdaStartupError(
                f"{self.handshake_path} is not a valid handshake: {error!r}"
            ) from error

    def _await_handshake(
        self,
        deadline_seconds: float,
        accept: Callable[[Handshake], bool],
        on_poll: Callable[[], None],
    ) -> Handshake | None:
        deadline = time.monotonic() + deadline_seconds
        while time.monotonic() < deadline:
            on_poll()
            candidate = self._read_handshake()
            if candidate is not None and accept(candidate):
                return candidate
            time.sleep(_POLL_INTERVAL)
        return None

    def _raise_if_exited(self) -> None:
        exit_code = self._proc.poll() if self._proc is not None else None
        if exit_code is not None:
            raise NvdaStartupError(
                f"NVDA exited with code {exit_code} before handshaking.\n"
                f"Command: {' '.join(self.argv)}\n"
                f"Log tail:\n{self.log_tail()}"
            )

    def _reset_for_start(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.handshake_path.unlink(missing_ok=True)
        self._handshake = None
        self._ownership = Ownership.SPAWNED
        self._start_count += 1
        self._number_log_file()

    def start(self, timeout: float = 60) -> Handshake:
        deadline_seconds = timeout * self.timeout_scale
        self._reset_for_start()
        self._proc = subprocess.Popen(self.argv, env=self._environment())
        try:
            handshake = self._await_handshake(
                deadline_seconds, lambda _: True, self._raise_if_exited
            )
        except NvdaStartupError:
            self.kill()
            raise
        if handshake is None:
            self._fail_handshake_timeout(deadline_seconds)
        self._handshake = handshake
        return handshake

    def _fail_handshake_timeout(self, deadline_seconds: float) -> NoReturn:
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
        candidate = self._await_handshake(
            deadline_seconds, lambda found: found.pid != exclude_pid, lambda: None
        )
        if candidate is not None:
            self._handshake = candidate
            self._ownership = Ownership.ADOPTED
            return candidate
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
            self._request_quit_via_rpc()
            return
        with contextlib.suppress(OSError, subprocess.TimeoutExpired):
            subprocess.run(
                [self.argv[0], "--quit"],
                capture_output=True,
                check=False,
                timeout=30 * self.timeout_scale,
            )

    def _request_quit_via_rpc(self) -> None:
        if self._handshake is None:
            return
        client = RpcClient.from_handshake(self._handshake, token=self.token)
        try:
            with contextlib.suppress(Exception):
                client.call("quit")
        finally:
            client.close()

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
        if _exited_within(self._proc, timeout * self.timeout_scale):
            self._proc = None
            return
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
