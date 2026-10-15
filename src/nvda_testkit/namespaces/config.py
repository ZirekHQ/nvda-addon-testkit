"""nvda.config -- read and write NVDA's configuration."""

from __future__ import annotations

from typing import Any

from ..rpcclient import RpcClient
from ..wire import ConfigPath, ConfigSnapshot


def _as_list(path: ConfigPath) -> list[str]:
    if isinstance(path, str):
        return [path]
    return list(path)


class ConfigNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def get(self, path: ConfigPath) -> Any:
        return self._rpc.call("config_get", _as_list(path))

    def set(self, path: ConfigPath, value: Any) -> None:
        self._rpc.call("config_set", _as_list(path), value)

    def snapshot(self) -> ConfigSnapshot:
        snapshot: ConfigSnapshot = self._rpc.call("config_snapshot")
        return snapshot

    def restore(self, snapshot: ConfigSnapshot) -> None:
        self._rpc.call("config_restore", snapshot)
