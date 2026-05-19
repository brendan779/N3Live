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

## P3 — APK reverse-engineering (in progress)

Route chosen: extract the DUML command set from the DJI Fly APK.

### What DJI Fly is

- Package `dji.go.v5`, 705 MB `base.apk`. A **React Native** shell over
  **546 MB of native libraries** (213 `.so` files).
- The protocol/transport/video logic lives in **`libdjisdk_jni.so` (72 MB)** —
  the DJI Mobile SDK core. Pure Java/dex decompilation would not reach it.

### The key: the SDK keeps full C++ symbols

`libdjisdk_jni.so` is **not stripped** of C++ symbols. Mining strings reveals
the whole architecture:

- Transport: `dji::core::AoaServicePort`, `AOARead` / `AOAWrite`,
  `JNI_LoadUsbAccessory` — confirms mobile mode = USB AOA.
- Live view: `ModuleMediator::StartLiveStreaming`, `PigeonLiveViewLogic`,
  `SpecialCommandManager::RequestIFrameForLiveView`, `LIVEVIEW1..5`.

### DUML commands are recoverable from the symbol table

Every DUML command is a C++ template
`dji::core::dji_cmd_base_req<type, cmd_set, cmd_id, req_struct, rsp_struct>`.
The template parameters **are** the command constants, so the whole command
dictionary can be read straight out of the demangled symbols. Video-relevant
commands found so far:

| cmd_set | cmd_id | command |
|---------|--------|---------|
| 0x08 | 0x78 | `dm368_set_sh_start_live_streaming` |
| 0x08 | 0x79 | `dm368_get_sh_get_live_streaming_setting_info` |
| 0x02 | 0x09 | `camera_set_liveview_source_camera` |
| 0x02 | 0xB3 | `camera_get_app_request_i_frame` (request an I-frame) |
| 0x02 | 0x4C | `camera_set_video_out_para` |
| 0x02 | 0x4D | `camera_get_video_out_para` |
| 0x02 | 0x18 | `camera_set_video_format` |
| 0x02 | 0x02 | `camera_record_video` |

`0x08:0x78 start_live_streaming` and `0x02:0xB3 request_i_frame` are the prime
candidates for the video-start sequence.

The full 416-command table is in [`duml-commands.md`](duml-commands.md),
generated by [`extract_duml_commands.py`](extract_duml_commands.py).

### AOA transport (mobile mode)

Relevant to the Pi-bridge route, not the Mac/OTG path. Symbols show:

- The AOA handshake itself is **standard Android Open Accessory** — the
  goggles (USB host) issue control requests 51/52/53, the device re-enumerates
  as an accessory with two bulk endpoints. The SDK does not implement this;
  Android's framework does. The SDK's `JNIUsbAccessory` just receives an
  already-open accessory file descriptor (`[AOA]onUsbConnected fd = …`).
- Over that single bulk pipe the SDK runs `dji::core::AoaServicePort`, which
  carries **both control and video** — it exposes a separate
  `IServicePortConnectionObserver` and `IServicePortConnectionVideoObserver`.
  So DUML control and the video stream are multiplexed on one pipe in mobile
  mode (unlike OTG-computer mode, which has separate vendor interfaces).
- `AOARead` / `AOAWrite` are the pipe primitives.

Implication: in mobile mode there is a framing/channel layer above DUML to
demux control vs. video. OTG-computer mode instead gives physically separate
interfaces (IF4 control, IF3/5/6/7 dormant) — simpler, and the Mac's path.

### Payload structs — partial

Exact `_req` byte layouts live in compiled code, not symbols, so full static
recovery needs Ghidra on `libdjisdk_jni.so`. What symbols/strings do show:

- The dm368 (cmd_set 0x08) commands negotiate the **decoder side** — decode
  capability, max framerate, ground-side params: the receiver tells the air
  unit what it can decode. `08:78 start_live_streaming` likely carries a
  small option payload (a `LiveStreamingSettings`-shaped struct).
- `02:B3 get_app_request_i_frame` is a request — likely empty or 1 byte —
  that prompts the camera to emit a keyframe.
- `JNI_SetLiveStreamParam` takes a raw `byte[]` — the live-stream config is
  passed through as opaque bytes.

### Probing tool — duml_send.py

[`duml_send.py`](duml_send.py) sends an arbitrary DUML command on IF4, reads
the reply, then checks IF3/5/6/7 for a woken video stream. This makes the
payloads discoverable **empirically** — a NACK / length-error reply reveals
the expected payload size far faster than static RE.

## P4 — Driving the goggles (hardware probing)

Probed with the air unit live and the goggles in OTG-computer mode, using
`duml_send.py` and `duml_scan.py`.

### Our DUML stack works

`duml_send.py 00 01` (`get_version` → `0xBC`) round-trips cleanly: reply
`type=0xC0`, payload status `0x00`, ASCII `"zv300 gl Ver.02"`. Codec,
addressing (`0x2A`↔`0xBC`), cmd_type `0x40`→`0xC0`, and seq echo all confirmed.

### The whole DUML mesh is reachable

`duml_scan.py` swept get_version across all 256 receiver addresses — **14
modules answered**, so the goggles relay DUML across the wireless link to the
aircraft:

| addr | identity |
|------|----------|
| 0x09, 0x29 | `za530 uav` — the air unit |
| 0x0E, 0x2E | `zv300_gls rc` |
| 0x1C | `WM150 GL` |
| 0x1F | `zv300 gl Ver.A` |
| 0x3C, 0xBC | `zv300 gl Ver.02` — the goggles |
| 0x59 | `bsp001` |
| 0x6E | `zv300 gfsk v00` — the radio link |
| 0x8E | `multi-type GND` |
| 0x9C | (binary) |

Address byte = `(index << 5) | type`.

### But raw command firing does not start video

- Functional commands (`08:78 start_live_streaming`, `08:75/79`,
  `02:B3 request_i_frame`, `02:09`, `02:4D`) sent to `0xBC` → reply status
  **`0xE0`** (rejected — the goggles module doesn't implement them).
- The same commands sent to `0x09` (the air unit) → **no reply at all**.
- No video interface (IF3/5/6/7) ever woke.

### Conclusion / next

`get_version` works everywhere because every DUML node answers it. The
functional commands need more than a raw frame — the SDK performs a
**session/registration handshake** and routes each command to a specific
module/sub-address. Reconstructing that is the next target:

1. Ghidra pass on `libdjisdk_jni.so` — trace `PigeonLiveViewLogic::Start` /
   `ModuleMediator::StartLiveStreaming` to recover the exact command order,
   target addresses and payloads.
2. Or capture a real DJI Fly session (Pi-bridge / hardware sniffer) to
   observe the sequence directly.

The Mac-direct path is **not** ruled out — the air unit is reachable from the
Mac; we just need the correct command sequence.
