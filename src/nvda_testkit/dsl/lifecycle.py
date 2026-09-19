from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..client import NvdaClient
from ..errors import TestkitError
from ..namespaces.addons import AddonState


def no_bundle() -> Path:
    raise TestkitError(
        "install_addon() needs a path, or an addon-bundle setting under [tool.nvda-testkit] "
        "in pyproject.toml."
    )


def _spoken(state: AddonState) -> str:
    return state.value.lower().replace("_", " ")


def parse_state(state: str | AddonState) -> AddonState:
    try:
        return AddonState(str(state).upper().replace(" ", "_"))
    except ValueError:
        valid = ", ".join(_spoken(member) for member in AddonState)
        raise ValueError(f"{state!r} is not an add-on state. Use one of: {valid}.") from None


class Lifecycle:
    def __init__(self, client: NvdaClient, bundle: Callable[[], Path]) -> None:
        self._client = client
        self._bundle = bundle
        self._installed: list[str] = []

    def install(self, path: Path | None) -> None:
        info = self._client.addons.install(path if path is not None else self._bundle())
        self._installed.append(info.name)
        self._client.restart_harness()
        self.should_have(info.name, AddonState.ENABLED)

    def remove(self, name: str) -> None:
        self._client.addons.remove(name)
        self._client.restart_harness()
        self.should_have(name, AddonState.NOT_INSTALLED)

    def should_have(self, name: str, state: str | AddonState) -> None:
        __tracebackhide__ = True
        wanted = parse_state(state)
        actual = self._client.addons.state(name)
        if actual is not wanted:
            raise AssertionError(
                f"Expected add-on {name} to be {_spoken(wanted)}, but it is {_spoken(actual)}."
            )

    def undo_all(self) -> None:
        absent = AddonState.NOT_INSTALLED
        try:
            present = [n for n in self._installed if self._client.addons.state(n) is not absent]
            for name in present:
                self._client.addons.remove(name)
            if present:
                self._client.restart_harness()
        finally:
            self._installed.clear()
