"""NvdaClient -- the object every test receives as the `nvda` fixture."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .errors import TestkitError
from .namespaces.addons import AddonsNamespace
from .namespaces.braille import BrailleNamespace
from .namespaces.config import ConfigNamespace
from .namespaces.keys import KeysNamespace
from .namespaces.log import LogNamespace
from .namespaces.speech import SpeechNamespace
from .process import NvdaProcess
from .rpcclient import RpcClient
from .settings import TestkitSettings


@dataclass(frozen=True)
class NvdaVersion:
    version: str
    api_version: str | None
    api_compat_to: str | None
    channel: str = "unknown"


class NvdaClient:
    def __init__(
        self,
        process: NvdaProcess,
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
        self.addons = AddonsNamespace(rpc)
        self.speech = SpeechNamespace(rpc)
        self.braille = BrailleNamespace(rpc)
        self.keys = KeysNamespace(rpc)
        self.config = ConfigNamespace(rpc)
        self.log = LogNamespace(rpc)

    @property
    def rpc(self) -> RpcClient:
        return self._rpc

    @property
    def process(self) -> NvdaProcess:
        return self._process

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
        self._rpc.call("wait_until_idle", timeout)

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
        if failures:
            raise TestkitError("reset() failed for " + "; ".join(failures))

    def restart(self, *, timeout: float = 60.0) -> None:
        handshake = self._process.restart(timeout=timeout)
        self._rpc.close()
        self._attach(
            RpcClient.from_handshake(
                handshake,
                token=self._process.token,
                timeout_scale=self._settings.timeout_scale,
            )
        )

    def eval(self, source: str) -> Any:
        if not self._settings.allow_eval:
            raise TestkitError(
                "nvda.eval() is disabled. It runs arbitrary code inside NVDA, so it is "
                "opt-in: pass --nvda-allow-eval, or set allow-eval = true under "
                "[tool.nvda-testkit]."
            )
        return self._rpc.call("eval_in_nvda", source)

    def close(self) -> None:
        self._rpc.close()
