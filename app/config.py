"""Persistent settings stored under %APPDATA%\\PeripheralBattery."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields


def config_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    path = os.path.join(base, "PeripheralBattery")
    os.makedirs(path, exist_ok=True)
    return path


@dataclass
class Config:
    interval_seconds: int = 60
    low_battery_percent: int = 20
    notify_low_battery: bool = True
    alert_popup: bool = True
    always_on_top: bool = False
    mini_mode: bool = False
    show_unsupported: bool = True
    autostart: bool = False
    close_to_tray: bool = True
    window_x: int = -1
    window_y: int = -1

    @classmethod
    def path(cls) -> str:
        return os.path.join(config_dir(), "config.json")

    @classmethod
    def load(cls) -> "Config":
        try:
            with open(cls.path(), "r", encoding="utf-8-sig") as fh:
                raw = json.load(fh)
        except Exception:
            return cls()
        known = {f.name for f in fields(cls)}
        data = {k: v for k, v in raw.items() if k in known}
        cfg = cls()
        for key, value in data.items():
            setattr(cfg, key, value)
        return cfg

    def save(self) -> None:
        try:
            with open(self.path(), "w", encoding="utf-8") as fh:
                json.dump(asdict(self), fh, ensure_ascii=False, indent=2)
        except Exception:
            pass
