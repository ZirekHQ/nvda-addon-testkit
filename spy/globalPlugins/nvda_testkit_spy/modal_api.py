# coding: utf-8
"""Dismiss a real modal dialog without going through NVDA's own queue.

A genuine wx.Dialog.ShowModal() nests its own message loop on NVDA's main
thread. Empirically (see tests_e2e/test_modal_dialog_investigation.py),
that loop never drains queueHandler.eventQueue for as long as the dialog is
up -- so run_on_main_thread (what eval_in_nvda, exec_in_nvda, and keys_press
all use) can never reach in and close it; a job queued that way just sits
there until the RPC caller's timeout fires, and the dialog is still open
afterwards.

The dialog's own message loop is still very much alive, though -- it has to
be, to receive the click a real user would make. simulate_modal reaches it
the way a human would instead: injected keyboard input via the Win32
SendInput API, sent from the RPC handler's own thread (never queued onto
NVDA's main thread, so the still-blocked queue is irrelevant to it), once
polling confirms our own process has taken the foreground -- which a modal
dialog does unconditionally on showing.

Pair this with exec_in_nvda_nowait (see eval_api.py), not exec_in_nvda, to
queue the scenario that opens the dialog: exec_in_nvda would block the
single-threaded RPC server itself until the dialog closed, and
simulate_modal's call would never even be dispatched.
"""

import ctypes
import ctypes.wintypes as wintypes
import math
import time

from .registry import rpc_method

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002
_GW_OWNER = 4

# Windows virtual-key codes for the gestures a modal message box responds to.
_VK = {
    "enter": 0x0D,
    "escape": 0x1B,
    "tab": 0x09,
    "space": 0x20,
    "yes": 0x59,  # 'Y' -- native MessageBox()-style YES_NO dialogs accept this directly.
    "no": 0x4E,  # 'N'
}

# The real Win32 INPUT/KEYBDINPUT/MOUSEINPUT/HARDWAREINPUT layout. SendInput
# rejects a call whose structure size doesn't match this exactly, so the
# union has to carry every real member, not just the KEYBDINPUT branch this
# module uses -- see https://learn.microsoft.com/windows/win32/api/winuser/ns-winuser-input.
_ULONG_PTR = ctypes.c_size_t


class _MouseInput(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _KeybdInput(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HardwareInput(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_short),
        ("wParamH", ctypes.c_ushort),
    ]


class _InputUnion(ctypes.Union):
    _fields_ = [("ki", _KeybdInput), ("mi", _MouseInput), ("hi", _HardwareInput)]


class _Input(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", ctypes.c_ulong), ("u", _InputUnion)]


def _user32():
    # GetForegroundWindow()/GetWindow() return a pointer-sized HWND; ctypes
    # defaults an undeclared restype to c_int, which truncates that handle
    # on 64-bit Windows and silently breaks every call built on it below.
    dll = ctypes.windll.user32
    dll.GetForegroundWindow.restype = wintypes.HWND
    dll.GetForegroundWindow.argtypes = []
    dll.GetWindowThreadProcessId.restype = wintypes.DWORD
    dll.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    dll.GetWindow.restype = wintypes.HWND
    dll.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    dll.IsWindowEnabled.restype = wintypes.BOOL
    dll.IsWindowEnabled.argtypes = [wintypes.HWND]
    dll.SendInput.restype = wintypes.UINT
    dll.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(_Input), ctypes.c_int]
    return dll


def _kernel32():
    dll = ctypes.windll.kernel32
    dll.GetCurrentProcessId.restype = wintypes.DWORD
    dll.GetCurrentProcessId.argtypes = []
    return dll


def _send_vk(vk):
    """Sends `vk` down then up via SendInput, raising if Windows rejected
    either event (e.g. another process holding an input-blocking state)
    instead of letting the caller believe the dialog was actually dismissed.
    """
    key_down = _Input(type=_INPUT_KEYBOARD, ki=_KeybdInput(vk, 0, 0, 0, 0))
    key_up = _Input(type=_INPUT_KEYBOARD, ki=_KeybdInput(vk, 0, _KEYEVENTF_KEYUP, 0, 0))
    user32 = _user32()
    sent_down = user32.SendInput(1, ctypes.byref(key_down), ctypes.sizeof(_Input))
    time.sleep(0.03)
    sent_up = user32.SendInput(1, ctypes.byref(key_up), ctypes.sizeof(_Input))
    if sent_down != 1 or sent_up != 1:
        raise OSError(
            "SendInput rejected the key event for vk=%r (down=%d, up=%d); Windows may be "
            "blocking synthetic input in this session." % (vk, sent_down, sent_up)
        )


def _foreground_owner():
    """(hwnd, owning pid) of the current foreground window, or (None, None)."""
    hwnd = _user32().GetForegroundWindow()
    if not hwnd:
        return None, None
    pid = wintypes.DWORD()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd, pid.value


def _is_owned_modal(hwnd):
    """Best-effort: true if `hwnd` looks like an application-modal dialog.

    An app-modal dialog disables its owner window for as long as it's up --
    the clearest Win32 signal available without inspecting the message loop
    itself. A dialog created with no parent (e.g. this module's own tests)
    has no owner to check, so this falls back to true -- which also means
    it can't tell such a dialog apart from any other ownerless top-level
    window our own process already had open (NVDA's main frame included).
    Only ever call this on a *newly*-foreground hwnd (see simulate_modal),
    never as the sole test against whatever was already there.
    """
    owner = _user32().GetWindow(hwnd, _GW_OWNER)
    if not owner:
        return True
    return not _user32().IsWindowEnabled(owner)


_UNSET = object()
_pending_baseline = {"hwnd": _UNSET}


def remember_foreground_baseline():
    """Records the current foreground hwnd for the next simulate_modal call.

    exec_in_nvda_nowait calls this before queueing its scenario, so a dialog
    the scenario foregrounds before simulate_modal's own RPC arrives still
    counts as a change from the baseline.
    """
    _pending_baseline["hwnd"], _ = _foreground_owner()


def _take_baseline():
    hwnd, _pending_baseline["hwnd"] = _pending_baseline["hwnd"], _UNSET
    if hwnd is _UNSET:
        hwnd, _ = _foreground_owner()
    return hwnd


def _require_seconds(name, value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("simulate_modal %s must be a number, got %r" % (name, value))
    if not math.isfinite(value) or value < 0:
        raise ValueError("simulate_modal %s must be finite and >= 0, got %r" % (name, value))


def _require_vk(gesture):
    vk = _VK.get(gesture) if isinstance(gesture, str) else None
    if vk is None:
        raise ValueError(
            "simulate_modal doesn't know gesture %r (have: %s)" % (gesture, sorted(_VK))
        )
    return vk


@rpc_method
def simulate_modal(gesture="enter", timeout=10.0, poll_interval=0.05):
    """Wait for our own process to bring a modal dialog to the foreground,
    then send it `gesture`. Returns False on timeout instead of raising,
    since a timeout here usually means the scenario never actually opened a
    dialog (a caller bug), not a hang worth crashing the RPC call over.
    Raises ValueError for an unknown gesture or a non-finite/negative timing.

    Requires the foreground hwnd to actually *change* from the baseline
    recorded when exec_in_nvda_nowait queued the scenario (or, without one,
    from when polling started), not just `_is_owned_modal(hwnd)` on its own:
    an ownerless dialog (see _is_owned_modal) is indistinguishable from a
    window our own process already had open before the scenario ran,
    e.g. NVDA's own main frame -- confirmed the hard way against a real
    NVDA, where dropping this check fired the gesture at whatever was
    already foreground and left the actual dialog open and blocked forever.
    """
    vk = _require_vk(gesture)
    _require_seconds("timeout", timeout)
    _require_seconds("poll_interval", poll_interval)
    our_pid = _kernel32().GetCurrentProcessId()
    initial_hwnd = _take_baseline()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd, pid = _foreground_owner()
        if hwnd and hwnd != initial_hwnd and pid == our_pid and _is_owned_modal(hwnd):
            _send_vk(vk)
            return True
        time.sleep(poll_interval)
    return False
