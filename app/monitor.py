"""Background scanner that merges all providers into one device snapshot."""

from __future__ import annotations

import threading
import time
import traceback

from . import logitech, sony, vgn
from . import unknown as unknown_provider
from .config import Config
from .model import Device

PROVIDERS = (
    ("logitech", logitech.scan),
    ("sony", sony.scan),
    ("vgn", vgn.scan),
)

OFFLINE_GRACE_SECONDS = 15 * 60


class Monitor:
    """Owns the refresh thread; the UI only reads ``snapshot()``."""

    def __init__(self, config: Config):
        self.config = config
        self._lock = threading.Lock()
        self._devices: list[Device] = []
        self._last_scan = 0.0
        self._last_error = ""
        self._alerts: list[tuple[float, str, int]] = []
        self._notified: dict[str, int] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._scanning = False

    # -- lifecycle --------------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._loop, name="battery-scan",
                                        daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def refresh_now(self) -> None:
        self._wake.set()

    # -- state ------------------------------------------------------------
    def snapshot(self) -> tuple[list[Device], float, str, bool]:
        with self._lock:
            devices = [Device(**{**d.__dict__}) for d in self._devices]
            return devices, self._last_scan, self._last_error, self._scanning

    def pop_alerts(self) -> list[tuple[str, int]]:
        with self._lock:
            now = time.time()
            fresh = [(ts, text, pct) for ts, text, pct in self._alerts
                     if now - ts < 30]
            self._alerts = []
            return [(text, pct) for _ts, text, pct in fresh]

    # -- scanning ---------------------------------------------------------
    def _loop(self) -> None:
        # first scan runs immediately
        while not self._stop.is_set():
            self._scan_once()
            interval = max(10, int(self.config.interval_seconds))
            self._wake.wait(timeout=interval)
            self._wake.clear()

    def _scan_once(self) -> None:
        with self._lock:
            self._scanning = True
        errors: list[str] = []
        fresh: list[Device] = []
        for name, provider in PROVIDERS:
            try:
                fresh.extend(provider())
            except Exception as exc:  # provider bugs must never kill the loop
                errors.append(f"{name}: {exc}")
                if __debug__:
                    traceback.print_exc()

        # Anything wireless we did not manage to read still deserves a card,
        # so the user can tell "not detected" apart from "not supported".
        try:
            claimed = {d.hw_id for d in fresh if d.hw_id}
            fresh.extend(unknown_provider.scan(claimed))
        except Exception as exc:
            errors.append(f"unknown: {exc}")
            if __debug__:
                traceback.print_exc()

        now = time.time()
        merged: list[Device] = []
        with self._lock:
            previous = {d.uid: d for d in self._devices}
        seen: set[str] = set()
        for device in fresh:
            old = previous.get(device.uid)
            if old is not None and device.percent is None and old.percent is not None:
                # the radio link is down or the read timed out: keep the last
                # known value but stop pretending the device is live
                device.percent = old.percent
                device.charging = old.charging
                device.voltage_mv = old.voltage_mv
                device.detail = device.detail or old.detail
                device.online = False
            merged.append(device)
            seen.add(device.uid)

        # keep recently-seen devices that are temporarily unreachable
        for uid, old in previous.items():
            if uid in seen:
                continue
            if now - old.updated_at > OFFLINE_GRACE_SECONDS:
                continue
            stale = Device(**{**old.__dict__})
            stale.online = False
            merged.append(stale)

        merged.sort(key=lambda d: (not d.has_battery, d.kind, d.name.lower()))

        with self._lock:
            self._devices = merged
            self._last_scan = now
            self._last_error = "; ".join(errors)
            self._scanning = False
            self._check_low_battery(merged)

    def _check_low_battery(self, devices: list[Device]) -> None:
        if not self.config.notify_low_battery:
            return
        threshold = max(1, min(90, self.config.low_battery_percent))
        for device in devices:
            if not device.online or device.percent is None:
                continue
            if device.charging:
                self._notified.pop(device.uid, None)
                continue
            if device.percent <= threshold:
                last = self._notified.get(device.uid)
                # alert once per 10 % band, and again when it drops further
                band = device.percent // 10
                if last is None or band < last:
                    self._notified[device.uid] = band
                    self._alerts.append((time.time(), device.name, device.percent))
            else:
                self._notified.pop(device.uid, None)
