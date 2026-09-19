"""Failure text for the DSL: plain, linear, numbered; long lists are truncated unless verbose."""

from __future__ import annotations

from collections.abc import Sequence

from ..actionmark import ActionMark

MAX_SHOWN = 10
PLAIN_HINT = "Nothing matched. Matching is case-insensitive plain text; use matching= for a regex."
REGEX_HINT = "Nothing matched. The pattern is a regular expression, searched case-insensitively."


def seconds(value: float) -> str:
    return "1 second" if value == 1 else f"{value:g} seconds"


def _count(number: int, noun: str) -> str:
    return f"{number} {noun}" if number == 1 else f"{number} {noun}s"


def _numbered(lines: Sequence[str], verbose: bool, limit: int = MAX_SHOWN) -> list[str]:
    shown = list(lines) if verbose else list(lines[:limit])
    collapsed = [" ".join(line.split()) for line in shown]
    out = [f"{number}. {line}" for number, line in enumerate(collapsed, start=1)]
    hidden = len(lines) - len(shown)
    if hidden:
        noun = "item" if hidden == 1 else "items"
        out.append(f"{hidden} more {noun} not shown; run with --nvda-verbose to see all")
    return out


def _quoted(texts: Sequence[str]) -> list[str]:
    return [f'"{text}"' for text in texts]


def _heard_block(heard: Sequence[str], mark: ActionMark, verbose: bool) -> list[str]:
    if not heard:
        return [f"Heard nothing {mark.since()}."]
    header = f"Heard {mark.since()}, {_count(len(heard), 'item')}:"
    return [header, *_numbered(_quoted(heard), verbose)]


def expected_to_hear(
    description: str,
    *,
    within: float,
    elapsed: float,
    mark: ActionMark,
    heard: Sequence[str],
    verbose: bool,
    hint: str,
) -> str:
    lines = [
        f"Expected to hear {description} within {seconds(within)} {mark.after()}.",
        f"Time elapsed: {elapsed:.2f} seconds.",
        *_heard_block(heard, mark, verbose),
    ]
    return "\n".join([*lines, hint] if heard else lines)


def unexpected_hearing(
    description: str,
    *,
    for_seconds: float,
    mark: ActionMark,
    heard: Sequence[str],
    verbose: bool,
) -> str:
    span = f"for {seconds(for_seconds)} {mark.after()}"
    head = f"Expected not to hear {description} {span}, but heard:"
    return "\n".join([head, *_numbered(_quoted(heard), verbose)])


def expected_log(
    description: str,
    *,
    within: float,
    elapsed: float,
    records: Sequence[str],
    verbose: bool,
    hint: str,
) -> str:
    body = (
        [f"Logged so far, {_count(len(records), 'item')}:", *_numbered(records, verbose)]
        if records
        else ["Nothing was logged."]
    )
    head = [
        f"Expected NVDA to log {description} within {seconds(within)}.",
        f"Time elapsed: {elapsed:.2f} seconds.",
    ]
    return "\n".join([*head, *body, hint] if records else [*head, *body])


def no_errors_failure(unexpected: Sequence[str], ignored: Sequence[str], *, verbose: bool) -> str:
    lines = [
        f"NVDA logged {_count(len(unexpected), 'unexpected error')}:",
        *_numbered(unexpected, verbose, limit=6),
    ]
    if ignored:
        count = _count(len(ignored), "item")
        lines.append(f"Also logged, and ignored by ignore-log-errors, {count}:")
        lines.extend(_numbered(ignored, verbose, limit=3))
    return "\n".join(lines)
