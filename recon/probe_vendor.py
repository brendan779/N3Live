#!/usr/bin/env python3
"""P1/P2 probe — find which DJI vendor interface carries the video.

Claims vendor interfaces 3..7 in turn and reads their bulk IN endpoint to see
which channel is pushing data. By default it just listens (passive); with
--magic it first sends the legacy voc-poc start packet to the bulk OUT
endpoint, which is what kicks off video on the older DJI FPV goggles.

    ../.venv/bin/python probe_vendor.py            # passive listen
    ../.venv/bin/python probe_vendor.py --magic    # send start packet first

Run with the goggles connected and a live air-unit feed.
"""

import sys
import time
import usb.core
import usb.util

DJI_VID, DJI_PID = 0x2CA3, 0x0020
VENDOR_IFACES = (3, 4, 5, 6, 7)
MAGIC = bytes.fromhex("524d5654")   # "RMVT" — voc-poc start packet (V1/V2)
LISTEN_SECONDS = 2.5


def annexb_starts(buf: bytes) -> int:
    """Count H.264/H.265 Annex-B NAL start codes — a quick 'is this video?'."""
    return buf.count(b"\x00\x00\x00\x01") + buf.count(b"\x00\x00\x01")


def probe(dev, iface_num: int, send_magic: bool) -> None:
    cfg = dev.get_active_configuration()
    intf = cfg[(iface_num, 0)]
    ep_in = usb.util.find_descriptor(
        intf, custom_match=lambda e:
        usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN)
    ep_out = usb.util.find_descriptor(
        intf, custom_match=lambda e:
        usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT)

    usb.util.claim_interface(dev, iface_num)
    try:
        if send_magic and ep_out is not None:
            try:
                ep_out.write(MAGIC, timeout=500)
                print(f"  IF{iface_num}: start packet sent")
            except usb.core.USBError as exc:
                print(f"  IF{iface_num}: start packet failed — {exc}")

        total = bytearray()
        deadline = time.time() + LISTEN_SECONDS
        while time.time() < deadline:
            try:
                total += bytes(ep_in.read(16384, timeout=300))
            except usb.core.USBError as exc:
                if "timeout" in str(exc).lower() or exc.errno == 60:
                    continue
                print(f"  IF{iface_num}: read error — {exc}")
                break

        head = total[:32].hex(" ")
        print(f"  IF{iface_num}: {len(total):>8} bytes  "
              f"nal_starts={annexb_starts(total):<5} head=[{head}]")
    finally:
        usb.util.release_interface(dev, iface_num)


def main() -> int:
    send_magic = "--magic" in sys.argv
    dev = usb.core.find(idVendor=DJI_VID, idProduct=DJI_PID)
    if dev is None:
        print("Goggles not found — connected and powered?")
        return 1

    mode = "start-packet" if send_magic else "passive listen"
    print(f"Probing vendor interfaces {VENDOR_IFACES} — {mode}, "
          f"{LISTEN_SECONDS}s each:")
    for num in VENDOR_IFACES:
        try:
            probe(dev, num, send_magic)
        except Exception as exc:                          # noqa: BLE001
            print(f"  IF{num}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
