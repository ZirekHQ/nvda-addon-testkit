"""nvda.braille -- the raw text NVDA sent to the braille display."""

from __future__ import annotations

import re

from ..rpcclient import RpcClient


class BrailleNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def index(self) -> int:
        return int(self._rpc.call("braille_index"))

    def since(self, index: int) -> list[str]:
        return [entry["text"] for entry in self._rpc.call("braille_since", index)]

    def all(self) -> list[str]:
        return self.since(0)

    def last(self) -> str | None:
        writes = self.all()
        return writes[-1] if writes else None

    def clear(self) -> None:
        self._rpc.call("braille_clear")

    def set_cell_count(self, count: int) -> None:
        self._rpc.call("braille_set_cell_count", int(count))

    def cell_count(self) -> int:
        return int(self._rpc.call("braille_cell_count"))

    def wait_for(
        self,
        pattern: str,
        *,
        timeout: float = 10.0,
        since: int | None = None,
        flags: int = re.IGNORECASE,
    ) -> str:
        start = self.index() if since is None else since

        def find():
            for text in self.since(start):
                if re.search(pattern, text, flags):
                    return text
            return None

        return self._rpc.poll_until(
            find,
            timeout=timeout,
            description=f"braille matching {pattern!r}",
            last_seen=lambda: self.since(start),
        )
