#!/usr/bin/env python3
"""Send a DUML command to the goggles on IF4 and watch for a response.

For empirically probing the video-start sequence: issue a command, read the
control channel for the reply, then peek the dormant video interfaces
(IF3/5/6/7) to see if any woke up.

    ../.venv/bin/python duml_send.py <cmd_set> <cmd_id> [payload_hex] [opts]

    cmd_set / cmd_id : hex, e.g. 08 78   (dm368_set_sh_start_live_streaming)
    payload_hex      : optional, e.g. "01 00"
    --type N         : DUML cmd_type byte (default 0x40, as observed)
    --to N           : receiver address (default 0xBC, the goggles)
    --from N         : sender address (default 0x2A, the app)
    --repeat N       : send the command N times (default 1)

Requires the goggles connected in OTG-computer mode. A NACK or a
length-error response tells us about the expected payload; a video
interface waking tells us the command worked.

Example — try the live-streaming start with an empty payload:
    ../.venv/bin/python duml_send.py 08 78
"""

import sys
import time

import usb.core
import usb.util

import duml

DJI_VID, DJI_PID = 0x2CA3, 0x0020
CONTROL_IFACE, EP_CTRL_OUT, EP_CTRL_IN = 4, 0x04, 0x85
VIDEO_IFACES = {3: 0x84, 5: 0x86, 6: 0x87, 7: 0x88}   # iface -> bulk IN


def opt(name: str, default: int) -> int:
    if name in sys.argv:
        return int(sys.argv[sys.argv.index(name) + 1], 0)
    return default


def positional(argv: list[str]) -> list[str]:
    """Positional args only — skip each --flag *and its value*."""
    pos, i = [], 0
    while i < len(argv):
        if argv[i].startswith("--"):
            i += 2
        else:
            pos.append(argv[i])
            i += 1
    return pos


def main() -> int:
    args = positional(sys.argv[1:])
    if len(args) < 2:
        print(__doc__)
        return 1

    cmd_set = int(args[0], 16)
    cmd_id = int(args[1], 16)
    payload = bytes.fromhex(args[2]) if len(args) > 2 else b""
    cmd_type = opt("--type", 0x40)
    receiver = opt("--to", 0xBC)
    sender = opt("--from", 0x2A)
    repeat = opt("--repeat", 1)

    dev = usb.core.find(idVendor=DJI_VID, idProduct=DJI_PID)
    if dev is None:
        print("Goggles not found — connected in OTG-computer mode?")
        return 1

    usb.util.claim_interface(dev, CONTROL_IFACE)
    print(f"Sending DUML cmd_set=0x{cmd_set:02X} cmd_id=0x{cmd_id:02X} "
          f"type=0x{cmd_type:02X} {sender:02X}->{receiver:02X} "
          f"payload=[{payload.hex(' ')}]\n")

    try:
        for n in range(repeat):
            frame = duml.build(sender, receiver, seq=0x1000 + n,
                               cmd_type=cmd_type, cmd_set=cmd_set,
                               cmd_id=cmd_id, payload=payload)
            try:
                dev.write(EP_CTRL_OUT, frame, timeout=800)
                print(f"  → sent ({len(frame)} bytes): {frame.hex(' ')}")
            except usb.core.USBError as exc:
                print(f"  → write failed: {exc}")
                continue

            buf = bytearray()
            deadline = time.time() + 1.5
            while time.time() < deadline:
                try:
                    buf += bytes(dev.read(EP_CTRL_IN, 16384, timeout=300))
                except usb.core.USBError as exc:
                    if "timeout" in str(exc).lower() or exc.errno == 60:
                        continue
                    break
            packets, _ = duml.parse_stream(buf)
            replies = [p for p in packets
                       if p.cmd_set == cmd_set and p.cmd_id == cmd_id]
            for p in replies:
                print(f"  ← REPLY {p}")
            others = [p for p in packets if p not in replies]
            for p in others[:3]:
                print(f"  ← other {p}")
            if not packets:
                print("  ← (no DUML on control channel)")
    finally:
        usb.util.release_interface(dev, CONTROL_IFACE)

    # Did any video interface wake up?
    print("\nVideo interface check:")
    for iface, ep_in in VIDEO_IFACES.items():
        try:
            usb.util.claim_interface(dev, iface)
            got = bytearray()
            deadline = time.time() + 1.0
            while time.time() < deadline:
                try:
                    got += bytes(dev.read(ep_in, 16384, timeout=250))
                except usb.core.USBError:
                    pass
            usb.util.release_interface(dev, iface)
            flag = "  <-- DATA!" if got else ""
            print(f"  IF{iface}: {len(got)} bytes{flag}")
        except Exception as exc:                           # noqa: BLE001
            print(f"  IF{iface}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
