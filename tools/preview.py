"""UI preview with mock devices (development helper, not part of the app).

    python tools/preview.py            普通模式
    python tools/preview.py --mini     简洁模式
    python tools/preview.py --alert    触发一次低电量横幅
    python tools/preview.py --settings 打开设置窗口
"""

import sys
import time

sys.path.insert(0, ".")

from app.config import Config
from app.model import (KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE,
                       Device)
from app.ui import BatteryApp, _enable_dpi_awareness

ALERTS = [("WH-1000XM5", 15)] if "--alert" in sys.argv else []


class FakeMonitor:
    def __init__(self, devices):
        self.devices = devices
        self._alerts_delivered = False

    def snapshot(self):
        return self.devices, time.time(), "", False

    def pop_alerts(self):
        if ALERTS and not self._alerts_delivered:
            self._alerts_delivered = True
            return ALERTS
        return []

    def refresh_now(self):
        pass

    def stop(self):
        pass


DEVICES = [
    Device(uid="a", name="G502 LIGHTSPEED Wireless Gaming Mouse", kind=KIND_MOUSE,
           link="2.4G", percent=79, charging=False, voltage_mv=3963,
           detail="HID++ 2.0 · 2.4G 接收器", source="HID++"),
    Device(uid="b", name="VGN S99", kind=KIND_KEYBOARD, link="2.4G",
           percent=None, detail="2.4G 接收器 · 未识别协议"),
    Device(uid="c", name="DualSense 无线控制器", kind=KIND_GAMEPAD, link="蓝牙",
           percent=100, charging=True, detail="HID 报告 0x31 · 已充满",
           source="HID"),
    Device(uid="d", name="WH-1000XM5", kind=KIND_HEADSET, link="蓝牙",
           percent=15, charging=False, detail="蓝牙 · 电池服务", source="WinRT"),
    Device(uid="f", name="MX Master 3S", kind=KIND_MOUSE, link="蓝牙",
           percent=44, charging=False, voltage_mv=3810, online=False,
           detail="HID++ 2.0 · 蓝牙", source="HID++"),
]


def main():
    _enable_dpi_awareness()
    config = Config()
    config.window_x = 80
    config.window_y = 80
    config.mini_mode = "--mini" in sys.argv
    devices = [] if "--empty" in sys.argv else DEVICES
    app = BatteryApp(FakeMonitor(devices), config)
    if "--flyout" in sys.argv:
        app.after(1200, app._toggle_flyout)
    if "--alert-popup" in sys.argv:
        app.after(1200, lambda: app._show_alert_popup([("VGN S99", 15), ("G502 LIGHTSPEED", 9)]))
    if "--settings" in sys.argv:
        app.after(900, app._open_settings)
    app.mainloop()


if __name__ == "__main__":
    main()
