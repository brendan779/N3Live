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

## P2 — DUML control (in progress)

Goal: speak DUML on IF4 well enough to (a) complete whatever handshake the
goggles expect and (b) issue the "start live video" command.

### DUML codec — done & validated

[`duml.py`](duml.py) implements DUML framing and both CRCs (CRC-8 header,
seed `0x77`; CRC-16 packet, seed `0x3692` — tables from
`o-gs/dji-firmware-tools`). The frame layout:

    0x55 | len/ver (u16 LE, 10-bit len + 6-bit ver) | crc8 |
    sender | receiver | seq (u16 LE) | cmd_type | cmd_set | cmd_id |
    payload | crc16 (u16 LE)

Validated against live IF4 bytes via [`capture_duml.py`](capture_duml.py):
every byte framed cleanly, 0 junk bytes, all CRCs pass.

### Idle baseline (no air-unit feed)

With the goggles connected but no air-unit video, IF4 emits exactly one
message type, ~1 Hz:

    cmd_set 0x00 / cmd_id 0x82   device 0xBC -> 0x2A   cmd_type 0x40
    64-byte payload: "ZV300" + status (bytes 0x05 0x1C recur at off 32/40)

This is the heartbeat. New message types appearing once the air unit is live
(and during a phone session) are the ones to chase for video control.

### Air-unit-live capture — no change

Re-ran the probe and DUML capture with the air-unit feed live. Result:
**identical to idle.** IF3/5/6/7 stay dormant; IF4 emits the same `00:82`
heartbeat with the same payload. The goggles do not react to having a feed.

**Conclusion:** the goggles passively wait for a host (DJI Fly) to drive
them. The `00:82` heartbeat (`0xBC -> 0x2A`) is the goggles announcing
themselves to the app address `0x2A` and waiting for commands. No command →
no video. There is no handshake to passively observe — the goggles never
initiate one.

### The gate: discovering DJI Fly's command sequence

This is now the critical unknown. Candidate routes:

1. **USB capture of an Android + DJI Fly session** — the gold standard.
   Needs a rootable Android device (`usbmon`) or an inline USB hardware
   sniffer. Yields the exact DUML commands.
2. **Decompile the DJI Fly APK** — the command sequence is in the code.
   No hardware needed and deterministic, but DJI Fly is large and obfuscated.
3. **Blind DUML poking from the Mac** — send plausible DUML commands as
   device `0x2A`, watch IF4 responses and IF3/5/6/7 for video. No hardware,
   can start immediately, but a large search space.

References for DUML command sets: `fvantienen/dji_rev`,
`samuelsadok/dji_protocol`, `o-gs/dji-firmware-tools`.
