"""The `nvda` object tests receive: sentence-like steps over an NvdaClient."""

from __future__ import annotations

import re
from typing import Any, overload

from ..client import NvdaClient, NvdaVersion
from ..namespaces.addons import AddonsNamespace
from ..namespaces.braille import BrailleNamespace
from ..namespaces.config import ConfigNamespace
from ..namespaces.keys import KeysNamespace
from ..namespaces.log import LogNamespace
from ..namespaces.speech import SpeechNamespace
from ..process import NvdaProcess
from ..rpcclient import RpcClient
from ..settings import TestkitSettings
from .hearing import Hearing
from .matching import build_matcher


class Nvda:
    def __init__(self, client: NvdaClient) -> None:
        self._client = client
        self._hearing = Hearing(client, client.settings)

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
    def process(self) -> NvdaProcess:
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

    def restart_harness(self, *, timeout: float = 60.0) -> None:
        self._client.restart_harness(timeout=timeout)

    def eval(self, source: str) -> Any:
        return self._client.eval(source)

    def exec(self, source: str) -> Any:
        return self._client.exec(source)

    def exec_nowait(self, source: str) -> None:
        self._client.exec_nowait(source)

    def simulate_modal(self, gesture: str = "enter", *, timeout: float = 10.0) -> bool:
        return self._client.simulate_modal(gesture, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _within(self, within: float | None) -> float:
        return self.settings.timeout if within is None else within

    def press(self, gesture: str, *, timeout: float = 10.0) -> None:
        self._client.keys.press(gesture, timeout=timeout)

    def type(self, text: str, *, timeout: float = 30.0) -> None:
        self._client.keys.type_text(text, timeout=timeout)

    def relaunch(self, *, timeout: float = 60.0) -> None:
        self._client.restart_harness(timeout=timeout)

    def restart_nvda(self, *, timeout: float = 60.0) -> None:
        self._client.restart_nvda(timeout=timeout)

    @overload
    def should_hear(self, text: str, *, within: float | None = None) -> None: ...

    @overload
    def should_hear(
        self, *, matching: str | re.Pattern[str], within: float | None = None
    ) -> None: ...

    def should_hear(
        self,
        text: str | None = None,
        *,
        matching: str | re.Pattern[str] | None = None,
        within: float | None = None,
    ) -> None:
        __tracebackhide__ = True
        self._hearing.should_hear(
            build_matcher(text, matching),
            within=self._within(within),
            mark=self._client.last_action,
        )

    @overload
    def should_not_hear(self, text: str, *, for_seconds: float = 1.0) -> None: ...

    @overload
    def should_not_hear(
        self, *, matching: str | re.Pattern[str], for_seconds: float = 1.0
    ) -> None: ...

    def should_not_hear(
        self,
        text: str | None = None,
        *,
        matching: str | re.Pattern[str] | None = None,
        for_seconds: float = 1.0,
    ) -> None:
        __tracebackhide__ = True
        self._hearing.should_not_hear(
            build_matcher(text, matching),
            for_seconds=for_seconds,
            mark=self._client.last_action,
        )
