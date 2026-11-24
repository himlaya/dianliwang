"""Shared data model for a monitored peripheral."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

KIND_MOUSE = "mouse"
KIND_KEYBOARD = "keyboard"
KIND_GAMEPAD = "gamepad"
KIND_HEADSET = "headset"
KIND_OTHER = "other"

LINK_BT = "蓝牙"
LINK_24G = "2.4G"
LINK_USB = "USB"
LINK_RECEIVER = "2.4G 接收器"


@dataclass
class Device:
    uid: str
    name: str
    kind: str = KIND_OTHER
    link: str = ""
    percent: int | None = None
    charging: bool | None = None
    voltage_mv: int | None = None
    source: str = ""
    detail: str = ""
    online: bool = True
    updated_at: float = field(default_factory=time.time)
    hw_id: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def has_battery(self) -> bool:
        return self.percent is not None

    @property
    def level_color(self) -> str:
        p = self.percent
        if p is None:
            return "#5b6472"
        if self.charging:
            return "#38d9a9"
        if p <= 10:
            return "#ff5c5c"
        if p <= 30:
            return "#ff9558"
        if p <= 60:
            return "#ffc53d"
        return "#4ad991"

    def merge(self, other: "Device") -> None:
        """Keep identity from self, take fresh readings from other."""
        self.name = other.name or self.name
        self.kind = other.kind
        self.link = other.link or self.link
        self.percent = other.percent
        self.charging = other.charging
        self.voltage_mv = other.voltage_mv
        self.source = other.source
        self.detail = other.detail
        self.online = True
        self.updated_at = other.updated_at
        self.extra.update(other.extra)
