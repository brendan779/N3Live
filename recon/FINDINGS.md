# Recon findings

Running lab notebook. Newest findings at the bottom of each phase.

## P0 — USB enumeration ✅

Full descriptor in [`N3-usb-descriptor.txt`](N3-usb-descriptor.txt).

- DJI Goggles N3, **VID `0x2CA3` / PID `0x0020`**, one configuration, 8 interfaces.
- **IF0+IF1** — RNDIS network function. macOS binds it (`en3`/`en4`) but
  reports `media inactive` and never completes DHCP. macOS's partial RNDIS
  support does not bring the link up on its own → the network path is a dead
  end without significantly more work.
- **IF2** — USB mass storage (the goggles' storage as a disk).
- **IF3–IF7** — five DJI vendor-specific interfaces (`0xFF/0x43/0x01`), each a
  bulk OUT + bulk IN pair, 512-byte packets. No macOS kernel driver bound, so
  they are claimable directly via libusb.

## P1 — Vendor interface probe ✅

Tool: [`probe_vendor.py`](probe_vendor.py).

- **IF4 is the live control channel.** It pushes data with no prompting; the
  payload begins `55 4d 04 a8 …` — `0x55` is the **DUML** magic byte (DJI's
  control/telemetry protocol). An ASCII `ZV300` model string appears in it.
  IF4's bulk-OUT accepts writes, and its responses are stateful (a header
  byte changed after we wrote to it).
- **IF3, IF5, IF6, IF7 are dormant.** Their bulk-OUT endpoints time out on
  write and their bulk-IN endpoints are silent. One of them is the video
  channel; it is switched on by a command, not open by default.
- **The legacy voc-poc start packet (`0x524d5654` "RMVT") does not start
  video on the N3.** Expected — that was a V1/V2 mechanism.

### Conclusion

The N3 is driven over **DUML on IF4**. Video is enabled by sending the right
DUML command on IF4, after which one of IF3/5/6/7 should begin streaming
H.264/H.265. No RNDIS, no magic packet.

## P2 — DUML (next)

Goal: speak DUML on IF4 well enough to (a) complete whatever handshake the
goggles expect and (b) issue the "start live video" command.

Approach:
1. Implement DUML framing (`0x55` start, 13-bit length, header CRC8, payload
   CRC16, sender/receiver/seq/cmdset/cmdid).
2. Parse the packets IF4 already emits — identify heartbeats vs. queries.
3. **Reference capture:** record USB traffic between an Android device running
   DJI Fly and the N3 to observe the exact DUML start sequence. This is the
   reliable way to find the video-start command and host handshake.
4. Replay/derive the start command; confirm a video channel (IF3/5/6/7) wakes.

References for DUML: `fvantienen/dji_rev`, `samuelsadok/dji_protocol`.
