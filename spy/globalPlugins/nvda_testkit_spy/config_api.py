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
    return _plain(_walk(list(path)))


def _is_section(node):
    """Section-like: a dict, a ConfigObj Section, or an AggregatedSection."""
    return hasattr(node, "items") and hasattr(node, "__setitem__")


def _assign(path, value):
    import config

    node = config.conf
    for key in path[:-1]:
        # An AggregatedSection is not a dict, so an isinstance(..., dict) test
        # here would overwrite a whole live section with {} on the way past it.
        if key not in node or not _is_section(node[key]):
            node[key] = {}
        node = node[key]
    node[path[-1]] = value


@rpc_method
def config_set(path, value):
    run_on_main_thread(lambda: _assign(list(path), value))
    return True


def _plain(node):
    """Deep-copy NVDA's config objects into ordinary dicts, so they survive the wire."""
    # config.conf is a ConfigManager and its sections are AggregatedSections;
    # neither is a dict and xmlrpc can marshal neither, but both expose dict().
    if hasattr(node, "dict"):
        node = node.dict()
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

    # ConfigManager offers no clear(), no update() and no delete: a top-level key
    # a test invented can only be emptied here, never removed.
    live = config.conf.dict()
    for key, value in copy.deepcopy(snapshot).items():
        config.conf[key] = value
    for key in live:
        if key not in snapshot:
            config.conf[key] = {}


@rpc_method
def config_restore(snapshot):
    run_on_main_thread(lambda: _restore(snapshot))
    return True
