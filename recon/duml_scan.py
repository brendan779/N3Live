#!/usr/bin/env python3
"""Sweep every DUML receiver address with get_version on IF4.

`get_version` (00:01) is the one command every DUML node answers. Sending it
to all 256 possible receiver addresses maps which modules are reachable from
the Mac in OTG-computer mode — i.e. whether the goggles relay to the camera /
air unit at all, or only answer for themselves.

    ../.venv/bin/python duml_scan.py
"""

import sys
import time

import usb.core
import usb.util

import duml

DJI_VID, DJI_PID = 0x2CA3, 0x0020
CONTROL_IFACE, EP_OUT, EP_IN = 4, 0x04, 0x85
SENDER = 0x2A


def main() -> int:
    dev = usb.core.find(idVendor=DJI_VID, idProduct=DJI_PID)
    if dev is None:
        print("Goggles not found — connected in OTG-computer mode?")
        return 1

    usb.util.claim_interface(dev, CONTROL_IFACE)
    answered: dict[int, tuple[int, bytes]] = {}
    print("Sweeping receiver 0x00–0xFF with get_version…\n")
    try:
        for rx in range(256):
            frame = duml.build(SENDER, rx, seq=0x2000 + rx, cmd_type=0x40,
                               cmd_set=0x00, cmd_id=0x01)
            try:
                dev.write(EP_OUT, frame, timeout=400)
            except usb.core.USBError:
                continue
            buf = bytearray()
            deadline = time.time() + 0.3
            while time.time() < deadline:
                try:
                    buf += bytes(dev.read(EP_IN, 16384, timeout=120))
                except usb.core.USBError:
                    break
            packets, _ = duml.parse_stream(buf)
            for p in packets:
                if p.cmd_set == 0x00 and p.cmd_id == 0x01 and p.sender == rx:
                    answered[rx] = (p.payload[0] if p.payload else -1,
                                    p.payload)
                    break
    finally:
        usb.util.release_interface(dev, CONTROL_IFACE)

    print(f"── {len(answered)} address(es) answered get_version ──")
    for rx, (status, payload) in sorted(answered.items()):
        ascii_preview = "".join(
            chr(b) if 32 <= b < 127 else "." for b in payload)
        print(f"  0x{rx:02X}  status=0x{status:02X}  "
              f"plen={len(payload):<3} [{ascii_preview}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
