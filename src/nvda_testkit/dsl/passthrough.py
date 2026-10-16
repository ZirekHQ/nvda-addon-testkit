"""The raw NvdaClient surface the `nvda` object exposes unchanged."""

from __future__ import annotations

from typing import Any

from ..client import NvdaClient, ProcessHandle
from ..namespaces.addons import AddonsNamespace
from ..namespaces.braille import BrailleNamespace
from ..namespaces.config import ConfigNamespace
from ..namespaces.keys import KeysNamespace
from ..namespaces.log import LogNamespace
from ..namespaces.speech import SpeechNamespace
from ..rpcclient import RpcClient
from ..settings import TestkitSettings
from ..version import NvdaVersion


class ClientPassThrough:
    """Forwards to the client on every access, so a relaunch shows its fresh objects."""

    def __init__(self, client: NvdaClient) -> None:
        self._client = client

    @property
    def client(self) -> NvdaClient:
        return self._client

    @property
    def settings(self) -> TestkitSettings:
        return self._client.settings

    @property
    def speech(self) -> SpeechNamespace:
        return self._client.speech

    @property
    def braille(self) -> BrailleNamespace:
        return self._client.braille

    @property
    def keys(self) -> KeysNamespace:
        return self._client.keys

    @property
    def config(self) -> ConfigNamespace:
        return self._client.config

    @property
    def log(self) -> LogNamespace:
        return self._client.log

    @property
    def addons(self) -> AddonsNamespace:
        return self._client.addons

    @property
    def process(self) -> ProcessHandle:
        return self._client.process

    @property
    def version(self) -> NvdaVersion:
        return self._client.version

    @property
    def rpc(self) -> RpcClient:
        return self._client.rpc

    def wait_until_idle(self, *, timeout: float = 10.0) -> None:
        self._client.wait_until_idle(timeout=timeout)

    def reset(self) -> None:
        self._client.reset()

    def eval(self, source: str) -> Any:
        return self._client.eval(source)

    def exec(self, source: str) -> Any:
        return self._client.exec(source)

    def exec_nowait(self, source: str, *, label: str = "queueing a scenario") -> None:
        self._client.exec_nowait(source, label=label)

    def simulate_modal(self, gesture: str = "enter", *, timeout: float = 10.0) -> bool:
        return self._client.simulate_modal(gesture, timeout=timeout)

    def close(self) -> None:
        self._client.close()
