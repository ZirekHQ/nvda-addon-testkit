"""The `nvda` object tests receive: sentence-like steps over an NvdaClient."""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, overload

from ..client import NvdaClient, NvdaVersion
from ..namespaces.addons import AddonsNamespace, AddonState
from ..namespaces.braille import BrailleNamespace
from ..namespaces.config import ConfigNamespace
from ..namespaces.keys import KeysNamespace
from ..namespaces.log import LogNamespace
from ..namespaces.speech import SpeechNamespace
from ..process import NvdaProcess
from ..rpcclient import RpcClient
from ..settings import TestkitSettings
from .dialogs import Dialogs
from .hearing import Hearing
from .lifecycle import Lifecycle, no_bundle
from .logsteps import LogSteps
from .matching import build_matcher


class Nvda:
    def __init__(self, client: NvdaClient, *, bundle: Callable[[], Path] = no_bundle) -> None:
        self._client = client
        self._hearing = Hearing(client, client.settings)
        self._logs = LogSteps(client, client.settings)
        self._lifecycle = Lifecycle(client, bundle)
        self._dialogs = Dialogs(client)

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

    def exec_nowait(self, source: str, *, label: str = "queueing a scenario") -> None:
        self._client.exec_nowait(source, label=label)

    def simulate_modal(self, gesture: str = "enter", *, timeout: float = 10.0) -> bool:
        return self._client.simulate_modal(gesture, timeout=timeout)

    def close(self) -> None:
        self._client.close()

    def _within(self, within: float | None) -> float:
        return self.settings.timeout if within is None else within

    def press(self, gesture: str, *, timeout: float = 10.0) -> None:
        self._dialogs.require_none_open()
        self._client.keys.press(gesture, timeout=timeout)

    def type(self, text: str, *, timeout: float = 30.0) -> None:
        self._dialogs.require_none_open()
        self._client.keys.type_text(text, timeout=timeout)

    def relaunch(self, *, timeout: float = 60.0) -> None:
        self._dialogs.require_none_open()
        self._client.restart_harness(timeout=timeout)

    def restart_nvda(self, *, timeout: float = 60.0) -> None:
        self._dialogs.require_none_open()
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

    @overload
    def should_log(self, text: str, *, within: float | None = None) -> None: ...

    @overload
    def should_log(
        self, *, matching: str | re.Pattern[str], within: float | None = None
    ) -> None: ...

    def should_log(
        self,
        text: str | None = None,
        *,
        matching: str | re.Pattern[str] | None = None,
        within: float | None = None,
    ) -> None:
        __tracebackhide__ = True
        self._logs.should_log(build_matcher(text, matching), within=self._within(within))

    def should_have_no_errors(self, *, ignoring: Sequence[str] = ()) -> None:
        __tracebackhide__ = True
        self._logs.should_have_no_errors(ignoring)

    def install_addon(self, path: Path | None = None) -> None:
        self._dialogs.require_none_open()
        self._lifecycle.install(path)

    def remove_addon(self, name: str) -> None:
        self._dialogs.require_none_open()
        self._lifecycle.remove(name)

    def should_have_addon(self, name: str, state: str | AddonState) -> None:
        __tracebackhide__ = True
        self._lifecycle.should_have(name, state)

    def open_dialog(self, scenario: str) -> None:
        self._dialogs.open(scenario)

    def close_dialog(self, gesture: str = "enter", *, within: float = 10.0) -> None:
        __tracebackhide__ = True
        self._dialogs.close(gesture, within=within)

    def dialog(
        self, scenario: str, *, close_with: str = "enter", within: float = 10.0
    ) -> AbstractContextManager[None]:
        return self._dialogs.dialog(scenario, close_with, within)

    def finish(self) -> None:
        __tracebackhide__ = True
        problems = []
        for step in (
            self._logs.check_at_teardown,
            self._dialogs.close_leftover,
            self._lifecycle.undo_all,
        ):
            try:
                step()
            except AssertionError as error:
                problems.append(str(error))
        if problems:
            raise AssertionError("\n".join(problems))
