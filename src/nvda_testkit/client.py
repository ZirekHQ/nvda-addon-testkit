"""The NVDA RPC client behind the `nvda` fixture; reach it as `nvda.client`."""

from __future__ import annotations

import contextlib
import time
from pathlib import Path
from typing import Any, Protocol

from .actionmark import START, ActionMark
from .errors import AuthError, ConnectionLost, RpcError, TestkitError, WaitTimeout
from .handshake import Handshake
from .namespaces.addons import AddonsNamespace
from .namespaces.braille import BrailleNamespace
from .namespaces.config import ConfigNamespace
from .namespaces.keys import KeysNamespace
from .namespaces.log import LogNamespace
from .namespaces.speech import SpeechNamespace
from .rpcclient import RpcClient
from .settings import TestkitSettings
from .version import NvdaVersion

__all__ = ["NvdaClient", "NvdaVersion", "ProcessHandle"]


class ProcessHandle(Protocol):
    """What NvdaClient needs from the process that hosts NVDA."""

    @property
    def token(self) -> str: ...

    @property
    def handshake(self) -> Handshake | None: ...

    @property
    def handshake_path(self) -> Path: ...

    def restart(self, timeout: float = ...) -> Handshake: ...

    def adopt_relaunched_handshake(
        self, *, exclude_pid: int, timeout: float = ...
    ) -> Handshake: ...


_SETTLE_BUDGET = 1.0
_SETTLE_POLL = 0.05


class NvdaClient:
    def __init__(
        self,
        process: ProcessHandle,
        rpc: RpcClient,
        settings: TestkitSettings | None = None,
    ) -> None:
        self._process = process
        self._rpc = rpc
        self._settings = settings or TestkitSettings()
        self._attach(rpc)
        self._baseline_config = self.config.snapshot()

    def _attach(self, rpc: RpcClient) -> None:
        self._rpc = rpc
        self.last_action = START
        self.addons = AddonsNamespace(rpc)
        self.speech = SpeechNamespace(rpc)
        self.braille = BrailleNamespace(rpc)
        self.keys = KeysNamespace(rpc, on_action=self.mark_action)
        self.config = ConfigNamespace(rpc)
        self.log = LogNamespace(rpc)

    @property
    def rpc(self) -> RpcClient:
        return self._rpc

    @property
    def process(self) -> ProcessHandle:
        return self._process

    @property
    def settings(self) -> TestkitSettings:
        return self._settings

    @property
    def last_action_index(self) -> int:
        return self.last_action.index

    def _idle_within(self, deadline: float) -> bool:
        remaining = max(deadline - time.monotonic(), _SETTLE_POLL)
        try:
            return bool(self._rpc.call("wait_until_idle", remaining))
        except (ConnectionLost, AuthError):
            raise
        except RpcError:
            return False

    def _settle_before_marking(self) -> None:
        deadline = time.monotonic() + _SETTLE_BUDGET
        while not self._idle_within(deadline) and time.monotonic() < deadline:
            time.sleep(_SETTLE_POLL)

    def mark_action(self, label: str) -> ActionMark:
        """Record where speech from the action about to run begins.

        Waits for NVDA to go idle first so speech still in flight from the
        previous action is not attributed to this one. If NVDA still reports
        queued work after about a second, the mark is recorded anyway, so
        late speech from the previous action can be attributed to this one.
        """
        self._settle_before_marking()
        self.last_action = ActionMark(int(self._rpc.call("speech_index")), label)
        return self.last_action

    @property
    def version(self) -> NvdaVersion:
        handshake = self._process.handshake
        if handshake is None:
            raise TestkitError("NVDA is not running; no version information available.")
        return NvdaVersion(
            version=handshake.nvda_version,
            api_version=handshake.api_version,
            api_compat_to=handshake.api_compat_to,
            channel=self._settings.channel,
        )

    def wait_until_idle(self, *, timeout: float = 10.0) -> None:
        if not self._rpc.call("wait_until_idle", timeout):
            raise WaitTimeout("NVDA to go idle", timeout)

    def reset(self) -> None:
        """Return NVDA to the state a test should start from."""
        failures = []
        for label, step in (
            ("speech", self.speech.clear),
            ("braille", self.braille.clear),
            ("log", self.log.clear),
            ("config", lambda: self.config.restore(self._baseline_config)),
        ):
            try:
                step()
            except Exception as error:
                failures.append(f"{label}: {error}")
        self.last_action = START
        if failures:
            raise TestkitError("reset() failed for " + "; ".join(failures))

    def _require_eval(self, feature: str) -> None:
        if not self._settings.allow_eval:
            raise TestkitError(
                f"nvda.{feature}() is disabled. It runs arbitrary code inside NVDA, so it is "
                "opt-in: pass --nvda-allow-eval, or set allow-eval = true under "
                "[tool.nvda-testkit]."
            )

    def _reattach(self, handshake: Handshake, label: str) -> None:
        self._rpc.close()
        self._attach(
            RpcClient.from_handshake(
                handshake,
                token=self._process.token,
                timeout_scale=self._settings.timeout_scale,
            )
        )
        self.last_action = ActionMark(0, label)

    def restart_harness(self, *, timeout: float = 60.0) -> None:
        """Kill and relaunch the NVDA process. Does not exercise NVDA's own
        core.restart() -- see restart_nvda() for that."""
        try:
            handshake = self._process.restart(timeout=timeout)
        except TestkitError:
            self._rpc.close()
            raise
        self._reattach(handshake, "relaunching NVDA")

    def restart_nvda(self, *, timeout: float = 60.0) -> None:
        """Trigger NVDA's own core.restart() and wait for its replacement
        process to announce itself. Requires allow_eval, since it is built
        on eval() internally. Use this, not restart_harness(), to verify
        behavior that lives in NVDA's real self-relaunch path."""
        self._require_eval("restart_nvda")
        handshake = self._process.handshake
        if handshake is None:
            raise TestkitError("NVDA is not running; nothing to restart.")
        old_pid = handshake.pid
        self._process.handshake_path.unlink(missing_ok=True)
        with contextlib.suppress(ConnectionLost):
            self.eval("__import__('core').restart()")
        new_handshake = self._process.adopt_relaunched_handshake(
            exclude_pid=old_pid, timeout=timeout
        )
        self._reattach(new_handshake, "restarting NVDA")

    def eval(self, source: str) -> Any:
        self._require_eval("eval")
        return self._rpc.call("eval_in_nvda", source)

    def exec(self, source: str) -> Any:
        self._require_eval("exec")
        return self._rpc.call("exec_in_nvda", source)

    def exec_nowait(self, source: str, *, label: str = "queueing a scenario") -> None:
        """Queue a scenario on NVDA's main thread without waiting for it to
        finish. Use this, not exec(), for a scenario that opens a real modal
        dialog -- exec() would block this process's single-threaded RPC
        server for the dialog's whole lifetime, so a paired simulate_modal()
        call could never even be dispatched to close it. Records an action mark
        labelled `label`."""
        self._require_eval("exec_nowait")
        self.mark_action(label)
        self._rpc.call("exec_in_nvda_nowait", source)

    def simulate_modal(self, gesture: str = "enter", *, timeout: float = 10.0) -> bool:
        """Close a real modal dialog opened by a prior exec_nowait() call.

        Sends `gesture` (one of "enter", "escape", "tab", "space", "yes",
        "no") as real injected keyboard input once NVDA's process takes the
        foreground -- what a modal dialog does unconditionally on showing --
        rather than through NVDA's own input pipeline (keys.press()), which
        is dispatched the same blocked way exec()/eval() are and can't reach
        a dialog that's already up. Returns False, rather than raising, if
        no dialog took the foreground within `timeout`.
        """
        return bool(self._rpc.call("simulate_modal", gesture, timeout))

    def close(self) -> None:
        self._rpc.close()
