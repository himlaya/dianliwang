"""Tkinter interface for the peripheral battery monitor."""

from __future__ import annotations

import ctypes
import os
import queue
import sys
import time
import tkinter as tk
import tkinter.font as tkfont
from ctypes import wintypes
from tkinter import ttk

from .config import Config
from .model import (KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE,
                    Device)
from .monitor import Monitor
from . import __version__, shell
from .alert import LowBatteryPopup
from . import tray as tray_module

BG = "#0b0e13"
SURFACE = "#171d27"
SURFACE_2 = "#1e2532"
CARD = SURFACE
CARD_HOVER = "#1c2330"
BORDER = "#242c38"
CHIP = "#1f2734"
TEXT = "#e9eef7"
MUTED = "#8d98a9"
DIM = "#5d6879"
ACCENT = "#5b8cff"
ACCENT_SOFT = "#1c2740"
WARN = "#ffb02e"
WARN_SOFT = "#2b2314"
TRACK = "#232b38"

RADIUS_CARD = 32
_TRANSPARENT_KEY = "#ff00fe"
RADIUS_CHIP = 22
RADIUS_BAR = 6

APP_TITLE = "电力王"


def _log_line(message: str) -> None:
    try:
        from .config import config_dir
        with open(os.path.join(config_dir(), "flyout.log"), "a",
                  encoding="utf-8") as handle:
            handle.write(f"[{time.strftime('%H:%M:%S')}] {message}\n")
    except Exception:
        pass


def _log_exception(exc, value, tb) -> None:
    """Windowed builds have no console, so keep a small crash log."""
    import traceback
    try:
        from .config import config_dir
        path = os.path.join(config_dir(), "error.log")
        if os.path.exists(path) and os.path.getsize(path) > 256 * 1024:
            os.replace(path, path + ".old")
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}]\n")
            traceback.print_exception(exc, value, tb, file=fh)
    except Exception:
        pass


def _enable_dpi_awareness() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)  # system DPI aware
        return
    except Exception:
        pass
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _dark_titlebar(window: tk.Misc) -> None:
    """Ask DWM for a dark title bar so the frame matches the content."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1)
        for attribute in (20, 19):
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


def _round_window_corners(window: tk.Misc) -> None:
    """Windows 11 rounded window frame (DWMWCP_ROUND)."""
    try:
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        preference = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 33, ctypes.byref(preference), ctypes.sizeof(preference))
    except Exception:
        pass


def _style_window(window: tk.Misc) -> None:
    _dark_titlebar(window)
    _round_window_corners(window)


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)


def draw_icon(canvas: tk.Canvas, kind: str, cx: float, cy: float,
              s: float, color: str) -> None:
    """Small vector device icons, drawn with basic canvas primitives."""

    def line(*pts, width=1.6):
        canvas.create_line(*pts, fill=color, width=width * s,
                           capstyle="round", joinstyle="round")

    if kind == KIND_MOUSE:
        canvas.create_oval(cx - 6 * s, cy - 9 * s, cx + 6 * s, cy + 9 * s,
                           outline=color, width=1.7 * s)
        line(cx, cy - 9 * s, cx, cy - 3 * s, width=1.4)
        canvas.create_oval(cx - 1.1 * s, cy - 7.2 * s, cx + 1.1 * s, cy - 4.4 * s,
                           outline=color, width=1.2 * s)
    elif kind == KIND_KEYBOARD:
        canvas.create_rectangle(cx - 11 * s, cy - 6 * s, cx + 11 * s, cy + 6 * s,
                                outline=color, width=1.6 * s)
        for row in (-3, 0, 3):
            for i in range(-4, 5):
                canvas.create_rectangle(cx + i * 2.3 * s - 0.6 * s,
                                        cy + row * s - 0.55 * s,
                                        cx + i * 2.3 * s + 0.6 * s,
                                        cy + row * s + 0.55 * s,
                                        outline="", fill=color)
    elif kind == KIND_GAMEPAD:
        canvas.create_oval(cx - 11 * s, cy - 7 * s, cx + 11 * s, cy + 7 * s,
                           outline=color, width=1.7 * s)
        canvas.create_oval(cx - 7 * s, cy - 2 * s, cx - 3 * s, cy + 2 * s,
                           outline=color, width=1.4 * s)
        line(cx + 5 * s, cy - 2.4 * s, cx + 5 * s, cy + 2.4 * s, width=1.4)
        line(cx + 2.6 * s, cy, cx + 7.4 * s, cy, width=1.4)
    elif kind == KIND_HEADSET:
        canvas.create_arc(cx - 9 * s, cy - 9 * s, cx + 9 * s, cy + 9 * s,
                          start=20, extent=140, style="arc",
                          outline=color, width=1.8 * s)
        canvas.create_rectangle(cx - 9 * s, cy - 1 * s, cx - 5 * s, cy + 6 * s,
                                outline=color, width=1.5 * s)
        canvas.create_rectangle(cx + 5 * s, cy - 1 * s, cx + 9 * s, cy + 6 * s,
                                outline=color, width=1.5 * s)
    else:
        canvas.create_rectangle(cx - 8 * s, cy - 9 * s, cx + 8 * s, cy + 9 * s,
                                outline=color, width=1.7 * s)
        canvas.create_oval(cx - 3.2 * s, cy - 4 * s, cx + 3.2 * s, cy + 2.5 * s,
                           outline=color, width=1.4 * s)
        line(cx - 2 * s, cy + 6 * s, cx + 2 * s, cy + 6 * s, width=1.4)


def _truncate(text: str, font: tkfont.Font, width: int) -> str:
    if width <= 0:
        return ""
    if font.measure(text) <= width:
        return text
    ellipsis = "…"
    while text and font.measure(text + ellipsis) > width:
        text = text[:-1]
    return text + ellipsis


class PillButton(tk.Canvas):
    """Flat rounded button drawn on a canvas (Tk labels cannot be rounded)."""

    def __init__(self, parent: tk.Misc, text: str, command, font: tkfont.Font,
                 scale: float, height: float = 26, variant: str = "default"):
        h = int(round(height * scale))
        w = font.measure(text) + int(round(26 * scale))
        super().__init__(parent, width=w, height=h, bg=BG,
                         highlightthickness=0, bd=0, cursor="hand2")
        self._text = text
        self._font = font
        self._command = command
        self._variant = variant
        self._radius = (h - 2) / 2
        self._hover = False
        self._active = False
        self.bind("<Button-1>", lambda _e: self._command())
        self.bind("<Enter>", lambda _e: self._set_hover(True))
        self.bind("<Leave>", lambda _e: self._set_hover(False))
        self._draw()

    def _set_hover(self, value: bool) -> None:
        self._hover = value
        self._draw()

    def set_active(self, value: bool) -> None:
        if self._active != bool(value):
            self._active = bool(value)
            self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = int(self["width"])
        height = int(self["height"])
        if self._variant == "primary":
            fill = "#719dff" if self._hover else ACCENT
            fg = "#0b1020"
        elif self._variant == "ghost":
            fill = SURFACE_2 if self._hover else SURFACE
            fg = TEXT if self._hover else MUTED
        elif self._active:
            fill, fg = ACCENT_SOFT, ACCENT
        elif self._hover:
            fill, fg = SURFACE_2, TEXT
        else:
            fill, fg = SURFACE, MUTED
        _round_rect(self, 1, 1, width - 1, height - 1, self._radius,
                    fill=fill, outline="")
        self.create_text(width / 2, height / 2, text=self._text, fill=fg,
                         font=self._font)


class RoundedBanner(tk.Canvas):
    """Full-width rounded strip used for the low battery warning."""

    def __init__(self, parent: tk.Misc, font: tkfont.Font, scale: float):
        super().__init__(parent, height=int(round(36 * scale)), bg=BG,
                         highlightthickness=0, bd=0)
        self._font = font
        self._text = ""
        self._scale = scale
        self.bind("<Configure>", lambda _e: self._draw())

    def set_text(self, text: str) -> None:
        self._text = text
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        width = self.winfo_width()
        height = self.winfo_height()
        if width <= 2 or not self._text:
            return
        pad = int(round(14 * self._scale))
        _round_rect(self, 1, 1, width - 1, height - 1, (height - 2) / 2,
                    fill=WARN_SOFT, outline="")
        self.create_text(pad, height / 2, text=self._text, fill=WARN,
                         font=self._font, anchor="w")


class BatteryFlyout(tk.Toplevel):
    """Compact battery panel anchored above the tray icon."""

    WIDTH = 316
    ROW_H = 52
    HEADER_H = 34
    FOOTER_H = 32

    def __init__(self, app: "BatteryApp"):
        super().__init__(app)
        self.app = app
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=_TRANSPARENT_KEY)
        try:
            self.attributes("-transparentcolor", _TRANSPARENT_KEY)
        except Exception:
            pass
        self.canvas = tk.Canvas(self, bg=_TRANSPARENT_KEY, highlightthickness=0,
                                bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.visible = False
        self.shown_at = 0.0
        self._signature = None
        self._anchor = None
        self._canvas_size = (self.app.px(self.WIDTH), self.app.px(120))
        self.bind("<Escape>", lambda _e: self.hide())

    # -- geometry ---------------------------------------------------------
    def _size(self, count: int) -> tuple[int, int]:
        px = self.app.px
        height = (px(self.HEADER_H) + max(1, count) * px(self.ROW_H)
                  + px(self.FOOTER_H))
        return px(self.WIDTH), height

    def _place(self, anchor) -> None:
        width, height = self._canvas_size
        screen_w = self.winfo_screenwidth()
        if anchor:
            _left, top, right, _bottom = anchor
            x = right - width
            y = top - height - self.app.px(10)
        else:
            x = screen_w - width - self.app.px(40)
            y = self.winfo_screenheight() - height - self.app.px(70)
        x = max(self.app.px(8), min(x, screen_w - width - self.app.px(8)))
        y = max(self.app.px(8), y)
        self.geometry("%dx%d+%d+%d" % (width + 2, height + 2, x, y))

    # -- content ----------------------------------------------------------
    def show(self, devices: list[Device], anchor) -> None:
        self._anchor = anchor
        self._render(devices)
        self.deiconify()
        self._place(anchor)
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass
        self.visible = True
        self.shown_at = time.time()

    def hide(self) -> None:
        if self.visible:
            self.visible = False
            self.withdraw()

    def refresh(self, devices: list[Device]) -> None:
        if not self.visible:
            return
        if self._signature != self._sign(devices):
            self._render(devices)
            self._place(self._anchor)

    @staticmethod
    def _sign(devices: list[Device]) -> tuple:
        return tuple((d.uid, d.percent, d.charging, d.online) for d in devices)

    def _render(self, devices: list[Device]) -> None:
        app = self.app
        px = app.px
        width, height = self._size(len(devices))
        self._canvas_size = (width, height)
        self._signature = self._sign(devices)
        canvas = self.canvas
        canvas.delete("all")
        canvas.configure(width=width, height=height)
        _round_rect(canvas, 0, 0, width, height, px(20), fill=SURFACE,
                    outline=BORDER)

        # header
        canvas.create_text(px(14), px(17), text="电力王", fill=TEXT,
                           font=app.f_name, anchor="w")
        canvas.create_text(width - px(14), px(18),
                           text=time.strftime("%H:%M:%S"), fill=DIM,
                           font=app.f_tiny, anchor="e")
        canvas.create_line(px(12), px(self.HEADER_H), width - px(12),
                           px(self.HEADER_H), fill=BORDER)

        if not devices:
            canvas.create_text(width / 2, px(self.HEADER_H) + px(28),
                               text="没有检测到无线外设", fill=MUTED,
                               font=app.f_body)
        row_h = px(self.ROW_H)
        for index, device in enumerate(devices[:6]):
            top = px(self.HEADER_H) + index * row_h
            if index:
                canvas.create_line(px(50), top, width - px(14), top,
                                   fill='#1e2532')
            self._draw_row(canvas, device, width, top, row_h)

        footer_y = height - px(self.FOOTER_H)
        canvas.create_line(px(12), footer_y, width - px(12), footer_y,
                           fill=BORDER)
        canvas.create_text(px(14), footer_y + px(16), text="打开主窗口",
                           fill=ACCENT, font=app.f_small, anchor="w",
                           tags="open")
        canvas.create_text(width - px(14), footer_y + px(16), text="刷新",
                           fill=MUTED, font=app.f_small, anchor="e",
                           tags="refresh")
        for tag in ("open", "refresh"):
            canvas.tag_bind(tag, "<Button-1>", self._on_footer)
        canvas.tag_bind("open", "<Enter>",
                        lambda _e: canvas.configure(cursor="hand2"))
        canvas.tag_bind("refresh", "<Enter>",
                        lambda _e: canvas.configure(cursor="hand2"))
        canvas.tag_bind("open", "<Leave>",
                        lambda _e: canvas.configure(cursor=""))
        canvas.tag_bind("refresh", "<Leave>",
                        lambda _e: canvas.configure(cursor=""))

    def _draw_row(self, canvas: tk.Canvas, device: Device, width: int,
                  top: int, row_h: int) -> None:
        app = self.app
        px = app.px
        mid = top + row_h / 2
        canvas.create_oval(px(12), mid - px(14), px(40), mid + px(14),
                           fill="#1c2436" if device.online else "#191d25",
                           outline="")
        draw_icon(canvas, device.kind, px(26), mid, 0.60 * app.scale,
                  ACCENT if device.online else DIM)
        name = _truncate(device.name, app.f_body, width - px(132))
        canvas.create_text(px(50), top + px(17), text=name,
                           fill=TEXT if device.online else MUTED,
                           font=app.f_body, anchor="w")
        percent = "—" if device.percent is None else f"{device.percent}%"
        canvas.create_text(width - px(14), top + px(18), text=percent,
                           fill=device.level_color, font=app.f_pct_small,
                           anchor="e")
        canvas.create_text(px(50), top + px(35),
                           text=self.app._status_text(device), fill=DIM,
                           font=app.f_tiny, anchor="w")
        if device.percent is not None:
            bar_x1, bar_y = px(50), top + px(45)
            bar_x2 = width - px(14)
            bar_h = px(5)
            _round_rect(canvas, bar_x1, bar_y, bar_x2, bar_y + bar_h,
                        bar_h / 2, fill=TRACK, outline="")
            filled = (bar_x2 - bar_x1) * max(0, min(100, device.percent)) / 100
            if filled > bar_h:
                _round_rect(canvas, bar_x1, bar_y, bar_x1 + filled,
                            bar_y + bar_h, bar_h / 2,
                            fill=device.level_color, outline="")

    def _on_footer(self, event) -> None:
        tags = self.canvas.gettags("current")
        if "open" in tags:
            self.hide()
            self.app._show_main_window()
        elif "refresh" in tags:
            self.app.monitor.refresh_now()
            self.hide()


class BatteryApp(tk.Tk):
    def __init__(self, monitor: Monitor, config: Config):
        super().__init__()
        self.monitor = monitor
        self.config = config
        self._cards: list[tk.Widget] = []
        self._last_devices: list[Device] = []
        self._alert_text: str | None = None
        self._alert_until = 0.0
        self._mini = bool(config.mini_mode)
        self._signature = None
        self._uid_signature = None
        self._mini_rendered = None

        self.title(APP_TITLE)
        self.configure(bg=BG)
        self.scale = max(1.0, self.winfo_fpixels("1i") / 96.0)
        self.tk.call("tk", "scaling", self.scale * 96.0 / 72.0)
        self._init_fonts()
        self._set_icon()
        self.minsize(self.px(320), self.px(210))

        self._build()
        self._apply_geometry()
        self.attributes("-topmost", bool(config.always_on_top))
        self.after(120, lambda: _style_window(self))

        self.config.autostart = shell.autostart_enabled()
        self._tray_queue: queue.Queue[str] = queue.Queue()
        self.tray = tray_module.TrayIcon(self._tray_queue.put)
        self._tray_ready = self.tray.start()
        self._tray_hint_shown = False
        self.flyout: BatteryFlyout | None = None
        self.alert_popup: LowBatteryPopup | None = None

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(300, self._tick)
        self.after(400, self._flyout_watch)
        self.bind("<F5>", lambda _e: self.monitor.refresh_now())

    def report_callback_exception(self, exc, value, tb):
        _log_exception(exc, value, tb)

    def px(self, value: float) -> int:
        return int(round(value * self.scale))

    # -- setup ------------------------------------------------------------
    def _set_icon(self) -> None:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "assets", "app.ico")
        if os.path.exists(path):
            try:
                self.iconbitmap(path)
            except Exception:
                pass

    def _init_fonts(self) -> None:
        family = "Microsoft YaHei UI"
        available = set(tkfont.families(self))
        if family not in available:
            family = ("Microsoft YaHei" if "Microsoft YaHei" in available
                      else "Segoe UI")
        self.f_title = tkfont.Font(family=family, size=12, weight="bold")
        self.f_name = tkfont.Font(family=family, size=10, weight="bold")
        self.f_body = tkfont.Font(family=family, size=9)
        self.f_small = tkfont.Font(family=family, size=8)
        self.f_tiny = tkfont.Font(family=family, size=7)
        self.f_pct = tkfont.Font(family="Segoe UI", size=19, weight="bold")
        self.f_pct_small = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        self.f_btn = tkfont.Font(family=family, size=9)

    def _apply_geometry(self) -> None:
        w, h = self.px(500), self.px(340)
        if self.config.window_x >= 0 and self.config.window_y >= 0:
            self.geometry(f"{w}x{h}+{self.config.window_x}+{self.config.window_y}")
        else:
            x = max(0, self.winfo_screenwidth() - w - self.px(60))
            self.geometry(f"{w}x{h}+{x}+{self.px(110)}")

    def _build(self) -> None:
        self.header = tk.Frame(self, bg=BG)
        self.header.pack(fill="x", padx=self.px(16), pady=(self.px(14), self.px(8)))

        title_box = tk.Frame(self.header, bg=BG)
        title_box.pack(side="left")
        self.title_label = tk.Label(title_box, text=APP_TITLE, bg=BG, fg=TEXT,
                                    font=self.f_title, anchor="w", pady=0)
        self.title_label.pack(anchor="w")
        self.subtitle = tk.Label(title_box, text="正在扫描…", bg=BG, fg=MUTED,
                                 font=self.f_small, anchor="w")
        self.subtitle.pack(anchor="w", pady=(self.px(2), 0))

        buttons = tk.Frame(self.header, bg=BG)
        buttons.pack(side="right", pady=(self.px(4), 0))
        self.btn_pin = PillButton(buttons, "置顶", self._toggle_pin,
                                  self.f_btn, self.scale)
        self.btn_mini = PillButton(buttons, "简洁", self._toggle_mini,
                                   self.f_btn, self.scale)
        self.btn_refresh = PillButton(buttons, "刷新", self._refresh_clicked,
                                      self.f_btn, self.scale)
        self.btn_settings = PillButton(buttons, "设置", self._open_settings,
                                       self.f_btn, self.scale)
        for btn in (self.btn_settings, self.btn_refresh, self.btn_mini, self.btn_pin):
            btn.pack(side="right", padx=(self.px(6), 0))

        self.alert = RoundedBanner(self, self.f_body, self.scale)

        # footer is packed before the body: the body expands and would
        # otherwise take away the footer's space
        self.footer = tk.Frame(self, bg=BG)
        self.footer.pack(side="bottom", fill="x", padx=self.px(16),
                         pady=(self.px(6), self.px(10)))
        self.status = tk.Label(self.footer, text="", bg=BG, fg=DIM,
                               font=self.f_tiny, anchor="w")
        self.status.pack(side="left")
        # 小水印：右下角，颜色刻意压得很低，不影响读数
        self.watermark = tk.Label(self.footer, text="by:himlaya", bg=BG,
                                  fg="#39424f", font=self.f_tiny, anchor="e")
        self.watermark.pack(side="right", padx=(self.px(10), 0))
        self.error_label = tk.Label(self.footer, text="", bg=BG, fg="#ff7a7a",
                                    font=self.f_tiny, anchor="e")
        self.error_label.pack(side="right")

        self.body = tk.Frame(self, bg=BG)
        self.body.pack(side="top", fill="both", expand=True,
                       padx=self.px(12))
        self.canvas = tk.Canvas(self.body, bg=BG, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, bg=BG)
        self._inner_id = self.canvas.create_window((0, 0), window=self.inner,
                                                   anchor="nw")
        self._init_scrollbar()
        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.inner)

    def _init_scrollbar(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("Dark.Vertical.TScrollbar", troughcolor=BG,
                        background="#2c3644", bordercolor=BG,
                        darkcolor="#2c3644", lightcolor="#2c3644",
                        arrowcolor=BG, width=self.px(8),
                        relief="flat", arrowsize=self.px(5),
                        gripcount=0)
        self.scrollbar = ttk.Scrollbar(self.body, orient="vertical",
                                       command=self.canvas.yview,
                                       style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self._scrollbar_visible = False

    def _make_button(self, parent, text, command):  # kept for compatibility
        return PillButton(parent, text, command, self.f_btn, self.scale)

    def _update_button_states(self) -> None:
        self.btn_pin.set_active(bool(self.config.always_on_top))
        self.btn_mini.set_active(bool(self._mini))

    def _bind_wheel(self, widget) -> None:
        widget.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event) -> None:
        if self.canvas.bbox("all") and \
                self.canvas.bbox("all")[3] > self.canvas.winfo_height():
            self.canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_inner_configure(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self._sync_scrollbar()

    def _on_canvas_configure(self, event) -> None:
        self.canvas.itemconfigure(self._inner_id, width=event.width)
        for card in self._cards:
            try:
                card.configure(width=max(self.px(300), event.width - self.px(6)))
            except Exception:
                pass
        self._sync_scrollbar()

    def _sync_scrollbar(self) -> None:
        bbox = self.canvas.bbox("all")
        needs = bool(bbox) and bbox[3] > self.canvas.winfo_height() + 2
        if needs and not self._scrollbar_visible:
            self.scrollbar.pack(side="right", fill="y", padx=(self.px(4), 0))
            self._scrollbar_visible = True
        elif not needs and self._scrollbar_visible:
            self.scrollbar.pack_forget()
            self._scrollbar_visible = False

    # -- rendering --------------------------------------------------------
    def _tick(self) -> None:
        devices, last_scan, error, scanning = self.monitor.snapshot()
        self._render(devices, last_scan, error, scanning)
        alerts = self.monitor.pop_alerts()
        if alerts:
            self._alert_text = f"⚠  {alerts[0][0]} 电量仅剩 {alerts[0][1]}%"
            self._alert_until = time.time() + 8
            # window hidden in the tray: also bubble it through the shell
            if self._tray_ready and self.state() != "normal":
                self.tray.notify(f"{alerts[0][0]} 电量仅剩 {alerts[0][1]}%",
                                 "低电量提醒")
            self._show_alert_popup(alerts)
        self._update_alert()
        self._drain_tray_commands()
        if (self.flyout and self.flyout.winfo_exists()
                and self.flyout.visible):
            self.flyout.refresh(devices)
        if self._tray_ready:
            self.tray.update(devices, self.config.always_on_top,
                             self.config.autostart)
        self.after(1000, self._tick)

    def _drain_tray_commands(self) -> None:
        while True:
            try:
                command = self._tray_queue.get_nowait()
            except queue.Empty:
                return
            if command == "popup":
                self._toggle_flyout()
            elif command == "show":
                self._show_main_window()
            elif command == "toggle":
                self._toggle_window()
            elif command == "refresh":
                self._refresh_clicked()
            elif command == "pin":
                self._toggle_pin()
            elif command == "autostart":
                self.config.autostart = shell.set_autostart(
                    not self.config.autostart)
                self.config.save()
            elif command == "quit":
                self._quit()

    def _toggle_flyout(self) -> None:
        """Left click on the tray icon: battery panel, no main window."""
        now = time.time()
        if now - getattr(self, "_last_popup_ts", 0.0) < 0.35:
            return  # ignore the second half of a double click
        self._last_popup_ts = now
        if self.flyout is None or not self.flyout.winfo_exists():
            try:
                self.flyout = BatteryFlyout(self)
            except Exception:
                return
        if self.flyout is None:
            return
        if self.flyout.visible:
            self.flyout.hide()
            return
        devices, _ts, _err, _scanning = self.monitor.snapshot()
        if not self.config.show_unsupported:
            devices = [d for d in devices if d.has_battery]
        anchor = None
        if self._tray_ready:
            try:
                anchor = self.tray.icon_rect()
            except Exception:
                anchor = None
        self.flyout.show(devices, anchor)

    def _show_alert_popup(self, alerts: list[tuple[str, int]]) -> None:
        """Popup next to the tray icon; never steals keyboard focus."""
        if not self.config.notify_low_battery or not self.config.alert_popup:
            return
        if self.flyout and self.flyout.winfo_exists() and self.flyout.visible:
            self.flyout.hide()
        if self.alert_popup is None or not self.alert_popup.winfo_exists():
            try:
                self.alert_popup = LowBatteryPopup(self)
            except Exception:
                self.alert_popup = None
                return
        anchor = None
        if self._tray_ready:
            try:
                anchor = self.tray.icon_rect()
            except Exception:
                anchor = None
        try:
            self.alert_popup.show(alerts, anchor)
        except Exception:
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass

    def _show_main_window(self) -> None:
        if self.flyout:
            self.flyout.hide()
        if self.state() == "withdrawn":
            self.deiconify()
        self.lift()
        try:
            self.focus_force()
        except Exception:
            pass

    def _flyout_watch(self) -> None:
        """Hide the panel when the user clicks anywhere outside it."""
        try:
            flyout = self.flyout
            if (flyout and flyout.winfo_exists() and flyout.visible
                    and time.time() - flyout.shown_at > 0.25):
                user32 = ctypes.windll.user32
                if user32.GetAsyncKeyState(0x01) & 0x8000:  # left button down
                    point = wintypes.POINT()
                    user32.GetCursorPos(ctypes.byref(point))
                    left, top = flyout.winfo_x(), flyout.winfo_y()
                    right = left + flyout.winfo_width()
                    bottom = top + flyout.winfo_height()
                    inside = (left <= point.x <= right
                              and top <= point.y <= bottom)
                    anchor = flyout._anchor
                    on_icon = bool(anchor) and (
                        anchor[0] <= point.x <= anchor[2]
                        and anchor[1] <= point.y <= anchor[3])
                    # the taskbar strip holds the tray icon: clicks there are
                    # handled by the icon itself, not by 'click outside'
                    on_taskbar = point.y >= self.winfo_screenheight() - self.px(60)
                    if not inside and not on_icon and not on_taskbar:
                        flyout.hide()
        except Exception:
            pass
        self.after(150, self._flyout_watch)

    def _toggle_window(self) -> None:
        if self.state() == "withdrawn":
            self.deiconify()
            self.lift()
            try:
                self.focus_force()
            except Exception:
                pass
        else:
            self.withdraw()

    def _update_alert(self) -> None:
        if self._alert_text and time.time() < self._alert_until:
            self.alert.set_text(self._alert_text)
            if not self.alert.winfo_ismapped():
                self.alert.pack(fill="x", padx=self.px(14),
                                pady=(0, self.px(8)), before=self.body)
        else:
            self._alert_text = None
            if self.alert.winfo_ismapped():
                self.alert.pack_forget()

    def _render(self, devices: list[Device], last_scan: float,
                error: str, scanning: bool) -> None:
        if not self.config.show_unsupported:
            devices = [d for d in devices if d.has_battery]
        self._last_devices = devices

        online = [d for d in devices if d.online]
        if online:
            self.subtitle.configure(text=f"{len(online)} 个设备已连接")
        elif devices:
            self.subtitle.configure(text="设备已断开")
        else:
            self.subtitle.configure(text="未发现无线设备")

        self.btn_pin.set_active(bool(self.config.always_on_top))
        self.btn_mini.set_active(bool(self._mini))

        signature = tuple((d.uid, d.percent, d.charging, d.online, d.name)
                          for d in devices)
        uid_signature = tuple(d.uid for d in devices)
        if (signature != self._signature or self._mini != self._mini_rendered
                or uid_signature != self._uid_signature):
            self._signature = signature
            self._mini_rendered = self._mini
            self._rebuild_cards(devices, uid_signature)

        self.error_label.configure(text="读取异常" if error else "")
        if last_scan:
            stamp = time.strftime("%H:%M:%S", time.localtime(last_scan))
            self.status.configure(
                text=f"每 {self.config.interval_seconds} 秒刷新 · 上次 {stamp}"
                     + (" · 扫描中…" if scanning else ""))

    def _rebuild_cards(self, devices: list[Device], uid_signature) -> None:
        for widget in self._cards:
            widget.destroy()
        self._cards = []
        width = max(self.px(300), self.canvas.winfo_width() - self.px(6))
        if not devices:
            self._make_empty_state()
        else:
            for device in devices:
                card = self._make_card(device, width)
                card.pack(fill="x", padx=self.px(4), pady=self.px(7))
                self._cards.append(card)
        if uid_signature != self._uid_signature:
            self._uid_signature = uid_signature
            self._autosize()
        self.canvas.yview_moveto(0)
        self.after(30, self._sync_scrollbar)

    def _autosize(self) -> None:
        """Fit the window to its content, within the screen limit."""
        self.update_idletasks()
        header_h = self.header.winfo_reqheight()
        cards_h = self.inner.winfo_reqheight()
        # the footer text is filled in after the cards, so give it a floor
        footer_h = max(self.footer.winfo_reqheight(), self.px(22))
        alert_h = self.alert.winfo_reqheight() if self.alert.winfo_ismapped() else 0
        chrome = self.px(14 + 8) + self.px(6 + 10) + self.px(6)
        height = header_h + cards_h + footer_h + alert_h + chrome
        width = self.px(340) if self._mini else self.px(500)
        max_height = self.winfo_screenheight() - self.px(110)
        height = max(self.px(200), min(height, max_height))
        self.geometry(f"{width}x{height}")
        # pack() gives leftover space to the body first, so measure what the
        # footer actually needs and grow by the difference if it got squeezed
        self.update_idletasks()
        needed = (self.footer.winfo_y() + self.footer.winfo_reqheight()
                  + self.px(10))
        if self.winfo_height() < needed and needed <= max_height:
            self.geometry(f"{width}x{min(needed, max_height)}")

    def _make_empty_state(self) -> None:
        holder = tk.Frame(self.inner, bg=BG)
        holder.pack(fill="both", expand=True, pady=self.px(30))
        canvas = tk.Canvas(holder, bg=BG, highlightthickness=0,
                           height=self.px(150), width=self.px(300))
        canvas.pack()
        s = self.scale
        cx, cy = self.px(150), self.px(58)
        # wireless "searching" glyph: dot plus two radiating arcs
        canvas.create_oval(cx - 3 * s, cy + 6 * s, cx + 3 * s, cy + 12 * s,
                           outline="", fill=DIM)
        for radius in (14, 26):
            canvas.create_arc(cx - radius * s, cy + 9 * s - radius * s,
                              cx + radius * s, cy + 9 * s + radius * s,
                              start=45, extent=90, style="arc",
                              outline=DIM, width=2 * s)
        canvas.create_text(self.px(150), self.px(100), text="没有检测到无线外设",
                           fill=MUTED, font=self.f_body)
        canvas.create_text(self.px(150), self.px(122),
                           text="连接鼠标 / 键盘 / 手柄后会自动出现",
                           fill=DIM, font=self.f_small)
        self._cards.append(holder)

    @staticmethod
    def _status_text(device: Device) -> str:
        if not device.online:
            return "已断开"
        if device.percent is None:
            return "不支持读取"
        if device.charging:
            return "⚡ 充电中"
        return "放电中"

    @staticmethod
    def _status_colors(device: Device) -> tuple[str, str]:
        """(text, background) for the charge state pill."""
        if not device.online:
            return "#ff8a80", "#2a1d1d"
        if device.percent is None:
            return "#6b7688", "#1a2029"
        if device.charging:
            return "#4ce0b0", "#12332a"
        return "#9aa6b8", "#212a38"

    def _make_card(self, device: Device, width: int) -> tk.Widget:
        if self._mini:
            return self._make_mini_card(device, width)
        height = self.px(118)
        canvas = tk.Canvas(self.inner, bg=BG, highlightthickness=0, bd=0,
                           height=height, width=width, cursor="hand2")
        canvas.device = device
        canvas.mini = False
        canvas.fixed_height = height
        canvas.bind("<Configure>", self._on_card_configure)
        canvas.bind("<Enter>",
                    lambda _e: self._hover(canvas, device, canvas.winfo_width(),
                                           height, True))
        canvas.bind("<Leave>",
                    lambda _e: self._hover(canvas, device, canvas.winfo_width(),
                                           height, False))
        canvas.bind("<Button-1>", lambda _e: self._copy_device(device))
        self._bind_wheel(canvas)
        self._draw_card(canvas, device, max(width, 1), height)
        return canvas

    def _on_card_configure(self, event) -> None:
        """Redraw whenever the card changes size (window resize, mini mode)."""
        canvas = event.widget
        device = getattr(canvas, "device", None)
        if device is None or event.width <= 1:
            return
        height = getattr(canvas, "fixed_height", event.height)
        if getattr(canvas, "mini", False):
            self._draw_mini_card(canvas, device, event.width, height)
        else:
            self._draw_card(canvas, device, event.width, height)

    def _hover(self, canvas: tk.Canvas, device: Device, width: int,
               height: int, entering: bool) -> None:
        canvas.delete("bgshape")
        _round_rect(canvas, 1, 1, width - 1, height - 1, self.px(RADIUS_CARD),
                    fill=CARD_HOVER if entering else SURFACE, outline="",
                    tags="bgshape")
        canvas.tag_lower("bgshape")

    def _copy_device(self, device: Device) -> None:
        percent = "—" if device.percent is None else f"{device.percent}%"
        self.clipboard_clear()
        self.clipboard_append(f"{device.name}  {percent}  {device.link}")

    def _make_mini_card(self, device: Device, width: int) -> tk.Widget:
        height = self.px(40)
        canvas = tk.Canvas(self.inner, bg=BG, highlightthickness=0, bd=0,
                           height=height, width=width, cursor="hand2")
        canvas.device = device
        canvas.mini = True
        canvas.fixed_height = height
        canvas.bind("<Configure>", self._on_card_configure)
        canvas.bind("<Button-1>", lambda _e: self._copy_device(device))
        self._bind_wheel(canvas)
        self._draw_mini_card(canvas, device, max(width, 1), height)
        return canvas

    def _draw_mini_card(self, canvas: tk.Canvas, device: Device, width: int,
                        height: int) -> None:
        canvas.delete("all")
        _round_rect(canvas, 1, 1, width - 1, height - 1, (height - 2) / 2,
                    fill=SURFACE, outline="")
        draw_icon(canvas, device.kind, self.px(22), height / 2,
                  0.58 * self.scale, MUTED if not device.online else ACCENT)
        percent = "—" if device.percent is None else f"{device.percent}%"
        name = _truncate(device.name, self.f_body,
                         max(self.px(60), width - self.px(150)))
        canvas.create_text(self.px(40), height / 2, text=name, fill=TEXT,
                           font=self.f_body, anchor="w")
        if device.charging:
            canvas.create_text(width - self.px(74), height / 2, text="⚡",
                               fill=device.level_color, font=self.f_small,
                               anchor="e")
        canvas.create_text(width - self.px(14), height / 2, text=percent,
                           fill=device.level_color, font=self.f_pct_small,
                           anchor="e")

    def _draw_card(self, canvas: tk.Canvas, device: Device, width: int,
                   height: int) -> None:
        canvas.delete("all")
        _round_rect(canvas, 1, 1, width - 1, height - 1, self.px(RADIUS_CARD),
                    fill=SURFACE, outline="", tags="bgshape")

        # icon: soft circular chip, flat fill, no stroke
        chip_fill = "#1c2436" if device.online else "#191d25"
        canvas.create_oval(self.px(16), self.px(25), self.px(62), self.px(71),
                           fill=chip_fill, outline="")
        draw_icon(canvas, device.kind, self.px(39), self.px(48),
                  0.98 * self.scale, ACCENT if device.online else DIM)

        # name + meta
        right_reserved = self.px(96)
        name = _truncate(device.name, self.f_name,
                         max(self.px(60), width - self.px(74) - right_reserved))
        canvas.create_text(self.px(74), self.px(37), text=name,
                           fill=TEXT if device.online else MUTED,
                           font=self.f_name, anchor="w")

        # charge state pill geometry (drawn after the percentage, but the
        # detail text has to stay clear of it)
        status = self._status_text(device)
        status_fg, status_bg = self._status_colors(device)
        pill_h = self.px(20)
        pill_w = self.f_small.measure(status) + self.px(18)
        pill_x2 = width - self.px(18)
        pill_x1 = pill_x2 - pill_w
        pill_y1 = self.px(53)

        link = device.link or "无线"
        badge_w = self.f_small.measure(link) + self.px(16)
        _round_rect(canvas, self.px(74), self.px(49),
                    self.px(74) + badge_w, self.px(65), self.px(8),
                    fill="#1c2638", outline="")
        canvas.create_text(self.px(74) + badge_w / 2, self.px(57), text=link,
                           fill="#8fb0ff", font=self.f_small)

        detail_x = self.px(74) + badge_w + self.px(9)
        detail_max = max(self.px(20), pill_x1 - self.px(10) - detail_x)
        detail = _truncate(device.detail or "", self.f_tiny, detail_max)
        canvas.create_text(detail_x, self.px(57), text=detail, fill=DIM,
                           font=self.f_tiny, anchor="w")

        # percentage
        if device.percent is None:
            pct_text, pct_color = "—", DIM
        else:
            pct_text, pct_color = f"{device.percent}%", device.level_color
        canvas.create_text(width - self.px(18), self.px(37), text=pct_text,
                           fill=pct_color, font=self.f_pct, anchor="e")

        # charge state pill: 充电中 / 放电中 / 已断开 / 不支持读取
        _round_rect(canvas, pill_x1, pill_y1, pill_x2, pill_y1 + pill_h,
                    pill_h / 2, fill=status_bg, outline="")
        canvas.create_text((pill_x1 + pill_x2) / 2, pill_y1 + pill_h / 2,
                           text=status, fill=status_fg, font=self.f_small)

        # battery bar, or an explicit note when the device cannot report one
        bar_x1, bar_y1 = self.px(74), self.px(86)
        bar_x2 = width - self.px(18)
        bar_h = self.px(10)
        if device.voltage_mv:
            bar_x2 -= self.px(58)
        if device.percent is None:
            canvas.create_text(bar_x1, bar_y1 + bar_h / 2,
                               text="未获取到电量数据（该设备不提供电量上报）",
                               fill="#7b8698", font=self.f_small, anchor="w")
        else:
            _round_rect(canvas, bar_x1, bar_y1, bar_x2, bar_y1 + bar_h,
                        bar_h / 2, fill=TRACK, outline="")
            fill_w = (bar_x2 - bar_x1) * max(0, min(100, device.percent)) / 100
            if fill_w > bar_h:
                _round_rect(canvas, bar_x1, bar_y1, bar_x1 + fill_w,
                            bar_y1 + bar_h, bar_h / 2, fill=pct_color,
                            outline="")
        if device.voltage_mv:
            canvas.create_text(width - self.px(18), self.px(91),
                               text=f"{device.voltage_mv / 1000:.2f} V",
                               fill=MUTED, font=self.f_small, anchor="e")

    # -- actions ----------------------------------------------------------
    def _refresh_clicked(self) -> None:
        self.monitor.refresh_now()
        self.btn_refresh.set_active(True)
        self.after(700, lambda: self.btn_refresh.set_active(False))

    def _toggle_pin(self) -> None:
        self.config.always_on_top = not self.config.always_on_top
        self.attributes("-topmost", self.config.always_on_top)
        self.btn_pin.set_active(self.config.always_on_top)
        self.config.save()

    def _toggle_mini(self) -> None:
        self._mini = not self._mini
        self.config.mini_mode = self._mini
        self.config.save()
        self.title("电力王 · 简洁" if self._mini else APP_TITLE)
        self._uid_signature = None
        self._signature = None
        self._render(self._last_devices, self.monitor.snapshot()[1],
                     self.monitor.snapshot()[2], False)

    def _open_settings(self) -> None:
        SettingsDialog(self, self.config, on_save=self._settings_saved)

    def _settings_saved(self) -> None:
        self.config.save()
        self._signature = None
        self.monitor.refresh_now()

    def _on_close(self) -> None:
        if self._tray_ready and self.config.close_to_tray:
            self._save_geometry()
            self.withdraw()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify("已最小化到托盘，双击图标恢复窗口",
                                 "电力王")
            return
        self._quit()

    def _save_geometry(self) -> None:
        try:
            self.config.window_x = self.winfo_x()
            self.config.window_y = self.winfo_y()
        except Exception:
            pass
        self.config.save()

    def _quit(self) -> None:
        self._save_geometry()
        self.monitor.stop()
        if self._tray_ready:
            self.tray.stop()
        self.destroy()


class ToggleRow(tk.Frame):
    """Label + pill switch, drawn by hand so it matches the dark theme."""

    def __init__(self, parent: tk.Misc, text: str, value: bool,
                 font: tkfont.Font, scale: float, on_change=None):
        super().__init__(parent, bg=BG)
        self.value = value
        self.scale = scale
        self.on_change = on_change
        self.label = tk.Label(self, text=text, bg=BG, fg=TEXT, font=font,
                              anchor="w")
        self.label.pack(side="left", fill="x", expand=True)
        w, h = int(34 * scale), int(18 * scale)
        self.canvas = tk.Canvas(self, bg=BG, width=w, height=h,
                                highlightthickness=0, cursor="hand2")
        self.canvas.pack(side="right", padx=(int(10 * scale), 0))
        self.canvas.bind("<Button-1>", self._toggle)
        self.label.bind("<Button-1>", self._toggle)
        self.w, self.h = w, h
        self._draw()

    def _draw(self) -> None:
        c, w, h = self.canvas, self.w, self.h
        c.delete("all")
        radius = h / 2
        color = ACCENT if self.value else "#2c3644"
        _round_rect(c, 1, 1, w - 1, h - 1, radius, fill=color, outline="")
        knob = h - 6
        x = (w - knob - 3) if self.value else 3
        c.create_oval(x, 3, x + knob, 3 + knob, fill="#0b1020" if self.value
                      else "#8d98a9", outline="")

    def _toggle(self, _event=None) -> None:
        self.value = not self.value
        self._draw()
        if self.on_change:
            self.on_change(self.value)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: BatteryApp, config: Config, on_save):
        super().__init__(parent)
        self.config = config
        self.on_save = on_save
        self.title("设置")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.after(80, lambda: _style_window(self))
        scale = parent.scale
        pad = parent.px(20)

        style = ttk.Style(self)
        style.configure("Dark.TCombobox", fieldbackground=CARD,
                        background=CARD, foreground=TEXT, arrowcolor=MUTED,
                        bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD,
                        selectbackground=CARD, selectforeground=TEXT,
                        insertcolor=TEXT, padding=parent.px(4))
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", CARD)],
                  foreground=[("readonly", TEXT)],
                  background=[("readonly", CARD)],
                  selectbackground=[("readonly", CARD)],
                  selectforeground=[("readonly", TEXT)],
                  bordercolor=[("focus", BORDER)])
        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#0b1020")
        self.option_add("*TCombobox*Listbox.font", parent.f_body)

        body = tk.Frame(self, bg=BG, padx=pad, pady=parent.px(14))
        body.pack(fill="both", expand=True)
        body.grid_columnconfigure(1, weight=1)

        tk.Label(body, text="刷新间隔", bg=BG, fg=MUTED,
                 font=parent.f_body).grid(row=0, column=0, sticky="w",
                                          pady=parent.px(6))
        self.interval = tk.StringVar(value=str(config.interval_seconds))
        ttk.Combobox(body, textvariable=self.interval, width=8,
                     style="Dark.TCombobox", state="readonly",
                     values=("15", "30", "60", "120", "300")).grid(
            row=0, column=1, sticky="e", pady=parent.px(6))

        tk.Label(body, text="低电量阈值", bg=BG, fg=MUTED,
                 font=parent.f_body).grid(row=1, column=0, sticky="w",
                                          pady=parent.px(6))
        self.threshold = tk.StringVar(value=str(config.low_battery_percent))
        ttk.Combobox(body, textvariable=self.threshold, width=8,
                     style="Dark.TCombobox", state="readonly",
                     values=("10", "15", "20", "25", "30", "40", "50")).grid(
            row=1, column=1, sticky="e", pady=parent.px(6))

        self.notify = ToggleRow(body, "低电量时在界面提示",
                                bool(config.notify_low_battery),
                                parent.f_body, scale)
        self.notify.grid(row=2, column=0, columnspan=2, sticky="ew",
                         pady=(parent.px(8), parent.px(4)))
        self.show_unsupported = ToggleRow(body, "显示暂不支持读数的设备",
                                          bool(config.show_unsupported),
                                          parent.f_body, scale)
        self.show_unsupported.grid(row=3, column=0, columnspan=2, sticky="ew",
                                   pady=parent.px(4))
        self.autostart = ToggleRow(body, "开机自动启动",
                                   shell.autostart_enabled(),
                                   parent.f_body, scale)
        self.autostart.grid(row=4, column=0, columnspan=2, sticky="ew",
                            pady=parent.px(4))
        self.close_to_tray = ToggleRow(body, "关闭窗口时最小化到托盘",
                                       bool(config.close_to_tray),
                                       parent.f_body, scale)
        self.close_to_tray.grid(row=5, column=0, columnspan=2, sticky="ew",
                                pady=parent.px(4))
        self.alert_popup = ToggleRow(body, "低电量时弹窗提醒",
                                     bool(config.alert_popup),
                                     parent.f_body, scale)
        self.alert_popup.grid(row=6, column=0, columnspan=2, sticky="ew",
                              pady=parent.px(4))

        footer = tk.Frame(body, bg=BG)
        footer.grid(row=7, column=0, columnspan=2, sticky="ew",
                    pady=(parent.px(16), 0))
        save = PillButton(footer, "保存", self._save, parent.f_btn, scale,
                          variant="primary")
        save.pack(side="right")
        cancel = PillButton(footer, "取消", self.destroy, parent.f_btn, scale,
                            variant="ghost")
        cancel.pack(side="right", padx=parent.px(8))

        tk.Label(body, text=f"电力王 v{__version__} · 本地读取，不联网 · by himlaya",
                 bg=BG, fg=DIM, font=parent.f_tiny).grid(
            row=8, column=0, columnspan=2, sticky="w",
            pady=(parent.px(12), 0))

        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + parent.px(80)
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _save(self) -> None:
        try:
            self.config.interval_seconds = max(10, int(self.interval.get()))
        except ValueError:
            pass
        try:
            self.config.low_battery_percent = max(
                1, min(90, int(self.threshold.get())))
        except ValueError:
            pass
        self.config.notify_low_battery = bool(self.notify.value)
        self.config.show_unsupported = bool(self.show_unsupported.value)
        self.config.autostart = shell.set_autostart(bool(self.autostart.value))
        self.config.close_to_tray = bool(self.close_to_tray.value)
        self.config.alert_popup = bool(self.alert_popup.value)
        self.on_save()
        self.destroy()


def main() -> None:
    _enable_dpi_awareness()
    if not shell.acquire_single_instance():
        shell.activate_existing_window()
        return
    sys.excepthook = _log_exception
    config = Config.load()
    monitor = Monitor(config)
    monitor.start()
    app = BatteryApp(monitor, config)
    try:
        app.mainloop()
    finally:
        monitor.stop()
