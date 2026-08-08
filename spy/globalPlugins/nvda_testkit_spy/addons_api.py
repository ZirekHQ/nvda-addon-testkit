# coding: utf-8
"""Install, list and remove add-ons through NVDA's own addonHandler.

Installation is two-phase in NVDA: installAddonBundle extracts to a
.pendingInstall directory and completion happens on the next start. That shape
is preserved here rather than hidden, because exercising installTasks.onInstall
is the whole reason a test would call this.
"""

from .mainthread import run_on_main_thread
from .registry import rpc_method


def _state_of(addon):
    # INCOMPATIBLE has no branch here and is unreachable: incompatibility
    # reporting is Phase 6, not this slice.
    if addon.isPendingRemove:
        return "PENDING_REMOVE"
    if addon.isPendingInstall:
        return "PENDING_INSTALL"
    if addon.isDisabled:
        return "DISABLED"
    return "ENABLED"


def _find(name):
    import addonHandler

    for addon in addonHandler.getAvailableAddons(refresh=True):
        if addon.name == name:
            return addon
    return None


def _describe(addon):
    return {
        "name": addon.name,
        "version": getattr(addon, "version", "unknown"),
        "state": _state_of(addon),
    }


def _list():
    import addonHandler

    return [_describe(addon) for addon in addonHandler.getAvailableAddons(refresh=True)]


@rpc_method
def addons_list(timeout=10.0):
    # refresh=True rescans and rebuilds addonHandler's internal list, which is
    # closer to a mutation than a read; racing it against installAddonBundle
    # or requestRemove on the main thread would be a Windows-only flake.
    return run_on_main_thread(_list, timeout=timeout)


def _state(name):
    addon = _find(name)
    return _state_of(addon) if addon is not None else "NOT_INSTALLED"


@rpc_method
def addons_state(name, timeout=10.0):
    return run_on_main_thread(lambda: _state(name), timeout=timeout)


def _install(bundle_path):
    import addonHandler

    bundle = addonHandler.AddonBundle(bundle_path)
    return _describe(addonHandler.installAddonBundle(bundle))


@rpc_method
def addons_install(bundle_path, timeout=120.0):
    return run_on_main_thread(lambda: _install(bundle_path), timeout=timeout)


def _remove(name):
    addon = _find(name)
    if addon is None:
        raise LookupError("Add-on %r is not installed, so it cannot be removed." % (name,))
    addon.requestRemove()
    return True


@rpc_method
def addons_remove(name, timeout=60.0):
    return run_on_main_thread(lambda: _remove(name), timeout=timeout)
