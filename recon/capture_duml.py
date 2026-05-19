#!/usr/bin/env python3
"""Capture and decode the DUML control channel (vendor interface 4).

Reads IF4's bulk IN endpoint, frames the bytes as DUML, prints each packet,
and ends with a summary of the distinct cmd_set:cmd_id messages seen — which
is what we need to recognise heartbeats vs. queries vs. the video commands.

    ../.venv/bin/python capture_duml.py [seconds]

Works with just the goggles connected (the IF4 control channel is live even
without an air-unit feed).
"""

import sys
import time
from collections import Counter

import usb.core
import usb.util

import duml

DJI_VID, DJI_PID = 0x2CA3, 0x0020
CONTROL_IFACE = 4
EP_IN = 0x85          # IF4 bulk IN, from the P0 descriptor


def main() -> int:
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else 6.0

    dev = usb.core.find(idVendor=DJI_VID, idProduct=DJI_PID)
    if dev is None:
        print("Goggles not found — connected and in OTG mode?")
        return 1

    usb.util.claim_interface(dev, CONTROL_IFACE)
    buf = bytearray()
    seen: Counter = Counter()
    samples: dict[str, duml.DumlPacket] = {}
    total_bytes = 0
    print(f"Capturing DUML on IF{CONTROL_IFACE} (EP 0x{EP_IN:02X}) "
          f"for {seconds:.0f}s…\n")

    try:
        deadline = time.time() + seconds
        while time.time() < deadline:
            try:
                chunk = bytes(dev.read(EP_IN, 16384, timeout=300))
            except usb.core.USBError as exc:
                if "timeout" in str(exc).lower() or exc.errno == 60:
                    continue
                print(f"read error — {exc}")
                break
            total_bytes += len(chunk)
            buf += chunk
            packets, buf = duml.parse_stream(buf)
            for pkt in packets:
                key = f"{pkt.cmd}  {pkt.sender:02X}->{pkt.receiver:02X}"
                seen[key] += 1
                samples.setdefault(key, pkt)
                if seen[key] <= 2:                   # print first couple only
                    print(pkt)
    finally:
        usb.util.release_interface(dev, CONTROL_IFACE)

    print(f"\n── summary ──")
    print(f"{total_bytes} bytes, {sum(seen.values())} DUML packets, "
          f"{len(buf)} unframed tail bytes")
    for key, count in seen.most_common():
        pkt = samples[key]
        ascii_preview = "".join(
            chr(b) if 32 <= b < 127 else "." for b in pkt.payload[:32])
        print(f"  {key}  ×{count:<4} cmd_type={pkt.cmd_type:02X} "
              f"plen={len(pkt.payload):<4} [{ascii_preview}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
