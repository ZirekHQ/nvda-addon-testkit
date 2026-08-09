# coding: utf-8
"""Read and write NVDA's configuration.

Writes go through the main thread: NVDA reacts to some config changes
immediately, and doing that from the server thread is how you get a flake.
"""

import copy

from .mainthread import run_on_main_thread
from .registry import rpc_method


def _walk(path):
    import config

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
def config_get(path):
    return _walk(list(path))


def _assign(path, value):
    import config

    node = config.conf
    for key in path[:-1]:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


@rpc_method
def config_set(path, value):
    run_on_main_thread(lambda: _assign(list(path), value))
    return True


def _plain(node):
    """Deep-copy a ConfigObj section into ordinary dicts, so it survives the wire."""
    if hasattr(node, "items"):
        return {key: _plain(value) for key, value in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(item) for item in node]
    return node


@rpc_method
def config_snapshot():
    import config

    return _plain(config.conf)


def _restore(snapshot):
    import config

    config.conf.clear()
    # Assign key by key rather than update(): config.conf is a ConfigObj whose
    # __setitem__ rebuilds nested dicts into Section objects. update() can write
    # plain dicts straight in, leaving NVDA with a structurally different config
    # than it started with. This runs between every test, so a degraded
    # structure would poison the whole session.
    for key, value in copy.deepcopy(snapshot).items():
        config.conf[key] = value


@rpc_method
def config_restore(snapshot):
    run_on_main_thread(lambda: _restore(snapshot))
    return True
