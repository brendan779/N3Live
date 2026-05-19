# N3Live

Live FPV video from the **DJI Goggles N3** on macOS — plug the goggles into a
Mac over USB-C and watch the feed in a window.

> **Status: research / experimental.** There is no working build yet. This
> repository currently holds the feasibility findings and the implementation
> plan. See [Project status](#project-status).

## The goal

The DJI Goggles N3 have no official desktop video-out. Their only sanctioned
"Live View" path is a USB-C tether to a **phone** running DJI Fly. N3Live aims
to reimplement that path on macOS so the feed can be shown in a native window —
and, eventually, fed straight into [Skyline](https://github.com/brendan779/SkylineOverlay)
as a live video backdrop.

## Feasibility summary

Getting the N3 feed on a Mac is **possible but is a reverse-engineering
effort** — not a wiring-up of an existing library.

- **No UVC / webcam mode.** The N3 does not present as a standard camera; it
  cannot just be opened in QuickTime or captured with AVFoundation directly.
- **Existing open-source tools don't cover the N3.** `fpv-wtf/voc-poc`,
  `fpvout/fpvout-cpp` and `fpvout/DigiView-Android` work only on the original
  DJI FPV Goggles V1/V2, via a USB bulk-endpoint magic packet (`0x524d5654`)
  the newer goggles no longer accept.
- **Newer goggles use a USB network link.** When connected to a computer the
  N3 (like the G2/G3/Integra) opens an **RNDIS USB network connection** — the
  host is given an IP in `192.168.42.*` — and the video is pulled over a
  proprietary DJI protocol.
- **It is provably extractable.** The commercial *Cosmostreamer* product does
  N3 video-out today (on a Raspberry Pi). The protocol is closed and nobody
  has published an open-source N3 path — that gap is what N3Live fills.

### Risks

1. **macOS + RNDIS.** RNDIS is a Windows protocol; macOS (especially Apple
   Silicon) does not enumerate it natively. The mitigation is to bypass the OS
   network stack and talk to the goggles' USB endpoints directly with
   **libusb**, which works on Apple Silicon without a kernel extension.
2. **A reference capture is required.** Learning the handshake and stream
   format needs the USB traffic between an Android phone running DJI Fly and
   the N3 to be recorded and analysed.

## Plan

| Phase | Goal |
|-------|------|
| **P0 — Recon** | With a live feed running (drone/air unit on), connect the N3 in OTG mode; dump `system_profiler SPUSBDataType` / `ioreg` to capture VID/PID, interface classes and endpoints. Repeat idle (no air unit) to diff. This decides the whole architecture. |
| **P1 — Capture** | Record USB traffic between a phone + DJI Fly + N3; identify the handshake and the video port/codec (expected H.264/H.265 + DJI's "DUML" control protocol). |
| **P2 — Client** | Reimplement the handshake and stream pull over libusb. |
| **P3 — Decode + display** | Feed the bitstream into VideoToolbox → an `AVSampleBufferDisplayLayer` window. |
| **P4 — Polish** | Native SwiftUI macOS app; optional Skyline live-backdrop integration. |

## Hardware / tooling needed

- DJI Goggles N3 + a USB-C ↔ USB-C data cable.
- **The drone / O4 air unit, powered on and bound to the goggles.** The
  goggles only enable their video-out (broadcast) mode while they are
  actually receiving a feed — with no air unit linked there is nothing to
  stream, so all recon and testing must be done with the full FPV system
  live.
- An Android phone with DJI Fly (for the P1 reference capture).
- Likely a USB protocol analyser or a Linux box with `usbmon` for the capture.

> **Test rig.** Every capture session = Goggles N3 + drone/air unit powered
> and linked (live feed visible in the goggles), *then* plug into the Mac.
> The goggles' exposed USB interfaces and endpoints may differ between idle
> and broadcasting, so P0 should be run both ways for comparison.

## Prior art / references

- [fpv-wtf/voc-poc](https://github.com/fpv-wtf/voc-poc) — V1/V2 USB video PoC.
- [fpvout/DigiView-Android](https://github.com/fpvout/DigiView-Android) — V1/V2 Android viewer.
- [Amzd/DJI-FPV-Goggles](https://github.com/Amzd/DJI-FPV-Goggles) — early RNDIS reverse-engineering notes.
- [Cosmostreamer](https://cosmostreamer.com/products/djigoggles2/) — commercial N3-capable reference (closed source).

## Legal note

This project is for personal interoperability — watching your own goggles'
feed on your own computer. It reimplements a protocol through observation; it
ships no DJI code or firmware.

## Project status

Nothing is implemented yet. Phase P0 (recon) is the next action and needs the
physical goggles connected to the Mac.
