"""Windows shell integration: single instance, autostart, window activation."""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "PeripheralBattery.SingleInstance.v1"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "电力王"
WINDOW_TITLE_PREFIX = "电力王"

_mutex_handle = None
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND,
                                 wintypes.LPARAM)
user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
user32.EnumWindows.restype = wintypes.BOOL
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsWindowVisible.restype = wintypes.BOOL


# -- single instance --------------------------------------------------------
def acquire_single_instance() -> bool:
    """True when this is the first running copy."""
    global _mutex_handle
    _mutex_handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def activate_existing_window() -> bool:
    """Bring an already running copy to the front."""
    found = {"hwnd": None}

    def callback(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        buf = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, buf, 256)
        if buf.value.startswith(WINDOW_TITLE_PREFIX):
            found["hwnd"] = hwnd
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    hwnd = found["hwnd"]
    if not hwnd:
        return False
    user32.ShowWindow(hwnd, 9)          # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


# -- autostart --------------------------------------------------------------
def _launch_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    interpreter = sys.executable
    windowed = os.path.join(os.path.dirname(interpreter), "pythonw.exe")
    if os.path.exists(windowed):
        interpreter = windowed
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "PeripheralBattery.pyw")
    return f'"{interpreter}" "{script}"'


def autostart_enabled() -> bool:
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, RUN_VALUE)
            return bool(value)
    except OSError:
        return False


def set_autostart(enabled: bool) -> bool:
    """Register or remove the Run-key entry; returns the resulting state."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                            winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, RUN_VALUE, 0, winreg.REG_SZ,
                                  _launch_command())
            else:
                try:
                    winreg.DeleteValue(key, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return enabled
    except OSError:
        return autostart_enabled()
