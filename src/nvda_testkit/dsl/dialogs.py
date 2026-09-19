from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from ..client import NvdaClient
from ..errors import RpcError, TestkitError
from . import messages

LEAK = "Dialog opened by this test was still open at the end. Call close_dialog()."
BLOCKED = "A dialog is open. Call close_dialog() first."


class Dialogs:
    def __init__(self, client: NvdaClient) -> None:
        self._client = client
        self._open = False

    @property
    def is_open(self) -> bool:
        return self._open

    def require_none_open(self) -> None:
        if self._open:
            raise TestkitError(BLOCKED)

    def open(self, scenario: str) -> None:
        self.require_none_open()
        self._client.exec_nowait(scenario, label="opening a dialog")
        self._open = True

    def close(self, gesture: str = "enter", *, within: float = 10.0) -> None:
        __tracebackhide__ = True
        if not self._client.simulate_modal(gesture, timeout=within):
            raise AssertionError(
                f"No dialog took the foreground within {messages.seconds(within)}. "
                "Check that the scenario passed to open_dialog() shows a modal dialog."
            )
        self._open = False

    @contextmanager
    def dialog(self, scenario: str, close_with: str, within: float) -> Iterator[None]:
        self.open(scenario)
        try:
            yield
        finally:
            if self._open:
                self.close(close_with, within=within)

    def close_leftover(self) -> None:
        if not self._open:
            return
        try:
            self._client.simulate_modal("escape", timeout=5.0)
            self._client.wait_until_idle(timeout=5.0)
        except RpcError:
            self._client.restart_harness()
        finally:
            self._open = False
        raise AssertionError(LEAK)
