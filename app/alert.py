"""Low battery popup window (rounded, compact, never steals focus)."""

from __future__ import annotations

import time
import tkinter as tk

from .model import Device

# any colour outside the drawn card is punched out with a colour key so the
# window really has rounded corners instead of a rectangle
TRANSPARENT_KEY = "#ff00fe"


class LowBatteryPopup(tk.Toplevel):
    """Small alert that appears above the tray icon and auto-dismisses."""

    WIDTH = 296
    BASE_HEIGHT = 100
    LINE_H = 20
    RADIUS = 22
    AUTO_HIDE_MS = 15000

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-transparentcolor", TRANSPARENT_KEY)
        except Exception:
            pass
        self.configure(bg=TRANSPARENT_KEY)
        self.canvas = tk.Canvas(self, bg=TRANSPARENT_KEY, highlightthickness=0,
                                bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.visible = False
        self.shown_at = 0.0
        self._timer = None
        self._alerts: list[tuple[str, int]] = []
        self._anchor = None
        self._size = (app.px(self.WIDTH), app.px(self.BASE_HEIGHT))
        self.bind("<Escape>", lambda _e: self.hide())

    # -- geometry ---------------------------------------------------------
    def _place(self) -> None:
        width, height = self._size
        screen_w = self.winfo_screenwidth()
        anchor = self._anchor
        if anchor:
            _left, top, right, _bottom = anchor
            x = right - width
            y = top - height - self.app.px(10)
        else:
            x = screen_w - width - self.app.px(40)
            y = self.winfo_screenheight() - height - self.app.px(80)
        x = max(self.app.px(8), min(x, screen_w - width - self.app.px(8)))
        y = max(self.app.px(8), y)
        self.geometry("%dx%d+%d+%d" % (width, height, x, y))

    # -- content ----------------------------------------------------------
    def show(self, alerts: list[tuple[str, int]], anchor) -> None:
        self._alerts = alerts[:3]
        self._anchor = anchor
        self._render()
        self.deiconify()
        self._place()
        self.lift()
        self.visible = True
        self.shown_at = time.time()
        if self._timer:
            try:
                self.after_cancel(self._timer)
            except Exception:
                pass
        self._timer = self.after(self.AUTO_HIDE_MS, self.hide)

    def hide(self) -> None:
        if self._timer:
            try:
                self.after_cancel(self._timer)
            except Exception:
                pass
            self._timer = None
        if self.visible:
            self.visible = False
            self.withdraw()

    def _render(self) -> None:
        app = self.app
        px = app.px
        width = px(self.WIDTH)
        height = (px(self.BASE_HEIGHT)
                  + max(0, len(self._alerts) - 1) * px(self.LINE_H))
        self._size = (width, height)
        canvas = self.canvas
        canvas.delete("all")
        canvas.configure(width=width, height=height)

        # rounded card
        _round_rect(canvas, 0, 0, width, height, px(self.RADIUS),
                    fill="#171d27", outline="#3a2f18")

        # warning triangle + title
        cx, cy, r = px(24), px(26), px(9)
        canvas.create_polygon(cx, cy - r, cx + r, cy + r * 0.85,
                              cx - r, cy + r * 0.85, fill="#ffb02e",
                              outline="")
        canvas.create_text(cx, cy + px(1), text="!", fill="#2b1d05",
                           font=app.f_tiny)
        canvas.create_text(px(40), px(26), text="电量不足", fill="#ffc53d",
                           font=app.f_body, anchor="w")

        row_y = px(52)
        for name, percent in self._alerts:
            label = _truncate(f"· {name}", app.f_small, width - px(76))
            canvas.create_text(px(14), row_y, text=label,
                               fill="#e9eef7", font=app.f_small, anchor="w")
            canvas.create_text(width - px(14), row_y, text=f"{percent}%",
                               fill="#ff9558", font=app.f_small, anchor="e")
            row_y += px(self.LINE_H)

        button_y = height - px(14)
        canvas.create_text(width - px(14), button_y, text="打开主窗口",
                           fill="#5b8cff", font=app.f_tiny, anchor="e",
                           tags="open")
        canvas.create_text(width - px(96), button_y, text="知道了",
                           fill="#8d98a9", font=app.f_tiny, anchor="e",
                           tags="dismiss")
        for tag in ("open", "dismiss"):
            canvas.tag_bind(tag, "<Button-1>", self._on_click)
            canvas.tag_bind(tag, "<Enter>",
                            lambda _e: canvas.configure(cursor="hand2"))
            canvas.tag_bind(tag, "<Leave>",
                            lambda _e: canvas.configure(cursor=""))

    def _on_click(self, _event) -> None:
        tags = self.canvas.gettags("current")
        self.hide()
        if "open" in tags:
            self.app._show_main_window()


def _truncate(text: str, font, width: int) -> str:
    if width <= 0:
        return ""
    if font.measure(text) <= width:
        return text
    while text and font.measure(text + "…") > width:
        text = text[:-1]
    return text + "…"


def _round_rect(canvas: tk.Canvas, x1, y1, x2, y2, radius, **kwargs):
    """Rounded rectangle as a smooth polygon (shared with the flyout)."""
    radius = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    points = [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)
