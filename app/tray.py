"""System tray icon (notification area) via Shell_NotifyIcon.

Implemented with ctypes so there is no third-party dependency: a message-only
window receives the tray callbacks, the icon bitmap is rasterised by hand so
its colour can follow the battery level, and a popup menu provides the
commands.
"""

from __future__ import annotations

import ctypes
import math
import os
import sys
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# -- constants --------------------------------------------------------------
WM_APP = 0x8000
WM_TRAYICON = WM_APP + 1
WM_NULL = 0x0000
WM_CLOSE = 0x0010
WM_DESTROY = 0x0002
WM_COMMAND = 0x0111
WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

NIM_ADD = 0
WM_TIMER = 0x0113
TIMER_PROMOTE = 1
NIM_MODIFY = 1
NIM_DELETE = 2
NIF_MESSAGE = 0x01
NIF_ICON = 0x02
NIF_TIP = 0x04
NIF_INFO = 0x10
NIIF_INFO = 0x01

MF_STRING = 0x0000
MF_SEPARATOR = 0x0800
MF_CHECKED = 0x0008
TPM_RETURNCMD = 0x0100
TPM_RIGHTBUTTON = 0x0002

IDM_TOGGLE = 1
IDM_REFRESH = 2
IDM_PIN = 3
IDM_AUTOSTART = 4
IDM_QUIT = 5

COLORS = {
    "ok": (74, 217, 145),
    "mid": (255, 197, 61),
    "low": (255, 149, 88),
    "critical": (255, 92, 92),
    "charging": (76, 224, 176),
    "unknown": (150, 160, 175),
}

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", GUID),
        ("hBalloonIcon", wintypes.HICON),
    ]


class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HICON),
    ]


class MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND), ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM), ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD), ("pt", wintypes.POINT),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER),
                ("bmiColors", wintypes.DWORD * 3)]


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                ("hbmColor", wintypes.HBITMAP)]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("guidItem", GUID)]


class RECT(ctypes.Structure):
    _fields_ = [("left", wintypes.LONG), ("top", wintypes.LONG),
                ("right", wintypes.LONG), ("bottom", wintypes.LONG)]


user32.RegisterClassExW.argtypes = [ctypes.POINTER(WNDCLASSEXW)]
user32.RegisterClassExW.restype = wintypes.WORD
user32.CreateWindowExW.restype = wintypes.HWND
user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                  wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT,
                                wintypes.WPARAM, wintypes.LPARAM]
user32.PostMessageW.restype = wintypes.BOOL
user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), wintypes.HWND,
                               wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.CreatePopupMenu.restype = wintypes.HMENU
user32.TrackPopupMenu.restype = wintypes.UINT
user32.CreateIconIndirect.restype = wintypes.HICON
user32.DestroyIcon.argtypes = [wintypes.HICON]
gdi32.CreateDIBSection.restype = wintypes.HBITMAP
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
shell32.Shell_NotifyIconW.argtypes = [wintypes.DWORD,
                                      ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wintypes.BOOL
shell32.Shell_NotifyIconGetRect.argtypes = [ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(RECT)]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long


def _color_for(percent: int | None, charging: bool | None) -> tuple:
    if percent is None:
        return COLORS["unknown"]
    if charging:
        return COLORS["charging"]
    if percent <= 10:
        return COLORS["critical"]
    if percent <= 30:
        return COLORS["low"]
    if percent <= 60:
        return COLORS["mid"]
    return COLORS["ok"]


def _sdf_round_rect(x: float, y: float, x0: float, y0: float,
                    x1: float, y1: float, r: float) -> float:
    cx = min(max(x, x0 + r), x1 - r)
    cy = min(max(y, y0 + r), y1 - r)
    return math.hypot(x - cx, y - cy) - r


def _rasterize(percent: int | None, charging: bool | None,
               size: int = 64) -> bytes:
    """Draw a battery into a BGRA buffer (top-down, no external libs)."""
    color = _color_for(percent, charging)
    scale = size / 64.0
    pixels = bytearray(size * size * 4)
    level = max(0.0, min(100.0, percent if percent is not None else 0.0))

    body = (10 * scale, 22 * scale, 52 * scale, 50 * scale, 9 * scale)
    cap = (52 * scale, 30 * scale, 60 * scale, 42 * scale, 3 * scale)
    fill_x1 = 17 * scale
    fill_x2 = fill_x1 + 28 * scale * level / 100.0

    for py in range(size):
        y = py + 0.5
        for px in range(size):
            x = px + 0.5
            alpha = 0.0
            # body outline
            d_body = _sdf_round_rect(x, y, *body)
            d_inner = _sdf_round_rect(x, y, body[0] + 4 * scale,
                                      body[1] + 4 * scale, body[2] - 4 * scale,
                                      body[3] - 4 * scale, 6 * scale)
            if d_body < 0 and d_inner > 0:
                alpha = 1.0
            elif d_body < 0:
                alpha = 0.0
            if d_body < 0.5 and d_body > -0.5:
                alpha = max(alpha, 0.5 - d_body)
            # cap
            d_cap = _sdf_round_rect(x, y, *cap)
            if d_cap < 0:
                alpha = 1.0
            # level fill inside the body
            if percent is not None and d_inner < 0:
                if fill_x1 <= x <= fill_x2 and \
                        body[1] + 5 * scale < y < body[3] - 5 * scale:
                    alpha = 1.0
            if alpha <= 0:
                continue
            alpha = min(1.0, alpha)
            index = (py * size + px) * 4
            pixels[index] = int(color[2] * alpha)
            pixels[index + 1] = int(color[1] * alpha)
            pixels[index + 2] = int(color[0] * alpha)
            pixels[index + 3] = int(255 * alpha)
    return bytes(pixels)


def _path_matches(entry_path: str, target: str) -> bool:
    r"""Compare a NotifyIconSettings path with our exe path.

    Explorer sometimes stores the path with a KNOWNFOLDERID prefix, e.g.
    ``{6D809377-...}\PeripheralBattery\app.exe`` instead of a literal
    path, so exact comparison silently fails. Fall back to suffix matching
    for that form.
    """
    candidate = os.path.normcase(entry_path.strip())
    if not candidate:
        return False
    if candidate.startswith("{"):
        brace = candidate.find("}")
        if brace < 0:
            return False
        rest = candidate[brace + 1:]
        return bool(rest) and target.endswith(rest)
    try:
        return os.path.normcase(os.path.abspath(entry_path)) == target
    except OSError:
        return False


def _make_hicon(percent: int | None, charging: bool | None,
                size: int = 32) -> int:
    data = _rasterize(percent, charging, size)
    header = BITMAPINFO()
    header.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.bmiHeader.biWidth = size
    header.bmiHeader.biHeight = -size
    header.bmiHeader.biPlanes = 1
    header.bmiHeader.biBitCount = 32
    header.bmiHeader.biCompression = 0  # BI_RGB
    bits = ctypes.c_void_p()
    hdc = user32.GetDC(None)
    color_bitmap = gdi32.CreateDIBSection(
        wintypes.HDC(hdc), ctypes.byref(header), 0, ctypes.byref(bits),
        None, 0)
    ctypes.memmove(bits, data, len(data))

    mask_header = BITMAPINFO()
    mask_header.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    mask_header.bmiHeader.biWidth = size
    mask_header.bmiHeader.biHeight = -size
    mask_header.bmiHeader.biPlanes = 1
    mask_header.bmiHeader.biBitCount = 1
    mask_bits = ctypes.c_void_p()
    mask_bitmap = gdi32.CreateDIBSection(
        wintypes.HDC(hdc), ctypes.byref(mask_header), 0,
        ctypes.byref(mask_bits), None, 0)
    stride = ((size + 31) // 32) * 4
    ctypes.memset(mask_bits, 0, stride * size)

    info = ICONINFO()
    info.fIcon = 1
    info.hbmMask = mask_bitmap
    info.hbmColor = color_bitmap
    icon = user32.CreateIconIndirect(ctypes.byref(info))

    user32.ReleaseDC(None, wintypes.HDC(hdc))
    gdi32.DeleteObject(color_bitmap)
    gdi32.DeleteObject(mask_bitmap)
    return icon


class TrayIcon:
    """Notification-area icon with a popup menu."""

    CLASS_NAME = "PeripheralBatteryTrayWnd"

    def __init__(self, dispatch):
        self._dispatch = dispatch
        self._hwnd = None
        self._thread = None
        self._ready = False
        self._hicon = None
        self._pinned = False
        self._autostart = False
        self._last_state = None
        self._tooltip = "电力王"
        self._wndproc_ref = WNDPROC(self._wndproc)
        self.last_error = ""

    # -- lifecycle --------------------------------------------------------
    def start(self) -> bool:
        self._thread = threading.Thread(target=self._run, name="tray",
                                        daemon=True)
        self._thread.start()
        for _ in range(50):
            if self._ready or not self._thread.is_alive():
                break
            threading.Event().wait(0.02)
        return self._ready

    def stop(self) -> None:
        if self._hwnd:
            try:
                user32.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
            except Exception:
                pass
        self._hwnd = None
        self._ready = False

    def _log(self, message: str) -> None:
        self.last_error = message
        try:
            from .config import config_dir
            path = "%s\\tray.log" % config_dir()
            with open(path, "a", encoding="utf-8") as handle:
                handle.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")
        except Exception:
            pass

    def _run(self) -> None:
        self._log('tray thread started')
        try:
            instance = kernel32.GetModuleHandleW(None)
            wc = WNDCLASSEXW()
            wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
            wc.lpfnWndProc = self._wndproc_ref
            wc.hInstance = instance
            wc.lpszClassName = self.CLASS_NAME
            if not user32.RegisterClassExW(ctypes.byref(wc)):
                self._log(f"RegisterClassEx failed: {ctypes.get_last_error()}")

            self._hwnd = user32.CreateWindowExW(
                0, self.CLASS_NAME, "PeripheralBatteryTray", 0,
                0, 0, 0, 0, None, None, instance, None)
            if not self._hwnd:
                self._log(f"CreateWindowEx failed: {ctypes.get_last_error()}")
                return

            self._hicon = _make_hicon(None, None)
            if not self._hicon:
                self._log(f"CreateIconIndirect failed: {ctypes.get_last_error()}")
            data = self._notify_data()
            data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
            data.uCallbackMessage = WM_TRAYICON
            data.hIcon = self._hicon
            data.szTip = self._tooltip
            if not shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data)):
                self._log(f"Shell_NotifyIcon ADD failed: "
                          f"{ctypes.get_last_error()}")
            else:
                self._ready = True
                self._log("tray icon added")
                # Windows 11 parks new icons in the overflow area; mark our
                # own entry as promoted and re-add so it lands on the taskbar
                if self._promote_icon():
                    shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
                    shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
                    self._log("icon promoted, re-added")
                else:
                    # Explorer creates the NotifyIconSettings entry only after
                    # the icon exists; retry a few times so a fresh install
                    # still lands on the taskbar instead of the overflow
                    self._promote_tries = 0
                    user32.SetTimer(self._hwnd, TIMER_PROMOTE, 3000, None)

            message = MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))

            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
            if self._hicon:
                user32.DestroyIcon(self._hicon)
                self._hicon = None
        except Exception as exc:  # pragma: no cover - defensive
            self._log(f'tray thread crashed: {exc!r}')

    def icon_rect(self):
        """Screen rectangle of the tray icon (for anchoring the flyout)."""
        if not self._ready or not self._hwnd:
            return None
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = self._hwnd
        ident.uID = 1
        rect = RECT()
        try:
            result = shell32.Shell_NotifyIconGetRect(ctypes.byref(ident),
                                                     ctypes.byref(rect))
        except Exception:
            return None
        if result != 0:
            return None
        return (rect.left, rect.top, rect.right, rect.bottom)

    def _notify_data(self) -> NOTIFYICONDATAW:
        data = NOTIFYICONDATAW()
        data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        data.hWnd = self._hwnd
        data.uID = 1
        return data

    def _promote_icon(self) -> bool:
        """Mark our own NotifyIconSettings entry as shown on the taskbar.

        Windows 11 keeps newly added icons in the overflow flyout by default;
        the per-icon flag lives in HKCU and is honoured when the icon is
        added, so we flip it and re-add the icon once.
        """
        try:
            import winreg
            target = os.path.normcase(os.path.abspath(sys.executable))
            root = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Control Panel\NotifyIconSettings", 0,
                winreg.KEY_READ | winreg.KEY_WRITE)
        except OSError:
            return False
        changed = False
        try:
            index = 0
            while index < 256:
                try:
                    name = winreg.EnumKey(root, index)
                except OSError:
                    break
                index += 1
                try:
                    with winreg.OpenKey(root, name, 0,
                                        winreg.KEY_READ | winreg.KEY_WRITE) as entry:
                        path = str(winreg.QueryValueEx(entry, "ExecutablePath")[0])
                        if not _path_matches(path, target):
                            continue
                        try:
                            current = winreg.QueryValueEx(entry, "IsPromoted")[0]
                        except OSError:
                            current = 0
                        if not current:
                            winreg.SetValueEx(entry, "IsPromoted", 0,
                                              winreg.REG_DWORD, 1)
                            changed = True
                except OSError:
                    continue
        finally:
            root.Close()
        return changed

    # -- window procedure -------------------------------------------------
    def _wndproc(self, hwnd, message, wparam, lparam):
        if message == WM_TRAYICON:
            event = lparam & 0xFFFF
            if event in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
                self._dispatch("popup")
            elif event in (WM_RBUTTONUP, WM_CONTEXTMENU):
                self._show_menu(hwnd)
            return 0
        if message == WM_TIMER and wparam == TIMER_PROMOTE:
            self._promote_tries = getattr(self, "_promote_tries", 0) + 1
            if self._promote_icon():
                data = self._notify_data()
                data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
                data.uCallbackMessage = WM_TRAYICON
                data.hIcon = self._hicon
                data.szTip = self._tooltip
                shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
                shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
                self._log("icon promoted on retry, re-added")
                user32.KillTimer(hwnd, TIMER_PROMOTE)
            elif self._promote_tries >= 40:
                self._log("icon promotion skipped (no settings entry yet)")
                user32.KillTimer(hwnd, TIMER_PROMOTE)
            return 0
        if message == WM_CLOSE:
            user32.DestroyWindow(hwnd)
            return 0
        if message == WM_DESTROY:
            user32.PostQuitMessage(0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _show_menu(self, hwnd) -> None:
        menu = user32.CreatePopupMenu()
        user32.AppendMenuW(menu, MF_STRING, IDM_TOGGLE, "打开主窗口")
        user32.AppendMenuW(menu, MF_STRING, IDM_REFRESH, "立即刷新")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self._pinned else 0),
                           IDM_PIN, "窗口置顶")
        user32.AppendMenuW(menu, MF_STRING | (MF_CHECKED if self._autostart else 0),
                           IDM_AUTOSTART, "开机自动启动")
        user32.AppendMenuW(menu, MF_SEPARATOR, 0, None)
        user32.AppendMenuW(menu, MF_STRING, IDM_QUIT, "退出")
        point = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.SetForegroundWindow(hwnd)
        command = user32.TrackPopupMenu(
            menu, TPM_RETURNCMD | TPM_RIGHTBUTTON, point.x, point.y, 0,
            hwnd, None)
        user32.PostMessageW(hwnd, WM_NULL, 0, 0)
        user32.DestroyMenu(menu)
        actions = {
            IDM_TOGGLE: "show", IDM_REFRESH: "refresh", IDM_PIN: "pin",
            IDM_AUTOSTART: "autostart", IDM_QUIT: "quit",
        }
        if command in actions:
            self._dispatch(actions[command])

    # -- updates ----------------------------------------------------------
    def update(self, devices, pinned: bool, autostart: bool) -> None:
        if not self._ready or not self._hwnd:
            return
        self._pinned = pinned
        self._autostart = autostart

        known = [d for d in devices if d.percent is not None and d.online]
        if known:
            lowest = min(known, key=lambda d: d.percent)
            percent, charging = lowest.percent, lowest.charging
        else:
            percent, charging = None, None

        lines = ["电力王"]
        for device in sorted(devices, key=lambda d: (d.percent is None,
                                                     d.percent or 0))[:3]:
            value = "—" if device.percent is None else f"{device.percent}%"
            if device.charging:
                value += " 充电中"
            if not device.online:
                value += " 离线"
            lines.append(f"{device.name[:22]}  {value}")
        if len(devices) > 3:
            lines.append(f"… 还有 {len(devices) - 3} 个")
        tooltip = "\n".join(lines)[:120]

        state = (percent, charging, tooltip)
        if state == self._last_state:
            return
        self._last_state = state

        data = self._notify_data()
        data.uFlags = NIF_ICON | NIF_TIP
        data.szTip = tooltip
        if self._hicon:
            user32.DestroyIcon(self._hicon)
        self._hicon = _make_hicon(percent, charging)
        data.hIcon = self._hicon
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))

    def notify(self, message: str, title: str = "电力王") -> None:
        if not self._ready or not self._hwnd:
            return
        data = self._notify_data()
        data.uFlags = NIF_INFO
        data.szInfo = message[:255]
        data.szInfoTitle = title[:63]
        data.dwInfoFlags = NIIF_INFO
        shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(data))
