#!/usr/bin/env python3
"""Extract the full DUML command dictionary from the DJI SDK native library.

Every DUML command in libdjisdk_jni.so is a C++ template instantiation
`dji::core::dji_cmd_base_req<type, cmd_set, cmd_id, req_struct, rsp_struct>`.
The SDK is not stripped of C++ symbols, so the whole command table can be
read straight out of the binary — no decompiler needed.

    ../.venv/bin/python extract_duml_commands.py

Writes recon/duml-commands.md.
"""

import re
import subprocess
import sys
from pathlib import Path

LIB = Path("apk/lib/arm64-v8a/libdjisdk_jni.so")
OUT = Path("duml-commands.md")

TEMPLATE = re.compile(
    r"dji_cmd_base_req<"
    r"\(unsigned char\)(\d+), "      # arg 1 — cmd type/flags
    r"\(unsigned char\)(\d+), "      # arg 2 — cmd set
    r"\(unsigned char\)(\d+), "      # arg 3 — cmd id
    r"(\w+)"                          # request struct
)


def main() -> int:
    if not LIB.exists():
        print(f"missing {LIB} — extract it from the APK first")
        return 1

    raw = subprocess.run(["strings", "-n", "10", str(LIB)],
                         capture_output=True, text=True).stdout
    candidates = [ln for ln in raw.splitlines() if "dji_cmd_base_req" in ln]
    demangled = subprocess.run(["c++filt"], input="\n".join(candidates),
                               capture_output=True, text=True).stdout

    # key: (cmd_set, cmd_id) -> (type_arg, request struct name)
    cmds: dict[tuple[int, int], tuple[int, str]] = {}
    for m in TEMPLATE.finditer(demangled):
        type_arg, cmd_set, cmd_id, req = m.groups()
        name = req.removesuffix("_req")
        cmds[(int(cmd_set), int(cmd_id))] = (int(type_arg), name)

    lines = [
        "# DUML command dictionary",
        "",
        f"Extracted from `{LIB.name}` — every `dji_cmd_base_req<type, "
        "cmd_set, cmd_id, ...>` template instantiation in the SDK.",
        f"{len(cmds)} commands recovered.",
        "",
        "`type` is the first template arg (cmd type / flags); `cmd_set` and "
        "`cmd_id` are the DUML routing bytes.",
        "",
        "| cmd_set | cmd_id | type | command |",
        "|---------|--------|------|---------|",
    ]
    for (cmd_set, cmd_id) in sorted(cmds):
        type_arg, name = cmds[(cmd_set, cmd_id)]
        lines.append(f"| 0x{cmd_set:02X} | 0x{cmd_id:02X} | {type_arg} "
                     f"| `{name}` |")
    OUT.write_text("\n".join(lines) + "\n")
    print(f"wrote {OUT} — {len(cmds)} commands")
    return 0


if __name__ == "__main__":
    sys.exit(main())
