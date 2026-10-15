"""End-to-end testing for NVDA add-ons against a real NVDA."""

from __future__ import annotations

from importlib import import_module
from typing import TYPE_CHECKING, Any

from nvda_testkit._version import __version__

if TYPE_CHECKING:
    from .client import NvdaClient
    from .dsl import Nvda
    from .errors import TestkitError
    from .namespaces.addons import AddonState
    from .settings import TestkitSettings
    from .speechtypes import SpeechSequence
    from .version import NvdaVersion

_EXPORTS = {
    "Nvda": ".dsl",
    "NvdaClient": ".client",
    "NvdaVersion": ".version",
    "TestkitError": ".errors",
    "TestkitSettings": ".settings",
    "SpeechSequence": ".speechtypes",
    "AddonState": ".namespaces.addons",
}

__all__ = [
    "AddonState",
    "Nvda",
    "NvdaClient",
    "NvdaVersion",
    "SpeechSequence",
    "TestkitError",
    "TestkitSettings",
    "__version__",
]


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    return getattr(import_module(module, __name__), name)
