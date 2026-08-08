"""Minimal fakes for the NVDA modules the spy imports.

The spy only ever runs inside NVDA, and there is no pip-installable NVDA, so
its pure logic is tested by installing these into sys.modules before import.
Each stub records what the spy did to it, so tests assert on interactions
rather than on internals.
"""

from __future__ import annotations

import logging
import sys
import threading
import types
from typing import ClassVar
from unittest.mock import MagicMock


class FakeEventQueue:
    """Stands in for queueHandler's event queue plus the main thread draining it."""

    def __init__(self) -> None:
        self.pending: list = []
        self.auto_drain = True
        self._lock = threading.RLock()

    def put(self, func) -> None:
        with self._lock:
            self.pending.append(func)
        if self.auto_drain:
            self.drain()

    def drain(self) -> int:
        drained = 0
        while True:
            with self._lock:
                if not self.pending:
                    return drained
                func = self.pending.pop(0)
            func()
            drained += 1

    def empty(self) -> bool:
        with self._lock:
            return not self.pending


class FakeAction:
    """Stands in for extensionPoints.Action."""

    def __init__(self) -> None:
        self.handlers: list = []

    def register(self, handler) -> None:
        self.handlers.append(handler)

    def unregister(self, handler) -> None:
        if handler in self.handlers:
            self.handlers.remove(handler)

    def notify(self, **kwargs) -> None:
        for handler in list(self.handlers):
            handler(**kwargs)


class FakeFilter(FakeAction):
    """Stands in for extensionPoints.Filter."""

    def apply(self, value, **kwargs):
        for handler in list(self.handlers):
            value = handler(value, **kwargs)
        return value


def install(event_queue: FakeEventQueue | None = None) -> dict[str, types.ModuleType]:
    """Install the stubs into sys.modules and hand them back for assertions."""
    queue = event_queue or FakeEventQueue()

    queue_handler = types.ModuleType("queueHandler")
    queue_handler.eventQueue = queue
    queue_handler.queueFunction = lambda target_queue, func, *a, **kw: target_queue.put(
        lambda: func(*a, **kw)
    )
    queue_handler.pumpAll = queue.drain

    log_handler = types.ModuleType("logHandler")
    # A real Logger, not a bare MagicMock: log_tap attaches a logging.Handler
    # to it and needs records to actually flow. Each level method is then
    # mock-wrapped in place so existing tests can still assert call counts
    # and call args, same as they could against the old MagicMock.
    stub_logger = logging.getLogger("nvda_testkit_stub")
    stub_logger.setLevel(logging.DEBUG)
    stub_logger.propagate = False
    level_mocks = {
        level_name: MagicMock(wraps=getattr(stub_logger, level_name))
        for level_name in ("debug", "info", "warning", "error", "exception", "critical")
    }
    for level_name, mock in level_mocks.items():
        setattr(stub_logger, level_name, mock)
    # A real Logger has no reset_mock of its own; cascade to the level mocks
    # so callers can still reset the whole thing in one call, as they could
    # against the old bare MagicMock.
    stub_logger.reset_mock = lambda *a, **kw: [
        mock.reset_mock(*a, **kw) for mock in level_mocks.values()
    ]
    log_handler.log = stub_logger

    global_plugin_handler = types.ModuleType("globalPluginHandler")

    class GlobalPlugin:
        def __init__(self, *args, **kwargs):
            pass

        def terminate(self):
            pass

    global_plugin_handler.GlobalPlugin = GlobalPlugin

    version_info = types.ModuleType("versionInfo")
    version_info.version = "2026.1.1"
    version_info.formatBuildVersionString = lambda: "2026.1.1"

    build_version = types.ModuleType("buildVersion")
    build_version.version = "2026.1.1"

    addon_api_version = types.ModuleType("addonAPIVersion")
    addon_api_version.CURRENT = (2026, 1, 0)
    addon_api_version.BACK_COMPAT_TO = (2026, 1, 0)
    addon_api_version.formatForGUI = lambda v: ".".join(str(part) for part in v)

    core = types.ModuleType("core")
    core.postNvdaStartup = FakeAction()
    core.triggerNVDAExit = MagicMock()
    core.callLater = lambda delay, func, *a, **kw: func(*a, **kw)

    extension_points = types.ModuleType("extensionPoints")
    extension_points.Action = FakeAction
    extension_points.Filter = FakeFilter

    config_module = types.ModuleType("config")
    config_module.conf = {
        "speech": {"synth": "espeak", "espeak": {"rate": 50}},
        "braille": {"display": "noBraille"},
    }
    config_module.post_configProfileSwitch = FakeAction()

    speech_extensions = types.ModuleType("speech.extensions")
    speech_extensions.pre_speech = FakeAction()
    speech_extensions.pre_speechQueued = FakeAction()
    speech_extensions.filter_speechSequence = FakeFilter()
    speech_extensions.speechCanceled = FakeAction()
    speech_extensions.pre_speechCanceled = FakeAction()
    speech_extensions.post_speechPaused = FakeAction()

    speech_commands = types.ModuleType("speech.commands")

    class _Command:
        def __repr__(self):
            fields = ", ".join(f"{k}={v!r}" for k, v in sorted(vars(self).items()))
            return f"{type(self).__name__}({fields})"

    class IndexCommand(_Command):
        def __init__(self, index):
            self.index = index

    class LangChangeCommand(_Command):
        def __init__(self, lang):
            self.lang = lang

    class BreakCommand(_Command):
        def __init__(self, time):
            self.time = time

    speech_commands.IndexCommand = IndexCommand
    speech_commands.LangChangeCommand = LangChangeCommand
    speech_commands.BreakCommand = BreakCommand

    speech = types.ModuleType("speech")
    speech.extensions = speech_extensions
    speech.commands = speech_commands
    speech.speak = MagicMock()
    speech.cancelSpeech = MagicMock()

    braille_extensions = types.ModuleType("braille.extensions")
    braille_extensions.pre_writeCells = FakeAction()
    braille_extensions.filter_displayDimensions = FakeFilter()

    braille_display = types.ModuleType("braille.display")

    class DisplayDimensions:
        def __init__(self, numRows, numCols):
            self.numRows = numRows
            self.numCols = numCols

        def __eq__(self, other):
            return (self.numRows, self.numCols) == (other.numRows, other.numCols)

    braille_display.DisplayDimensions = DisplayDimensions

    braille = types.ModuleType("braille")
    braille.extensions = braille_extensions
    braille.display = braille_display
    braille.handler = MagicMock()

    keyboard_handler = types.ModuleType("keyboardHandler")

    class KeyboardInputGesture:
        created: ClassVar[list] = []

        def __init__(self, name):
            self.name = name

        @classmethod
        def fromName(cls, name):
            gesture = cls(name)
            cls.created.append(name)
            return gesture

        def __repr__(self):
            return f"KeyboardInputGesture({self.name!r})"

    keyboard_handler.KeyboardInputGesture = KeyboardInputGesture

    input_core = types.ModuleType("inputCore")
    input_core.manager = MagicMock()
    input_core.NoInputGestureAction = type("NoInputGestureAction", (Exception,), {})

    addon_handler = types.ModuleType("addonHandler")

    class _FakeAddon:
        def __init__(self, name, version="1.0.0", pending_install=False):
            self.name = name
            self.version = version
            self.isPendingInstall = pending_install
            self.isPendingRemove = False
            self.isDisabled = False
            self.isRunning = not pending_install

        def requestRemove(self):
            self.isPendingRemove = True

    addon_handler.Addon = _FakeAddon
    addon_handler.INSTALLED = []

    class AddonBundle:
        def __init__(self, path):
            self.path = path
            self.manifest = {"name": "demo-addon", "version": "1.0.0"}

    addon_handler.AddonBundle = AddonBundle

    def _install_addon_bundle(bundle):
        addon = _FakeAddon(
            bundle.manifest["name"], bundle.manifest["version"], pending_install=True
        )
        addon_handler.INSTALLED.append(addon)
        return addon

    addon_handler.installAddonBundle = _install_addon_bundle
    addon_handler.getAvailableAddons = lambda refresh=False: iter(list(addon_handler.INSTALLED))

    modules = {
        "queueHandler": queue_handler,
        "logHandler": log_handler,
        "globalPluginHandler": global_plugin_handler,
        "versionInfo": version_info,
        "buildVersion": build_version,
        "addonAPIVersion": addon_api_version,
        "core": core,
        "extensionPoints": extension_points,
        "config": config_module,
        "speech": speech,
        "speech.extensions": speech_extensions,
        "speech.commands": speech_commands,
        "braille": braille,
        "braille.extensions": braille_extensions,
        "braille.display": braille_display,
        "keyboardHandler": keyboard_handler,
        "inputCore": input_core,
        "addonHandler": addon_handler,
    }
    sys.modules.update(modules)
    modules["_eventQueue"] = queue
    return modules
