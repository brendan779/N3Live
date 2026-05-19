#!/usr/bin/env python3
"""P0 recon — dump the full USB descriptor tree of the DJI Goggles N3.

Lists every configuration, interface (with alternate settings) and endpoint,
so we can see which interface carries the video and what its endpoints look
like. Run with the goggles connected and a live air-unit feed.

    ../.venv/bin/python enumerate.py
"""

import sys
import usb.core
import usb.util

DJI_VID = 0x2CA3

# USB interface class codes we care about.
CLASS_NAMES = {
    0x02: "Communications (CDC control)",
    0x0A: "CDC-Data",
    0x08: "Mass Storage",
    0xE0: "Wireless (RNDIS control)",
    0xFF: "Vendor-Specific",
}
XFER_NAMES = {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}


def describe_endpoint(ep: usb.core.Endpoint) -> str:
    addr = ep.bEndpointAddress
    direction = "IN" if usb.util.endpoint_direction(addr) == usb.util.ENDPOINT_IN else "OUT"
    xfer = XFER_NAMES.get(usb.util.endpoint_type(ep.bmAttributes), "?")
    return (f"      EP 0x{addr:02X} {direction:<3} {xfer:<11} "
            f"maxPacket={ep.wMaxPacketSize:<5} interval={ep.bInterval}")


def main() -> int:
    dev = usb.core.find(idVendor=DJI_VID)
    if dev is None:
        print(f"No DJI device (VID 0x{DJI_VID:04X}) found. "
              "Is it connected and powered?")
        return 1

    print("== DEVICE ==")
    print(f"  VID:PID     0x{dev.idVendor:04X}:0x{dev.idProduct:04X}")
    print(f"  bcdDevice   0x{dev.bcdDevice:04X}")
    print(f"  deviceClass 0x{dev.bDeviceClass:02X}")
    for label, index in (("manufacturer", dev.iManufacturer),
                          ("product", dev.iProduct),
                          ("serial", dev.iSerialNumber)):
        try:
            print(f"  {label:<11} {usb.util.get_string(dev, index)}")
        except Exception as exc:                         # noqa: BLE001
            print(f"  {label:<11} <unreadable: {exc}>")

    for cfg in dev:
        print(f"\n== CONFIGURATION {cfg.bConfigurationValue} "
              f"(interfaces: {cfg.bNumInterfaces}) ==")
        for intf in cfg:
            cls = intf.bInterfaceClass
            name = CLASS_NAMES.get(cls, f"class 0x{cls:02X}")
            print(f"  Interface {intf.bInterfaceNumber} "
                  f"alt {intf.bAlternateSetting} — {name} "
                  f"(class 0x{cls:02X} sub 0x{intf.bInterfaceSubClass:02X} "
                  f"proto 0x{intf.bInterfaceProtocol:02X}, "
                  f"{intf.bNumEndpoints} endpoints)")
            for ep in intf:
                print(describe_endpoint(ep))
    return 0


if __name__ == "__main__":
    sys.exit(main())
