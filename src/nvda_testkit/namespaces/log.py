"""nvda.log -- NVDA's log as structured records.

assert_no_errors quotes every offending record in its failure message. That
message is frequently the only diagnostic available to a maintainer reading a
CI log on a machine that cannot run NVDA at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..rpcclient import RpcClient

_ERROR_LEVELS = frozenset({"ERROR", "CRITICAL"})
_WARNING_LEVELS = frozenset({"WARNING", "ERROR", "CRITICAL"})


@dataclass(frozen=True)
class LogRecord:
    level: str
    message: str
    timestamp: float = 0.0

    def __repr__(self) -> str:
        return f"{self.level}: {self.message}"


def _parse(payloads: list[dict]) -> list[LogRecord]:
    return [
        LogRecord(
            level=str(payload.get("level", "")),
            message=str(payload.get("message", "")),
            timestamp=float(payload.get("timestamp") or 0.0),
        )
        for payload in payloads
    ]


class LogNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def index(self) -> int:
        return int(self._rpc.call("log_index"))

    def since(self, index: int) -> list[LogRecord]:
        return _parse(self._rpc.call("log_since", index))

    def all(self) -> list[LogRecord]:
        return self.since(0)

    def clear(self) -> None:
        self._rpc.call("log_clear")

    def errors(self, *, since: int = 0) -> list[LogRecord]:
        return [record for record in self.since(since) if record.level in _ERROR_LEVELS]

    def warnings(self, *, since: int = 0) -> list[LogRecord]:
        return [record for record in self.since(since) if record.level in _WARNING_LEVELS]

    def _assert_clean(self, records: list[LogRecord], label: str) -> None:
        if not records:
            return
        listing = "\n".join(f"  {record}" for record in records)
        raise AssertionError(f"NVDA logged {len(records)} {label}:\n{listing}")

    def assert_no_errors(self, *, since: int = 0) -> None:
        self._assert_clean(self.errors(since=since), "error(s)")

    def assert_no_warnings(self, *, since: int = 0) -> None:
        self._assert_clean(self.warnings(since=since), "warning(s) or error(s)")

    def wait_for(
        self,
        pattern: str,
        *,
        timeout: float = 10.0,
        since: int | None = None,
        flags: int = re.IGNORECASE,
    ) -> LogRecord:
        start = self.index() if since is None else since

        def find():
            for record in self.since(start):
                if re.search(pattern, record.message, flags):
                    return record
            return None

        return self._rpc.poll_until(
            find,
            timeout=timeout,
            description=f"a log record matching {pattern!r}",
            last_seen=lambda: [record.message for record in self.since(start)],
        )
