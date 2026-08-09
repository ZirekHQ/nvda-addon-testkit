"""nvda.keys -- send gestures through NVDA's own input pipeline.

press() returns only once NVDA has finished reacting, so a test never needs to
sleep between a keypress and the assertion about what it caused.
"""

from __future__ import annotations

from typing import Any

from ..rpcclient import RpcClient


class KeysNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def press(self, gesture: str, *, timeout: float = 10.0) -> None:
        self._rpc.call("keys_press", gesture, timeout)

    def press_all(self, *gestures: str, timeout: float = 10.0) -> None:
        for gesture in gestures:
            self.press(gesture, timeout=timeout)

    def type_text(self, text: str, *, timeout: float = 30.0) -> None:
        self._rpc.call("keys_type", text, timeout)

    def sent(self) -> list[dict[str, Any]]:
        """Every gesture sent this session. Goes into the replay trace."""
        return list(self._rpc.call("keys_sent"))
