#!/usr/bin/env python3
"""
Symbol gate: proves which backend a linked image really contains.

Each image must contain exactly one backend:
  - all 8 entry points of that backend (lwc_c_ / lwc_cpp_ / lwc_rs_ / lwc_zig_) as
    defined functions with non-zero size, and
  - no symbol with any other backend's prefix, and no un-prefixed legacy entry point
    (lwc_simon64_128_init, lwc_ascon128_aead_encrypt, ...).

This is what would have caught the first campaign's bug (one function timed under three
language labels). build_all.py runs it on every image; it can also be run by hand:
    python scripts/check_symbols.py --elf build/cells/<cell>/firmware.elf --lang Rust
"""

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import LANGS, find_llvm  # noqa: E402

FUNCS = ["simon64_128_init", "simon64_128_encrypt_block", "simon64_128_decrypt_block",
         "present80_init", "present80_encrypt_block", "present80_decrypt_block",
         "ascon_aead128_encrypt", "ascon_aead128_decrypt"]
LEGACY = ["lwc_" + f for f in FUNCS] + ["lwc_ascon128_aead_encrypt", "lwc_ascon128_aead_decrypt"]


def read_symbols(elf, nm):
    """{name: (type, size)} for every symbol in the ELF."""
    out = subprocess.run([nm, "-S", "--defined-only", str(elf)], capture_output=True, text=True, check=True).stdout
    syms = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4:
            syms[parts[3]] = (parts[2], int(parts[1], 16))
        elif len(parts) == 3:
            syms[parts[2]] = (parts[1], 0)
    return syms


def gate(elf, lang, nm=None):
    """Returns (ok, report_text)."""
    nm = nm or find_llvm("llvm-nm")
    syms = read_symbols(elf, nm)
    want = LANGS[lang]["prefix"] + "_"
    others = [LANGS[l]["prefix"] + "_" for l in LANGS if l != lang]
    lines, problems = [f"symbol gate: {elf} (expect {lang}, prefix {want})"], []

    for f in FUNCS:
        name = want + f
        typ, size = syms.get(name, (None, 0))
        lines.append(f"  {name:40} {typ or '--':2} {size:6} B")
        if typ is None:
            problems.append(f"{name} missing")
        elif typ not in ("T", "t") or size == 0:
            problems.append(f"{name} is not a defined function with a size (type {typ}, size {size})")

    for name in syms:
        if any(name.startswith(p) for p in others):
            problems.append(f"foreign backend symbol in image: {name}")
        if name in LEGACY:
            problems.append(f"legacy un-prefixed symbol in image: {name}")

    if problems:
        lines.append("[GATE FAILED]")
        lines += ["  - " + p for p in problems]
        return False, "\n".join(lines)
    lines.append(f"[GATE PASSED] exactly one backend in the image: {lang}")
    return True, "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Symbol gate for one firmware image")
    ap.add_argument("--elf", required=True)
    ap.add_argument("--lang", required=True, choices=list(LANGS))
    ap.add_argument("--nm", default=None, help="path to llvm-nm (default: auto-detect)")
    args = ap.parse_args()
    ok, report = gate(args.elf, args.lang, args.nm)
    print(report)
    sys.exit(0 if ok else 3)


if __name__ == "__main__":
    main()
