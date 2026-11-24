"""Probe unknown 2.4G dongles for a battery query.

Tries the frames used by several Chinese 2.4G vendors and prints any reply so
a protocol can be recognised by hand.  Read-only experiment tool.
"""

import sys
import time

sys.path.insert(0, ".")

from app import hid

CANDIDATES = [
    # (label, report_id, payload, optional expected byte/value)
    ("ATK/VXE p2", 0x08, [0x7D, 0x72, 0x02, 0x00, 0x01, 0x07, 0x01]),
    ("ATK/VXE p1", 0x08, [0x04] + [0x00] * 15 + [0x49]),
    ("nordic 0x15", 0x05, [0x15, 0x00, 0x00, 0x01]),
    ("vgn 0x06", 0x06, [0x01, 0x00]),
    ("vgn 0x08 aa", 0x08, [0xAA, 0x01]),
    ("generic 0x02", 0x02, [0x01]),
]

TARGET_VIDS = {0x320F, 0x3554, 0x373B, 0x1915, 0x05AC, 0x1EA7}


def read_all(dev, seconds=0.35):
    out = []
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        data = dev.read(80, 90)
        if data:
            out.append(data)
    return out


infos = [i for i in hid.enumerate_devices() if i.vendor_id in TARGET_VIDS]
print(f"{len(infos)} candidate collections")
for info in infos:
    if info.output_len < 3:
        continue
    print(f"\n=== {info.vid_pid} page=0x{info.usage_page:04X} "
          f"usage=0x{info.usage:04X} out={info.output_len} {info.product!r}")
    try:
        dev = hid.HidDevice(info)
    except OSError as exc:
        print("   open failed:", exc)
        continue
    try:
        idle = read_all(dev, 0.2)
        if idle:
            print("   idle stream:", [d.hex() for d in idle[:3]])
        for label, report_id, payload in CANDIDATES:
            frame_len = info.output_len
            if frame_len < len(payload) + 1:
                print(f"   {label}: skipped (frame too small)")
                continue
            frame = bytearray(frame_len)
            frame[0] = report_id
            frame[1:1 + len(payload)] = bytes(payload)
            ok = dev.write(bytes(frame))
            replies = read_all(dev, 0.3)
            if replies:
                print(f"   {label}: ok={ok} -> {[r.hex() for r in replies]}")
            else:
                print(f"   {label}: ok={ok} -> (no reply)")
    finally:
        dev.close()
