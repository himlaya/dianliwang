"""Record HID traffic on the VGN dongle while the vendor app queries it.

Read-only: opens every collection of VID 0x320F and logs all incoming
reports, so the frames VGN HUB exchanges with the keyboard become visible.
"""

import sys
import time

sys.path.insert(0, ".")

from app import hid


def main(seconds: float = 25.0) -> None:
    infos = [i for i in hid.enumerate_devices() if i.vendor_id == 0x320F]
    handles = []
    for info in infos:
        if info.input_len < 3:
            continue
        try:
            dev = hid.HidDevice(info, writable=False)
        except OSError as exc:
            print(f"skip page 0x{info.usage_page:04X}: {exc}", flush=True)
            continue
        handles.append((info, dev))
        print(f"listening page=0x{info.usage_page:04X} usage=0x{info.usage:04X} "
              f"in={info.input_len}", flush=True)

    if not handles:
        print("no VGN HID collection found", flush=True)
        return

    deadline = time.monotonic() + seconds
    seen = 0
    while time.monotonic() < deadline:
        for info, dev in handles:
            data = dev.read(max(info.input_len, 64), 60)
            if not data:
                continue
            seen += 1
            stamp = time.strftime("%H:%M:%S")
            print(f"{stamp} page=0x{info.usage_page:04X} {data.hex()}", flush=True)

    for _info, dev in handles:
        dev.close()
    print(f"done, {seen} reports", flush=True)


if __name__ == "__main__":
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    main(duration)
