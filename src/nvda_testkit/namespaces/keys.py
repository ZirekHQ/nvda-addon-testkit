"""nvda.keys -- send gestures through NVDA's own input pipeline.

press() returns only once NVDA has finished reacting, so a test never needs to
sleep between a keypress and the assertion about what it caused.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..rpcclient import RpcClient


class KeysNamespace:
    def __init__(self, rpc: RpcClient, on_action: Callable[[str], object] | None = None) -> None:
        self._rpc = rpc
        self._on_action = on_action

    def _announce(self, label: str) -> None:
        if self._on_action is not None:
            self._on_action(label)

    def _press(self, gesture: str, timeout: float) -> None:
        self._rpc.call("keys_press", gesture, timeout)

    def press(self, gesture: str, *, timeout: float = 10.0) -> None:
        self._announce(f"pressing {gesture}")
        self._press(gesture, timeout)

    def press_all(self, *gestures: str, timeout: float = 10.0) -> None:
        self._announce("pressing " + ", ".join(gestures))
        for gesture in gestures:
            self._press(gesture, timeout)

    def type_text(self, text: str, *, timeout: float = 30.0) -> None:
        self._announce(f'typing "{text}"')
        self._rpc.call("keys_type", text, timeout)

    def sent(self) -> list[dict[str, Any]]:
        """Every gesture sent this session. Goes into the replay trace."""
        return list(self._rpc.call("keys_sent"))
