"""Plain-text matching by default; regex only when asked for."""

from __future__ import annotations

import re
from dataclasses import dataclass

from . import messages


@dataclass(frozen=True)
class Matcher:
    pattern: re.Pattern[str]
    description: str
    hint: str

    def matches(self, text: str) -> bool:
        return self.pattern.search(text) is not None


def _plain(text: str) -> Matcher:
    pattern = re.compile(re.escape(text), re.IGNORECASE)
    return Matcher(pattern, f'"{text}"', messages.PLAIN_HINT)


def _regex(matching: str | re.Pattern[str]) -> Matcher:
    pattern = matching if isinstance(matching, re.Pattern) else re.compile(matching, re.IGNORECASE)
    return Matcher(pattern, f'text matching the pattern "{pattern.pattern}"', messages.REGEX_HINT)


def _pattern_text(matching: str | re.Pattern[str]) -> str:
    return matching.pattern if isinstance(matching, re.Pattern) else matching


def build_matcher(text: str | None, matching: str | re.Pattern[str] | None) -> Matcher:
    if text is not None and matching is None:
        if not text:
            raise ValueError("text must not be empty.")
        return _plain(text)
    if matching is not None and text is None:
        if not _pattern_text(matching):
            raise ValueError("matching must not be empty.")
        return _regex(matching)
    raise ValueError("Give exactly one of text or matching.")
