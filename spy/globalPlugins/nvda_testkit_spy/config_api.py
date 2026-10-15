# coding: utf-8
"""Read and write NVDA's configuration.

Every access goes through the main thread. Writes: NVDA reacts to some config
changes immediately, and doing that from the server thread is how you get a
flake. Reads: config.conf is a live structure NVDA's main thread mutates
during and after startup, so iterating it from the server thread races those
mutations -- observed as "dictionary changed size during iteration" raised
from inside NVDA's own ConfigManager.dict().
"""

from __future__ import annotations

import copy
from typing import Any

import config

from .mainthread import run_on_main_thread
from .registry import rpc_method


def _walk(path: list[Any]) -> Any:
    node = config.conf
    for key in path:
        try:
            node = node[key]
        except (KeyError, TypeError) as error:
            raise KeyError(
                "No such config path: %s (failed at %r)" % (".".join(map(str, path)), key)
            ) from error
    return node


@rpc_method
def config_get(path: list[Any]) -> Any:
    return run_on_main_thread(lambda: _plain(_walk(list(path))))


def _is_section(node: Any) -> bool:
    """Section-like: a dict, a ConfigObj Section, or an AggregatedSection."""
    return hasattr(node, "items") and hasattr(node, "__setitem__")


def _assign(path: list[Any], value: Any) -> None:
    node = config.conf
    for key in path[:-1]:
        if key not in node or not _is_section(node[key]):
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


@rpc_method
def config_set(path: list[Any], value: Any) -> bool:
    run_on_main_thread(lambda: _assign(list(path), value))
    return True


def _plain(node: Any) -> Any:
    """Deep-copy NVDA's config objects into ordinary dicts, so they survive the wire."""
    if hasattr(node, "dict"):
        node = node.dict()
    if hasattr(node, "items"):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(item) for item in node]
    if isinstance(node, (str, int, float, bool, bytes, type(None))):
        return node
    return str(node)


def _snapshot() -> dict[str, Any]:
    return _plain(config.conf)


@rpc_method
def config_snapshot() -> dict[str, Any]:
    return run_on_main_thread(_snapshot)


def _restore(snapshot: dict[str, Any]) -> None:
    live = config.conf.dict()
    for key, value in copy.deepcopy(snapshot).items():
        config.conf[key] = value
    for key in live:
        if key not in snapshot:
            config.conf[key] = {}


@rpc_method
def config_restore(snapshot: dict[str, Any]) -> bool:
    run_on_main_thread(lambda: _restore(snapshot))
    return True
