from __future__ import annotations

from collections.abc import Callable

from ..actionmark import ActionMark
from ..client import NvdaClient
from ..settings import TestkitSettings
from . import messages
from .matching import Matcher
from .waiting import wait_until


class Hearing:
    def __init__(self, client: NvdaClient, settings: TestkitSettings) -> None:
        self._client = client
        self._settings = settings

    def _heard(self, mark: ActionMark) -> list[str]:
        texts = (sequence.text for sequence in self._client.speech.since(mark.index))
        return [text for text in texts if text]

    def _found(self, matcher: Matcher, mark: ActionMark) -> Callable[[], bool]:
        return lambda: any(matcher.matches(text) for text in self._heard(mark))

    def should_hear(self, matcher: Matcher, *, within: float, mark: ActionMark) -> None:
        __tracebackhide__ = True
        scale = self._settings.timeout_scale
        outcome = wait_until(self._found(matcher, mark), within=within, scale=scale)
        if not outcome.found:
            raise AssertionError(
                messages.expected_to_hear(
                    matcher.description,
                    within=within * scale,
                    elapsed=outcome.elapsed,
                    mark=mark,
                    heard=self._heard(mark),
                    verbose=self._settings.verbose,
                    hint=matcher.hint,
                )
            )

    def should_not_hear(self, matcher: Matcher, *, for_seconds: float, mark: ActionMark) -> None:
        __tracebackhide__ = True
        scale = self._settings.timeout_scale
        outcome = wait_until(self._found(matcher, mark), within=for_seconds, scale=scale)
        if outcome.found:
            offending = [text for text in self._heard(mark) if matcher.matches(text)]
            raise AssertionError(
                messages.unexpected_hearing(
                    matcher.description,
                    for_seconds=for_seconds * scale,
                    mark=mark,
                    heard=offending,
                    verbose=self._settings.verbose,
                )
            )

    def _pid(self) -> int | None:
        handshake = self._client.process.handshake
        return handshake.pid if handshake else None

    def _search_mark(self, entry: ActionMark, pid: int | None) -> ActionMark:
        if self._pid() == pid:
            return entry
        return ActionMark(0, "relaunching NVDA")

    def expecting(self, matcher: Matcher, *, within: float) -> _Expecting:
        """Search from the block's start, or from the new process's start after a relaunch."""
        entry = self._client.mark_action("starting the block")
        return _Expecting(self, matcher, within, entry, self._pid())


class _Expecting:
    """Asserts on a clean exit only; a block that raised keeps its own error."""

    def __init__(
        self, hearing: Hearing, matcher: Matcher, within: float, entry: ActionMark, pid: int | None
    ) -> None:
        self._hearing = hearing
        self._matcher = matcher
        self._within = within
        self._entry = entry
        self._pid = pid

    def __enter__(self) -> None:
        return None

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        __tracebackhide__ = True
        if exc_type is None:
            mark = self._hearing._search_mark(self._entry, self._pid)
            self._hearing.should_hear(self._matcher, within=self._within, mark=mark)
