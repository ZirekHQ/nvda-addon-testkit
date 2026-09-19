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
