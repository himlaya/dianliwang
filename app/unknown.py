"""Detect wireless peripherals whose battery protocol is not supported yet.

The card is still useful: it tells the user the device was seen, which link it
uses, and that no reading is available instead of silently hiding it.
"""

from __future__ import annotations

import time

from . import hid
from .model import (KIND_GAMEPAD, KIND_HEADSET, KIND_KEYBOARD, KIND_MOUSE,
                    LINK_24G, LINK_BT, Device)

WIRELESS_WORDS = ("2.4g", "2.4 g", "dongle", "receiver", "接收器", "无线",
                  "wireless", "bt", "蓝牙", "低延迟")
# Collections that look like an input device rather than an LED/audio gadget.
INPUT_PAGES = {0x0001}

CLAIMED_VENDORS = {0x046D, 0x054C}  # handled by dedicated providers

NAME_SUFFIXES = (" 2.4g dongle", " 2.4g receiver", " usb receiver", " dongle",
                 " receiver", " 接收器", " 2.4g")


def _clean_name(name: str) -> str:
    text = name.strip()
    low = text.lower()
    for suffix in NAME_SUFFIXES:
        if low.endswith(suffix):
            text = text[: -len(suffix)].strip()
            low = text.lower()
    return text or name.strip()


def _guess_kind(groups: list[hid.HidInfo], name: str) -> str:
    uses = {(g.usage_page, g.usage) for g in groups}
    if (0x0001, 0x0005) in uses:
        return KIND_GAMEPAD
    if (0x0001, 0x0006) in uses:
        return KIND_KEYBOARD
    if (0x0001, 0x0002) in uses:
        return KIND_MOUSE
    text = name.lower()
    if any(w in text for w in ("keyboard", "键盘", "keys")):
        return KIND_KEYBOARD
    if any(w in text for w in ("mouse", "鼠标", "mice")):
        return KIND_MOUSE
    if any(w in text for w in ("pad", "手柄", "controller")):
        return KIND_GAMEPAD
    if any(w in text for w in ("headset", "耳机", "headphone", "audio")):
        return KIND_HEADSET
    if (0x000C, 0x0001) in uses:
        # consumer-control collection without pointer data: usually a keyboard
        return KIND_KEYBOARD
    return KIND_OTHER


def scan(claimed: set[str] | None = None,
         existing: dict[str, Device] | None = None) -> list[Device]:
    claimed = claimed or set()
    groups: dict[str, list[hid.HidInfo]] = {}
    for info in hid.enumerate_devices():
        if info.vendor_id in CLAIMED_VENDORS:
            continue
        node = info.hw_node or info.path
        groups.setdefault(node, []).append(info)

    devices: list[Device] = []
    for node, items in groups.items():
        if node in claimed:
            continue
        label = next((i.product for i in items if i.product), "")
        low = label.lower()
        if not label or not any(w in low for w in WIRELESS_WORDS):
            continue
        if not any(i.usage_page in INPUT_PAGES for i in items):
            continue
        bluetooth = any(i.is_bluetooth for i in items)
        name = _clean_name(label)
        devices.append(Device(
            uid=f"unknown:{node}",
            name=name,
            kind=_guess_kind(items, name),
            link=LINK_BT if bluetooth else LINK_24G,
            percent=None,
            charging=None,
            source="",
            detail="未识别电量协议" if bluetooth else "2.4G 接收器 · 未识别协议",
            updated_at=time.time(),
            hw_id=node,
        ))
    return devices
