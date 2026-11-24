"""Logitech HID++ 2.0 provider: battery for Lightspeed / Unifying / Bluetooth.

Logitech wireless peripherals answer HID++ 2.0 queries on a vendor-defined
HID collection (usage page 0xFF00).  A USB receiver multiplexes up to six
paired devices through device indices 0x01..0x06, while a device connected
straight over Bluetooth answers on index 0xFF.

Battery is exposed by one of three features, in order of preference:

    0x1004 UNIFIED_BATTERY   level %, charge flags, voltage
    0x1000 BATTERY_VOLTAGE   level % (fn 1) and voltage (fn 0)
    0x1001 BATTERY_VOLTAGE   big-endian millivolts + flags (G-series)

All of them are read defensively: a device that does not answer is simply
reported without a battery value instead of raising.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from . import hid
from .model import (KIND_GAMEPAD, KIND_KEYBOARD, KIND_MOUSE, LINK_24G,
                    LINK_BT, Device)

FEATURE_ROOT = 0x0000
FEATURE_DEVICE_INFO = 0x0003
FEATURE_DEVICE_NAME = 0x0005
FEATURE_BATTERY_STATUS = 0x1001
FEATURE_BATTERY_VOLTAGE = 0x1000
FEATURE_BATTERY_UNIFIED = 0x1004
FEATURE_BATTERY_LEVEL_STATUS = 0x1006

SOFTWARE_ID = 0x02
REPORT_SHORT = 0x10
REPORT_LONG = 0x11

DEVICE_INDICES = (0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0xFF)

# Product ids that are receivers rather than peripherals.
RECEIVER_IDS = {0xC539, 0xC534, 0xC532, 0xC52B, 0xC548, 0xC547, 0xC54D}

# Known product names, used when the device has no DEVICE_NAME feature.
PRODUCT_NAMES = {
    0x407F: "G502 LIGHTSPEED",
    0xC08D: "G502 X",
    0xC094: "G502 X PLUS",
    0x4082: "G403",
    0xC084: "G304",
    0x4074: "G PRO Wireless",
    0xC088: "G PRO X Superlight",
    0x4079: "G703",
    0x408E: "G903",
    0xC086: "G903 HERO",
    0xB034: "MX Master 3",
    0xC52B: "Unifying Receiver",
}


@dataclass
class Reading:
    percent: int | None = None
    voltage_mv: int | None = None
    charging: bool = False
    external_power: bool = False
    source: str = ""


def percent_from_voltage(voltage_mv: int) -> int:
    """Approximate a single-cell Li-ion discharge curve."""
    curve = [
        (4230, 100), (4150, 97), (4100, 93), (4060, 90), (4020, 86),
        (4000, 84), (3980, 82), (3960, 79), (3940, 76), (3920, 73),
        (3900, 70), (3880, 66), (3860, 62), (3840, 58), (3820, 54),
        (3800, 50), (3780, 46), (3760, 42), (3740, 38), (3720, 34),
        (3700, 30), (3680, 26), (3660, 22), (3630, 17), (3600, 12),
        (3560, 7), (3500, 3), (3400, 0),
    ]
    if voltage_mv >= curve[0][0]:
        return 100
    if voltage_mv <= curve[-1][0]:
        return 0
    for (v_hi, p_hi), (v_lo, p_lo) in zip(curve, curve[1:]):
        if v_lo <= voltage_mv <= v_hi:
            ratio = (voltage_mv - v_lo) / (v_hi - v_lo)
            return int(round(p_lo + ratio * (p_hi - p_lo)))
    return 0


class Channel:
    """HID++ 2.0 request/response over one vendor collection."""

    def __init__(self, info: hid.HidInfo):
        self.info = info
        self._dev = hid.HidDevice(info, writable=True)
        self.long_supported = info.output_len >= 20
        self._features: dict[tuple[int, int], int] = {}
        self._names: dict[int, str] = {}

    def close(self) -> None:
        self._dev.close()

    def __enter__(self) -> "Channel":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _drain(self) -> None:
        for _ in range(4):
            if self._dev.read(32, 8) is None:
                break

    def request(self, dev_index: int, feature_index: int, function: int,
                params: bytes = b"", use_long: bool | None = None,
                timeout_ms: int = 250) -> bytes | None:
        if use_long is None:
            use_long = self.long_supported
        if use_long and not self.long_supported:
            return None
        size = 20 if use_long else 7
        frame = bytearray(size)
        frame[0] = REPORT_LONG if use_long else REPORT_SHORT
        frame[1] = dev_index
        frame[2] = feature_index
        frame[3] = ((function & 0x0F) << 4) | SOFTWARE_ID
        frame[4:4 + len(params)] = params
        self._drain()
        if not self._dev.write(bytes(frame)):
            return None
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            data = self._dev.read(32, max(10, int((deadline - time.monotonic()) * 1000)))
            if not data or len(data) < 4:
                continue
            if data[0] not in (REPORT_SHORT, REPORT_LONG):
                continue
            if data[1] != dev_index or data[2] != feature_index:
                continue
            if (data[3] & 0x0F) != SOFTWARE_ID:
                continue
            return data[4:]
        return None

    # -- feature helpers --------------------------------------------------
    def feature(self, dev_index: int, feature_id: int,
                timeout_ms: int = 200) -> int:
        key = (dev_index, feature_id)
        if key not in self._features:
            reply = self.request(dev_index, FEATURE_ROOT, 0,
                                 bytes([feature_id >> 8, feature_id & 0xFF]),
                                 timeout_ms=timeout_ms)
            self._features[key] = reply[0] if reply and reply[0] else 0
        return self._features[key]

    def name(self, dev_index: int) -> str:
        if dev_index in self._names:
            return self._names[dev_index]
        index = self.feature(dev_index, FEATURE_DEVICE_NAME)
        name = ""
        if index:
            reply = self.request(dev_index, index, 0)
            if reply and reply[0]:
                total = reply[0]
                chunks = []
                # every reply carries up to 16 characters starting at the
                # requested offset, so walk the string in 16-char windows
                for offset in range(0, min(total, 64), 16):
                    part = self.request(dev_index, index, 1,
                                        bytes([offset]), timeout_ms=200)
                    if not part:
                        break
                    chunks.append(part[:16])
                raw = b"".join(chunks)[:total]
                name = raw.replace(b"\x00", b"").decode("utf-8", "ignore").strip()
        self._names[dev_index] = name
        return name

    def product_id(self, dev_index: int) -> int:
        index = self.feature(dev_index, FEATURE_DEVICE_INFO)
        if not index:
            return 0
        reply = self.request(dev_index, index, 0)
        if not reply or len(reply) < 8:
            return 0
        # params: entityCount, unitId[4], modelId[6], ...
        model = reply[5:11]
        if len(model) < 3:
            return 0
        return (model[1] << 8) | model[2]

    # -- battery ----------------------------------------------------------
    def battery(self, dev_index: int) -> Reading | None:
        for reader in (self._read_unified, self._read_voltage_level,
                       self._read_voltage_status):
            try:
                reading = reader(dev_index)
            except Exception:
                reading = None
            if reading and reading.percent is not None:
                return reading
        return None

    def _read_unified(self, dev_index: int) -> Reading | None:
        index = self.feature(dev_index, FEATURE_BATTERY_UNIFIED)
        if not index:
            return None
        reply = self.request(dev_index, index, 0, b"\x00", use_long=True)
        if not reply or len(reply) < 3:
            return None
        level, flags = reply[0], reply[1]
        voltage = reply[2] | (reply[3] << 8) if len(reply) >= 4 else None
        if level > 100:
            return None
        return Reading(percent=level, voltage_mv=voltage,
                       charging=bool(flags & 0x01),
                       external_power=bool(flags & 0x02),
                       source="HID++ unified")

    def _read_voltage_level(self, dev_index: int) -> Reading | None:
        index = self.feature(dev_index, FEATURE_BATTERY_VOLTAGE)
        if not index:
            return None
        reply = self.request(dev_index, index, 1)
        if reply and reply[0] <= 100:
            flags = reply[1] if len(reply) > 1 else 0
            voltage = None
            if len(reply) >= 4:
                voltage = reply[2] | (reply[3] << 8)
            return Reading(percent=reply[0], voltage_mv=voltage,
                           charging=bool(flags & 0x01),
                           external_power=bool(flags & 0x02),
                           source="HID++ level")
        reply = self.request(dev_index, index, 0)
        if not reply:
            return None
        voltage = reply[0] | (reply[1] << 8)
        if not 2500 <= voltage <= 4500:
            return None
        flags = reply[2] if len(reply) > 2 else 0
        return Reading(percent=percent_from_voltage(voltage),
                       voltage_mv=voltage,
                       charging=bool(flags & 0x01),
                       external_power=bool(flags & 0x02),
                       source="HID++ voltage")

    def _read_voltage_status(self, dev_index: int) -> Reading | None:
        """0x1001: deprecated, but the only battery feature on G-series."""
        index = self.feature(dev_index, FEATURE_BATTERY_STATUS)
        if not index:
            return None
        reply = self.request(dev_index, index, 0, b"\x00", use_long=True)
        if not reply or len(reply) < 3:
            return None
        voltage = (reply[0] << 8) | reply[1]
        flags = reply[2]
        if not 2500 <= voltage <= 4500:
            return None
        return Reading(percent=percent_from_voltage(voltage),
                       voltage_mv=voltage,
                       charging=bool(flags & 0x01),
                       external_power=bool(flags & 0x02),
                       source="HID++ 0x1001")


def _kind_from_name(name: str, product_id: int) -> str:
    text = name.lower()
    if any(w in text for w in ("mouse", "mice", "trackball")):
        return KIND_MOUSE
    if any(w in text for w in ("keyboard", "keys", "k380", "k580", "craft")):
        return KIND_KEYBOARD
    if any(w in text for w in ("gamepad", "controller", "wheel", "pedal")):
        return KIND_GAMEPAD
    if product_id in (0x407F, 0xC08D, 0xC094, 0x4082, 0xC084, 0x4074,
                      0xC088, 0x4079, 0x408E, 0xC086):
        return KIND_MOUSE
    return KIND_MOUSE


def _candidate_channels(infos: list[hid.HidInfo]) -> list[hid.HidInfo]:
    out = []
    for info in infos:
        if info.vendor_id != 0x046D or info.usage_page != 0xFF00:
            continue
        if info.output_len >= 20 or info.output_len == 7:
            out.append(info)
    # prefer the long-report interface (HID++ 2.0 carries feature queries there)
    out.sort(key=lambda i: (i.output_len < 20, i.path))
    return out


# Which device indices answered last time, keyed by HID instance id.  Avoids
# re-sweeping six indices on every refresh once a receiver's devices are known.
_INDEX_CACHE: dict[str, list[int]] = {}
_EMPTY_TS: dict[str, float] = {}
_EMPTY_RETRY_S = 60.0


def _probe_channel(info: hid.HidInfo, indices: list[int]) -> list[Device]:
    channel = Channel(info)
    devices: list[Device] = []
    alive: list[int] = []
    try:
        for dev_index in indices:
            if not channel.feature(dev_index, FEATURE_DEVICE_INFO,
                                   timeout_ms=150):
                continue
            alive.append(dev_index)
            product_id = channel.product_id(dev_index)
            if product_id in RECEIVER_IDS and dev_index == 0xFF:
                continue
            reading = channel.battery(dev_index)
            name = channel.name(dev_index)
            if not name:
                name = PRODUCT_NAMES.get(product_id, "")
            if not name:
                name = info.product if info.product.lower() not in (
                    "usb receiver", "receiver", "") else "罗技无线设备"
            if dev_index == 0xFF and reading is None:
                continue  # the receiver itself has no battery
            direct_bt = info.is_bluetooth
            devices.append(Device(
                uid=f"logi:{info.instance_id or info.path}:{dev_index:02X}",
                name=name,
                kind=_kind_from_name(name, product_id),
                link=LINK_BT if direct_bt else LINK_24G,
                percent=reading.percent if reading else None,
                charging=reading.charging if reading else None,
                voltage_mv=reading.voltage_mv if reading else None,
                source=reading.source if reading else "",
                detail=("HID++ 2.0 · 蓝牙" if direct_bt
                        else "HID++ 2.0 · 2.4G 接收器"),
                updated_at=time.time(),
                hw_id=info.hw_node or info.path,
            ))
    finally:
        channel.close()
    cache_key = info.instance_id or info.path
    if alive or cache_key not in _INDEX_CACHE:
        _INDEX_CACHE[cache_key] = alive
        if not alive:
            _EMPTY_TS[cache_key] = time.time()
    return devices


def scan(existing: dict[str, Device] | None = None) -> list[Device]:
    infos = hid.enumerate_devices()
    candidates = _candidate_channels(infos)
    found: list[Device] = []

    # Pass 1: HID++ 2.0 on the long-report collections.
    for info in [i for i in candidates if i.output_len >= 20]:
        key = info.instance_id or info.path
        cached = _INDEX_CACHE.get(key)
        if cached == [] and time.time() - _EMPTY_TS.get(key, 0) < _EMPTY_RETRY_S:
            continue
        indices = cached if cached else list(DEVICE_INDICES)
        try:
            found.extend(_probe_channel(info, indices))
        except OSError:
            continue
        except Exception:
            continue

    # Pass 2: devices that only expose the 7-byte HID++ interface.
    if not found:
        for info in candidates:
            if info.output_len != 7:
                continue
            try:
                found.extend(_probe_channel(info, list(DEVICE_INDICES)))
            except OSError:
                continue
            except Exception:
                continue

    return found
