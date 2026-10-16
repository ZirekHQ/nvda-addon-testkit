from __future__ import annotations

from collections.abc import Callable, Iterable


def _failures(steps: Iterable[Callable[[], None]]) -> list[Exception]:
    failures: list[Exception] = []
    for step in steps:
        try:
            step()
        except Exception as error:
            failures.append(error)
    return failures


def _describe(error: Exception) -> str:
    if isinstance(error, AssertionError):
        return str(error)
    return f"{type(error).__name__}: {error}"


def _join_problems(failures: list[Exception]) -> str:
    return "\n".join(
        f"Teardown problem {number}: {_describe(failure)}"
        for number, failure in enumerate(failures, start=1)
    )


def run_all(steps: Iterable[Callable[[], None]]) -> None:
    """Run every step even if earlier ones fail, then raise one error naming each failure."""
    __tracebackhide__ = True
    failures = _failures(steps)
    if failures:
        raise AssertionError(_join_problems(failures)) from failures[0]
