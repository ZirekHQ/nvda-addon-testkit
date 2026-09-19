from __future__ import annotations

import re
from collections.abc import Sequence

from ..client import NvdaClient
from ..namespaces.log import LogRecord
from ..settings import TestkitSettings
from . import messages
from .matching import Matcher
from .waiting import wait_until


class LogSteps:
    def __init__(self, client: NvdaClient, settings: TestkitSettings) -> None:
        self._client = client
        self._settings = settings

    def _logged(self, matcher: Matcher) -> bool:
        return any(matcher.matches(record.message) for record in self._client.log.all())

    def should_log(self, matcher: Matcher, *, within: float) -> None:
        __tracebackhide__ = True
        scale = self._settings.timeout_scale
        outcome = wait_until(lambda: self._logged(matcher), within=within, scale=scale)
        if not outcome.found:
            raise AssertionError(
                messages.expected_log(
                    matcher.description,
                    within=within * scale,
                    elapsed=outcome.elapsed,
                    records=[repr(r) for r in self._client.log.all()],
                    verbose=self._settings.verbose,
                    hint=matcher.hint,
                )
            )

    def _patterns(self, ignoring: Sequence[str] | str) -> list[re.Pattern[str]]:
        given = (ignoring,) if isinstance(ignoring, str) else tuple(ignoring)
        return [re.compile(p, re.IGNORECASE) for p in (*self._settings.ignore_log_errors, *given)]

    def _split_errors(
        self, ignoring: Sequence[str] | str
    ) -> tuple[list[LogRecord], list[LogRecord]]:
        patterns = self._patterns(ignoring)
        unexpected: list[LogRecord] = []
        ignored: list[LogRecord] = []
        for record in self._client.log.errors():
            hit = any(p.search(record.message) for p in patterns)
            (ignored if hit else unexpected).append(record)
        return unexpected, ignored

    def should_have_no_errors(self, ignoring: Sequence[str] | str = ()) -> None:
        __tracebackhide__ = True
        unexpected, ignored = self._split_errors(ignoring)
        if unexpected:
            raise AssertionError(
                messages.no_errors_failure(
                    [repr(r) for r in unexpected],
                    [repr(r) for r in ignored],
                    verbose=self._settings.verbose,
                )
            )

    def check_at_teardown(self) -> None:
        if self._settings.fail_on_log_errors:
            self.should_have_no_errors()
