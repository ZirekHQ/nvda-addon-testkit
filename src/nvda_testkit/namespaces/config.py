"""nvda.config -- read and write NVDA's configuration."""

from __future__ import annotations

from typing import Any

from ..rpcclient import RpcClient


def _as_list(path) -> list[str]:
    if isinstance(path, str):
        return [path]
    return list(path)


class ConfigNamespace:
    def __init__(self, rpc: RpcClient) -> None:
        self._rpc = rpc

    def get(self, path) -> Any:
        return self._rpc.call("config_get", _as_list(path))

    def set(self, path, value: Any) -> None:
        self._rpc.call("config_set", _as_list(path), value)

    def snapshot(self) -> dict:
        return self._rpc.call("config_snapshot")

    def restore(self, snapshot: dict) -> None:
        self._rpc.call("config_restore", snapshot)
