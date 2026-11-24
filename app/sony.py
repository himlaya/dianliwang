"""PlayStation controller provider (DualSense / DualShock 4).

Battery data lives inside the controller's HID input report, not in a
separate feature:

    DualSense, USB report 0x01 (64 bytes) -> status byte at 53
    DualSense, BT  report 0x31 (78 bytes) -> status byte at 54
    DualShock 4, USB 0x01 / BT 0x11      -> status byte at 30 / 32

The byte carries the capacity in the low nibble (one unit = 10 %) and the
charge state in the high nibble, matching the Linux ``hid-playstation``
driver.
"""

from __future__ import annotations

import time

from . import hid
from .model import KIND_GAMEPAD, LINK_BT, LINK_USB, Device

SONY_VID = 0x054C
PID_DUALSENSE = 0x0CE6
PID_DUALSENSE_EDGE = 0x0DF2
PID_DS4 = 0x05C4
PID_DS4_SLIM = 0x09CC

DUALSENSE_IDS = {PID_DUALSENSE, PID_DUALSENSE_EDGE}
DS4_IDS = {PID_DS4, PID_DS4_SLIM}


def _open_controller(info: hid.HidInfo) -> hid.HidDevice | None:
    try:
        return hid.HidDevice(info, writable=False)
    except OSError:
        return None


def _read_report(dev: hid.HidDevice, wanted: tuple[int, ...],
                 timeout_s: float = 1.2) -> bytes | None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        data = dev.read(max(dev.info.input_len, 78), 250)
        if data and data[0] in wanted:
            return data
    return None


def _decode_dualsense(status_byte: int,
                      wired: bool) -> tuple[int | None, bool, str]:
    level = status_byte & 0x0F
    state = status_byte >> 4
    if state == 0x02:
        return 100, True, "已充满"
    if state == 0x01 or wired:
        return min(level * 10 + 5, 100), True, "充电中"
    if state in (0x0A, 0x0B):
        return None, False, "电池温度或电压异常"
    if state == 0x0F:
        return None, False, "充电错误"
    return min(level * 10 + 5, 100), False, "放电中"


def _decode_ds4(status_byte: int, wired: bool) -> tuple[int | None, bool, str]:
    level = status_byte & 0x0F
    if level >= 10:
        return 100, True, "已充满"
    percent = level * 10 + 5
    if wired:
        return percent, True, "充电中"
    return percent, False, "放电中"


def scan(existing: dict[str, Device] | None = None) -> list[Device]:
    infos = [i for i in hid.enumerate_devices()
             if i.vendor_id == SONY_VID
             and i.usage_page == 0x0001 and i.usage == 0x0005]
    devices: list[Device] = []

    for info in infos:
        if (info.product_id not in DUALSENSE_IDS
                and info.product_id not in DS4_IDS):
            continue
        dev = _open_controller(info)
        if not dev:
            continue
        try:
            is_dualsense = info.product_id in DUALSENSE_IDS
            if is_dualsense:
                report = _read_report(dev, (0x01, 0x31))
                if not report:
                    continue
                wired = report[0] == 0x01
                offset = 53 if wired else 54
                if len(report) <= offset:
                    continue
                percent, charging, state = _decode_dualsense(report[offset], wired)
                name = "DualSense 无线控制器"
                detail = f"HID 报告 0x{report[0]:02X}"
                uid = f"sony:dualsense:{info.instance_id}"
            else:
                report = _read_report(dev, (0x01, 0x11))
                if not report:
                    continue
                wired = report[0] == 0x01
                offset = 30 if wired else 32
                if len(report) <= offset:
                    continue
                percent, charging, state = _decode_ds4(report[offset], wired)
                name = "DualShock 4 无线控制器"
                detail = f"HID 报告 0x{report[0]:02X}"
                uid = f"sony:ds4:{info.instance_id}"
            devices.append(Device(
                uid=uid,
                name=name,
                kind=KIND_GAMEPAD,
                link=LINK_USB if wired else LINK_BT,
                percent=percent,
                charging=charging,
                source="读取手柄报告",
                detail=detail,
                updated_at=time.time(),
                hw_id=info.hw_node or info.path,
            ))
        except Exception:
            continue
        finally:
            dev.close()
    return devices
