"""nvda.addons -- add-on install lifecycle.

Installation is two-phase, and that is exposed rather than hidden: install()
leaves the add-on PENDING_INSTALL, and only nvda.restart() makes it ENABLED.
A test of installTasks.onInstall depends on being able to see both halves.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from ..rpcclient import RpcClient


class AddonState(StrEnum):
    NOT_INSTALLED = "NOT_INSTALLED"
    PENDING_INSTALL = "PENDING_INSTALL"
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"
    PENDING_REMOVE = "PENDING_REMOVE"
    INCOMPATIBLE = "INCOMPATIBLE"


@dataclass(frozen=True)
class AddonInfo:
    name: str
    version: str
    state: AddonState

    @classmethod
    def from_payload(cls, payload: dict) -> AddonInfo:
        return cls(
            name=payload["name"],
            version=payload.get("version", "unknown"),
            state=AddonState(payload.get("state", "NOT_INSTALLED")),
        )


class AddonsNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def list(self) -> list[AddonInfo]:
        return [AddonInfo.from_payload(entry) for entry in self._rpc.call("addons_list")]

    def state(self, name: str) -> AddonState:
        return AddonState(self._rpc.call("addons_state", name))

    def install(self, bundle_path: str | Path) -> AddonInfo:
        """Install a bundle. The add-on stays PENDING_INSTALL until a restart."""
        payload = self._rpc.call("addons_install", str(Path(bundle_path).resolve()))
        return AddonInfo.from_payload(payload)

    def remove(self, name: str) -> None:
        """Mark for removal. Takes effect on the next restart."""
        self._rpc.call("addons_remove", name)
