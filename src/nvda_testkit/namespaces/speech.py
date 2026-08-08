"""nvda.speech -- what NVDA asked to say."""

from __future__ import annotations

from ..rpcclient import RpcClient
from ..speechtypes import SpeechSequence, parse_sequences


class SpeechNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def index(self) -> int:
        """The current cursor. Pass it to since() to ignore everything so far."""
        return int(self._rpc.call("speech_index"))

    def since(self, index: int) -> list[SpeechSequence]:
        return parse_sequences(self._rpc.call("speech_since", index))

    def all(self) -> list[SpeechSequence]:
        return self.since(0)

    def last(self) -> SpeechSequence | None:
        sequences = self.all()
        return sequences[-1] if sequences else None

    def clear(self) -> None:
        self._rpc.call("speech_clear")

    def speak(self, text: str) -> None:
        self._rpc.call("speech_speak", text)

    def cancel(self) -> None:
        self._rpc.call("speech_cancel")

    def cancel_count(self) -> int:
        return int(self._rpc.call("speech_cancel_count"))

    def wait_for(
        self,
        pattern: str,
        *,
        timeout: float = 10.0,
        since: int | None = None,
    ) -> SpeechSequence:
        """Wait for a sequence whose text matches `pattern` (regex, case-insensitive).

        By default only speech produced after this call counts. Pass since=0 to
        search everything captured so far.

        Snapshots index() when called, so it cannot see speech already
        emitted. After a synchronous action such as press() or speak(),
        capture index() before the action and pass it as since.
        """
        start = self.index() if since is None else since

        def find():
            for sequence in self.since(start):
                if sequence.matches(pattern):
                    return sequence
            return None

        return self._rpc.poll_until(
            find,
            timeout=timeout,
            description=f"speech matching {pattern!r}",
            last_seen=lambda: [sequence.text for sequence in self.since(start)],
        )

    def wait_for_done(self, *, timeout: float = 10.0) -> None:
        """Wait until NVDA's event queue has drained, i.e. speech has been dispatched."""
        self._rpc.poll_until(
            lambda: self._rpc.call("wait_until_idle", 5.0),
            timeout=timeout,
            description="NVDA to finish dispatching speech",
        )
