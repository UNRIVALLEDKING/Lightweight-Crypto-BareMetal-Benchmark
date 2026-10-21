#!/usr/bin/env python3
"""
Pico 2 (RP2350) preflight checklist -- runs without a board.

Prints: which hardware images are built (and their static-check status), size and SRAM margin per
image, the load address and entry, the serial settings and wiring, the loader commands, which
host tools are present, and every open TODO(verify) item in the hardware harness and scripts.
Exit status 1 if an image is missing or a static check fails (hw_check.py), else 0.

  python scripts/hw_preflight.py [--matrix build/matrix_hw.json]
"""

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rp2350_image  # noqa: E402
from lwc_matrix import BUILD_DIR, HW_TARGETS, REPO_ROOT, TARGETS, all_cells  # noqa: E402

TODO_SCAN = ["harness/rp2350_common", "harness/rp2350_arm", "harness/rp2350_rv", "scripts"]


def todo_items():
    items = []
    for d in TODO_SCAN:
        for f in sorted((REPO_ROOT / d).glob("*")):
            if f.suffix not in (".c", ".h", ".S", ".ld", ".py") or f.name == "hw_preflight.py":
                continue
            for n, line in enumerate(f.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                m = re.search(r"TODO\(verify\):?\s*(.*)", line)
                if m:
                    items.append((f"{f.relative_to(REPO_ROOT).as_posix()}:{n}", m.group(1).strip(" */\"")))
    return items


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=str(BUILD_DIR / "matrix_hw.json"))
    args = ap.parse_args()
    ok = True
    expected = [c.id for c in all_cells(HW_TARGETS)]
    built = {}
    if Path(args.matrix).exists():
        built = {c["id"]: c for c in json.loads(Path(args.matrix).read_text())["cells"] if c["status"] == "built"}

    print("PICO 2 (RP2350) HARDWARE PREFLIGHT -- no board needed, nothing is loaded\n")
    print(f"[1] Images built: {len(built)} of {len(expected)} ({args.matrix})")
    missing = [c for c in expected if c not in built]
    if missing:
        ok = False
        print(f"    MISSING: {missing}\n    -> python scripts/run_all.py hw-build")

    print("\n[2] Static checks (hw_check.py)")
    r = subprocess.run([sys.executable, str(REPO_ROOT / "scripts/hw_check.py"), "--matrix", args.matrix],
                       capture_output=True, text=True)
    summary = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr.strip()[-200:]
    print(f"    {summary}  -> {'OK' if r.returncode == 0 else 'FAILED'}")
    ok &= r.returncode == 0

    print("\n[3] Size and SRAM margin per image (SRAM 0x20000000-0x20082000, 532,480 B)")
    print(f"    {'cell':36} {'code+rodata':>11} {'margin':>8} {'data+bss+stack':>14} {'margin':>8}  load/entry")
    for cid in expected:
        if cid not in built:
            continue
        hw = TARGETS[built[cid]["target"]]["hardware"]
        elf = rp2350_image.Elf(BUILD_DIR / "cells" / cid / "firmware.elf")
        used = {k: 0 for k in hw["regions"]}
        for name, vma, lma, size, _ in elf.alloc_sections():
            for k, (a, b) in hw["regions"].items():
                for addr in {vma, lma}:
                    if a <= addr < b:
                        used[k] = max(used[k], addr + size - a)
        (fa, fb), (ra, rb) = hw["regions"]["FLASH"], hw["regions"]["RAM"]
        print(f"    {cid:36} {used['FLASH']:>11,} {fb - fa - used['FLASH']:>8,} {used['RAM']:>14,} "
              f"{rb - ra - used['RAM']:>8,}  0x{min(a for a, _ in elf.load_segments()):08x} / 0x{elf.entry:08x}")

    u = TARGETS[HW_TARGETS[0]]["hardware"]["uart"]
    print(f"""
[4] Serial console
    UART0, {u['baud']} baud, {u['format']} (8 data bits, no parity, 1 stop bit), no flow control
    Pico 2 {u['tx_pin']} = UART0 TX -> adapter RX;  {u['rx_pin']} = UART0 RX <- adapter TX;  GND -> GND
    (GP0/GP1: Pico SDK boards/pico2.h default UART pins; find them on the Pico 2 pinout)
    3.3 V logic levels only. The Pico 2's own USB port is NOT the console (no USB stack in the images).

[5] Load (image runs from SRAM; the bootrom loads RAM UF2s at 0x20000000-0x20082000, datasheet 5.5.2)
    a) BOOTSEL: hold BOOTSEL while plugging in USB -> drive "RP2350" appears
    b) default loader:  python scripts/run_all.py hw-run --port COM5 --confirm-hardware --uf2-drive E:/
       (copies build/cells/<cell>/firmware.uf2 to the drive; the board reboots into the image)
    c) alternatives:    --loader picotool   (picotool load -x <uf2> -t uf2)
                        --loader openocd    (debug probe; adjust --openocd-args)
                        --loader manual     (you copy the UF2, then press Enter)
    The images end in a loop: put the board back into BOOTSEL before each image (hw-run prompts).
    UF2 family IDs: Arm 0xe48bff59 (rp2350_arm_s), RISC-V 0xe48bff5a (rp2350_riscv), datasheet Table 469.
    RISC-V images: the bootrom switches both cores to Hazard3 when it finds a RISC-V IMAGE_DEF, keeping the
    RAM-image boot request across the switch (datasheet 5.1.20, 3.9.1), unless OTP disables it
    (BOOT_FLAGS0.DISABLE_AUTO_SWITCH_ARCH, CRIT0/CRIT1 flags; none set on a new chip, 3.9). Each log's
    BUILD,platform line (rp2350.armv8m.main / rp2350.rv32.hazard3) shows which core ran.""")

    print("\n[6] Host tools")
    for name, present in (("pyserial (python -m pip install pyserial)", importlib.util.find_spec("serial") is not None),
                          ("picotool (only for --loader picotool)", shutil.which("picotool") is not None),
                          ("openocd (only for --loader openocd)", shutil.which("openocd") is not None)):
        print(f"    {'found  ' if present else 'MISSING'} {name}")
    if importlib.util.find_spec("serial") is None:
        print("    -> hw-run needs pyserial")

    items = todo_items()
    print(f"\n[7] Open TODO(verify) items ({len(items)}) -- check against the RP2350 datasheet before trusting a run")
    for where, what in items:
        print(f"    {where}: {what}")
    print(f"\nPREFLIGHT {'OK' if ok else 'NOT READY'} (board-side items above remain unverified until the first run)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
