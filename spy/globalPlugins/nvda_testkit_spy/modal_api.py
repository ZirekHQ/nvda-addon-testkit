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
import time

from .registry import rpc_method

_INPUT_KEYBOARD = 1
_KEYEVENTF_KEYUP = 0x0002

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
    return ctypes.windll.user32


def _kernel32():
    return ctypes.windll.kernel32


def _send_vk(vk):
    key_down = _Input(type=_INPUT_KEYBOARD, ki=_KeybdInput(vk, 0, 0, 0, 0))
    key_up = _Input(type=_INPUT_KEYBOARD, ki=_KeybdInput(vk, 0, _KEYEVENTF_KEYUP, 0, 0))
    _user32().SendInput(1, ctypes.byref(key_down), ctypes.sizeof(_Input))
    time.sleep(0.03)
    _user32().SendInput(1, ctypes.byref(key_up), ctypes.sizeof(_Input))


def _foreground_owner():
    """(hwnd, owning pid) of the current foreground window, or (None, None)."""
    hwnd = _user32().GetForegroundWindow()
    if not hwnd:
        return None, None
    pid = ctypes.c_ulong()
    _user32().GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return hwnd, pid.value


@rpc_method
def simulate_modal(gesture="enter", timeout=10.0, poll_interval=0.05):
    """Wait for a window of our own process to take the foreground, then
    send it `gesture`. Returns False on timeout instead of raising, since a
    timeout here usually means the scenario never actually opened a dialog
    (a caller bug), not a hang worth crashing the RPC call over.
    """
    vk = _VK.get(gesture)
    if vk is None:
        raise ValueError(
            "simulate_modal doesn't know gesture %r (have: %s)" % (gesture, sorted(_VK))
        )
    our_pid = _kernel32().GetCurrentProcessId()
    initial_hwnd, _ = _foreground_owner()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        hwnd, pid = _foreground_owner()
        if hwnd and hwnd != initial_hwnd and pid == our_pid:
            _send_vk(vk)
            return True
        time.sleep(poll_interval)
    return False
