"""The `nvda` object tests receive: sentence-like steps over an NvdaClient."""

from __future__ import annotations

import functools
import re
from collections.abc import Callable, Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from pathlib import Path
from typing import Concatenate, cast, overload

from ..client import NvdaClient
from ..namespaces.addons import AddonState
from .dialogs import Dialogs
from .hearing import Hearing
from .lifecycle import Lifecycle, no_bundle
from .logsteps import LogSteps
from .matching import build_matcher
from .passthrough import ClientPassThrough
from .teardown import run_all


def _guarded[**P, R](
    method: Callable[Concatenate[Nvda, P], R],
) -> Callable[Concatenate[Nvda, P], R]:
    """Refuse to run a step while a dialog opened by this test is still open."""

    @functools.wraps(method)
    def wrapper(self: Nvda, *args: P.args, **kwargs: P.kwargs) -> R:
        __tracebackhide__ = True
        self._dialogs.require_none_open()
        return method(self, *args, **kwargs)

    return cast("Callable[Concatenate[Nvda, P], R]", wrapper)


class Nvda(ClientPassThrough):
    def __init__(self, client: NvdaClient, *, bundle: Callable[[], Path] = no_bundle) -> None:
        super().__init__(client)
        self._hearing = Hearing(client, client.settings)
        self._logs = LogSteps(client, client.settings)
        self._lifecycle = Lifecycle(client, bundle)
        self._dialogs = Dialogs(client)

    @_guarded
    def restart_harness(self, *, timeout: float = 60.0) -> None:
        self._client.restart_harness(timeout=timeout)

    def _within(self, within: float | None) -> float:
        return self.settings.timeout if within is None else within

    @_guarded
    def press(self, gesture: str, *, timeout: float = 10.0) -> None:
        self._client.keys.press(gesture, timeout=timeout)

    @_guarded
    def type(self, text: str, *, timeout: float = 30.0) -> None:
        self._client.keys.type_text(text, timeout=timeout)

    def relaunch(self, *, timeout: float = 60.0) -> None:
        self.restart_harness(timeout=timeout)

    @_guarded
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

    @contextmanager
    def expecting_speech(
        self,
        text: str | None = None,
        *,
        matching: str | re.Pattern[str] | None = None,
        within: float | None = None,
    ) -> Iterator[None]:
        __tracebackhide__ = True
        self._dialogs.require_none_open()
        matcher = build_matcher(text, matching)
        with self._hearing.expecting(matcher, within=self._within(within)):
            yield

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

    def should_have_no_errors(self, *, ignoring: Sequence[str] | str = ()) -> None:
        __tracebackhide__ = True
        self._logs.should_have_no_errors(ignoring)

    @_guarded
    def install_addon(self, path: Path | None = None) -> None:
        self._lifecycle.install(path)

    @_guarded
    def remove_addon(self, name: str) -> None:
        self._lifecycle.remove(name)

    @_guarded
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
        run_all(
            (
                self._logs.check_at_teardown,
                self._dialogs.close_leftover,
                self._lifecycle.undo_all,
            )
        )
