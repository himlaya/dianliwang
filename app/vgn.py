"""VGN / VXE keyboards and mice.

VGN does not expose battery through HID: the dongle only bridges vendor
commands, and the command set is implemented inside the vendor's native
service (``game-power-service.exe``) which the official VGN HUB app talks to
over ``POST http://127.0.0.1:<port>/<model>``.

So this provider reads the battery through that local service instead of
speaking the wire protocol itself.  It is only active while VGN HUB (or its
background service) is running; otherwise the device is simply reported as
unsupported, exactly like before.

The percentage is the one VGN HUB displays: the firmware reports a raw level
and the app snaps it to the nearest 5 %, so we do the same.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.request

from . import hid
from .model import KIND_KEYBOARD, KIND_MOUSE, LINK_24G, Device

CREATE_NO_WINDOW = 0x08000000

# endpoint -> (display name, device kind)
ENDPOINTS: dict[str, tuple[str, str]] = {
    "s99": ("VGN S99", KIND_KEYBOARD),
    "v98pro": ("VGN V98 Pro", KIND_KEYBOARD),
    "vxe75": ("VXE 75", KIND_KEYBOARD),
    "v75pro": ("VGN V75 Pro", KIND_KEYBOARD),
    "v75evo": ("VGN V75 Evo", KIND_KEYBOARD),
    "n75pro": ("VGN N75 Pro", KIND_KEYBOARD),
    "bykb": ("VGN 键盘", KIND_KEYBOARD),
    "f1pm": ("VGN F1 PM", KIND_MOUSE),
}

_cache: dict[str, object] = {"port": None, "checked_at": 0.0}
_PORT_TTL = 30.0


def _snap_percent(raw: int) -> int:
    """Same rounding the vendor app applies (nearest 5 %)."""
    if raw >= 100:
        return 100
    if raw <= 0:
        return 0
    remainder = raw % 10
    if remainder < 5:
        raw += 5 - remainder
    elif remainder > 5:
        raw += 10 - remainder
    return max(0, min(100, raw))


def _post(port: int, endpoint: str, method: str,
          params: dict | None = None, timeout: float = 0.8):
    url = f"http://127.0.0.1:{port}/{endpoint}"
    body = json.dumps({"method": method, "params": params or {}}).encode()
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8", "ignore"))
    except Exception:
        return None
    if not isinstance(payload, dict) or payload.get("code") != 200:
        return None
    return payload.get("data")


def _port_from_registry() -> int | None:
    import winreg
    roots = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
    subkeys = [
        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
    ]
    for root in roots:
        for subkey in subkeys:
            try:
                parent = winreg.OpenKey(root, subkey)
            except OSError:
                continue
            try:
                for index in range(256):
                    try:
                        name = winreg.EnumKey(parent, index)
                    except OSError:
                        break
                    try:
                        with winreg.OpenKey(parent, name) as entry:
                            title = str(winreg.QueryValueEx(entry, "DisplayName")[0])
                            if "vgn" not in title.lower():
                                continue
                            icon = str(winreg.QueryValueEx(entry, "DisplayIcon")[0])
                    except OSError:
                        continue
                    exe = icon.split(",")[0].strip().strip('"')
                    config = os.path.join(os.path.dirname(exe), "resources",
                                          "config.json")
                    try:
                        with open(config, "r", encoding="utf-8") as handle:
                            return int(json.load(handle)["port"])
                    except Exception:
                        continue
            finally:
                parent.Close()
    return None


def _port_from_process() -> int | None:
    """Fallback: find the listening port of game-power-service.exe."""
    try:
        listing = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq game-power-service.exe",
             "/FO", "CSV", "/NH"],
            capture_output=True, text=True, timeout=4,
            creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        return None
    pids = set()
    for line in listing.splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(parts[1])
    if not pids:
        return None
    try:
        table = subprocess.run(["netstat", "-ano", "-p", "TCP"],
                               capture_output=True, text=True, timeout=4,
                               creationflags=CREATE_NO_WINDOW).stdout
    except Exception:
        return None
    for line in table.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[3] != "LISTENING":
            continue
        if fields[4] not in pids:
            continue
        if fields[1].endswith(":0") or fields[1].startswith("0.0.0"):
            continue
        try:
            return int(fields[1].rsplit(":", 1)[1])
        except ValueError:
            continue
    return None


def service_port(force: bool = False) -> int | None:
    now = time.monotonic()
    if (not force and _cache["port"]
            and now - float(_cache["checked_at"]) < _PORT_TTL):
        return int(_cache["port"])  # type: ignore[arg-type]
    port = _port_from_registry()
    if port is None or _post(port, "s99", "device_is_link_ok", timeout=0.5) is None:
        fallback = _port_from_process()
        if fallback and _post(fallback, "s99", "device_is_link_ok",
                              timeout=0.5) is not None:
            port = fallback
        elif port is not None and _post(port, "s99", "device_is_link_ok",
                                        timeout=0.5) is not None:
            pass
        else:
            port = None
    _cache["port"] = port
    _cache["checked_at"] = now
    return port


def _dongle_node() -> str:
    """Hardware id of the VGN dongle, so the generic provider skips it."""
    for info in hid.enumerate_devices():
        if info.vendor_id == 0x320F:
            return info.hw_node or info.path
    return ""


def scan(existing: dict[str, Device] | None = None) -> list[Device]:
    port = service_port()
    if not port:
        return []
    node = _dongle_node()
    devices: list[Device] = []
    for endpoint, (name, kind) in ENDPOINTS.items():
        linked = _post(port, endpoint, "device_is_link_ok", timeout=0.6)
        if linked is not True:
            continue
        power = _post(port, endpoint, "get_device_power_info", timeout=0.8)
        percent = None
        charging = None
        if isinstance(power, list) and len(power) >= 2:
            try:
                percent = _snap_percent(int(power[0]))
                charging = int(power[1]) != 0
            except (TypeError, ValueError):
                percent = None
        devices.append(Device(
            uid=f"vgn:{endpoint}",
            name=name,
            kind=kind,
            link=LINK_24G,
            percent=percent,
            charging=charging,
            source="VGN 服务",
            detail="通过 VGN HUB 本地服务读取",
            updated_at=time.time(),
            hw_id=node,
        ))
    return devices
