"""电力王 —— 鼠标 / 键盘 / 手柄等无线外设的电量监视器.

双击即可运行（无控制台窗口）。命令行参数：

    PeripheralBattery.pyw           启动图形界面
    PeripheralBattery.pyw --probe   在控制台打印一次扫描结果
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _probe() -> int:
    from app.config import Config
    from app.monitor import Monitor

    monitor = Monitor(Config())
    monitor._scan_once()
    devices, _ts, error, _scanning = monitor.snapshot()
    if error:
        print(f"[warn] {error}")
    if not devices:
        print("没有检测到无线外设。")
        return 1
    for device in devices:
        percent = "—" if device.percent is None else f"{device.percent}%"
        volt = f" {device.voltage_mv} mV" if device.voltage_mv else ""
        print(f"{device.name}\n"
              f"    类型: {device.kind}  连接: {device.link}  电量: {percent}{volt}\n"
              f"    来源: {device.source or '未知'}  ({device.detail})\n"
              f"    {'在线' if device.online else '离线'}")
    return 0


def main() -> int:
    if "--probe" in sys.argv:
        return _probe()
    from app.ui import main as ui_main
    ui_main()
    return 0


if __name__ == "__main__":
    sys.exit(main())
