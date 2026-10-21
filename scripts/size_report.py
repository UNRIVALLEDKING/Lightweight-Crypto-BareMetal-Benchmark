#!/usr/bin/env python3
"""
Size report from the linker map (ld.lld -Map, after --gc-sections).

Every input section that survived garbage collection is attributed to a component:
  backend          the cipher backend itself (C/C++ objects, the lwc_rust crate, lwc_zig)
  backend_runtime  language/compiler runtime pulled in BY the backend library
                   (Rust core / compiler_builtins members of the staticlib, libgcc)
  harness_runtime  memcpy/memset/... and 64-bit shift helpers (rt.c, builtins.c), identical
                   in every image; which of them an image needed is listed in Helpers
  harness_kat      KAT vectors and KAT code (kat.c)
  harness          the rest of the harness (same in every image of a target)
and to an output section class (text, rodata, data, bss). The backend is further split by
cipher using section names (best effort; "shared" when a section names no cipher).

All images are linked by ld.lld (also gcc-compiled cells), so only the lld map format
is parsed.

Usage:
  size_report.py --cells build/cells/*      -> results/size/size_report.csv (+ per-cipher CSV)
  size_report.py --map firmware.map         -> print one image
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import REPO_ROOT  # noqa: E402

LINE = re.compile(r"^\s*([0-9a-f]+)\s+([0-9a-f]+)\s+([0-9a-f]+)\s+(\d+)(\s+)(\S.*)$")
CLASSES = {".text": "text", ".rodata": "rodata", ".data": "data", ".bss": "bss"}
HELPER_OBJS = ("rt.c.o", "builtins.c.o")


def component(path):
    p = path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    if "/obj/backend/" in p:
        return "backend"
    if "liblwc_rust.a(" in p:
        member = p.split("liblwc_rust.a(", 1)[1]
        return "backend" if member.startswith("lwc_rust") else "backend_runtime"
    if "liblwc_rust_opt.a(" in p:
        member = p.split("liblwc_rust_opt.a(", 1)[1]
        return "backend" if member.startswith("lwc_rust_opt") else "backend_runtime"
    if "liblwc_zig.a(" in p or p.endswith("liblwc_zig.a"):
        return "backend"
    if "libgcc" in p or "libclang_rt" in p:
        return "backend_runtime"
    if "/obj/harness/" in p:
        if name in HELPER_OBJS:
            return "harness_runtime"
        if name == "kat.c.o":
            return "harness_kat"
        return "harness"
    return "linker"


def cipher_of(section):
    s = section.lower()
    for key, cipher in (("simon", "SIMON64_128"), ("present", "PRESENT80"), ("ascon", "ASCON_AEAD128")):
        if key in s:
            return cipher
    return "shared"


def parse_map(map_path):
    """Returns (totals[(component, class)] -> bytes, backend[(cipher, class)] -> bytes,
    helper symbol names, stack size)."""
    totals, backend = defaultdict(int), defaultdict(int)
    helpers, stack = set(), 0
    out_section, in_component = None, None
    for raw in Path(map_path).read_text(errors="replace").splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        size, indent, rest = int(m.group(3), 16), len(m.group(5)), m.group(6)
        if indent <= 2:                                  # output section
            out_section = rest.split()[0]
            if out_section == ".stack":
                stack = size
            continue
        if ":(" in rest:                                 # input section: <file>:(<section>)
            path, section = rest.rsplit(":(", 1)
            section = section.rstrip(")")
            cls = CLASSES.get(out_section)
            in_component = component(path)
            if cls is None or size == 0:
                continue
            totals[(in_component, cls)] += size
            if in_component == "backend":
                backend[(cipher_of(section), cls)] += size
        elif in_component == "harness_runtime" and not rest.startswith(("$", ".L")):
            helpers.add(rest.strip())                    # symbol line under a helper section
    return totals, backend, helpers, stack


COMPONENTS = ["backend", "backend_runtime", "harness_runtime", "harness_kat", "harness", "linker"]


def cell_rows(cell_dir):
    manifest = json.loads((cell_dir / "manifest.json").read_text())
    if manifest.get("status") != "built":
        return None, None
    totals, backend, helpers, stack = parse_map(cell_dir / "firmware.map")
    base = {k: manifest[k] for k in ("cell", "target", "lang", "compiler", "profile", "opt_class", "safety")}
    row = dict(base)
    for comp in COMPONENTS:
        for cls in CLASSES.values():
            row[f"{comp}_{cls}"] = totals.get((comp, cls), 0)
    row["backend_flash"] = sum(totals.get(("backend", c), 0) for c in ("text", "rodata", "data"))
    row["backend_ram"] = sum(totals.get(("backend", c), 0) for c in ("data", "bss"))
    row["backend_runtime_flash"] = sum(totals.get(("backend_runtime", c), 0) for c in ("text", "rodata", "data"))
    row["image_flash"] = sum(v for (comp, cls), v in totals.items() if cls in ("text", "rodata", "data"))
    row["image_ram"] = sum(v for (comp, cls), v in totals.items() if cls in ("data", "bss"))
    row["stack_reserved"] = stack
    row["helpers"] = " ".join(sorted(helpers))
    per_cipher = []
    for cipher in ("SIMON64_128", "PRESENT80", "ASCON_AEAD128", "shared"):
        r = dict(base, cipher=cipher)
        for cls in CLASSES.values():
            r[cls] = backend.get((cipher, cls), 0)
        r["flash"] = r["text"] + r["rodata"] + r["data"]
        per_cipher.append(r)
    return row, per_cipher


def write_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", nargs="*", help="cell directories (default: every built cell)")
    ap.add_argument("--map", help="print the breakdown of a single map file")
    ap.add_argument("--output", default=str(REPO_ROOT / "results" / "size" / "size_report.csv"))
    args = ap.parse_args()

    if args.map:
        totals, backend, helpers, stack = parse_map(args.map)
        for (comp, cls), v in sorted(totals.items()):
            print(f"{comp:16} {cls:7} {v:8}")
        print("backend by cipher:", dict(backend))
        print("helpers:", sorted(helpers), "stack reserved:", stack)
        return

    dirs = [Path(d) for d in args.cells] if args.cells else sorted((REPO_ROOT / "build" / "cells").glob("*"))
    rows, ciphers = [], []
    for d in dirs:
        if not (d / "manifest.json").exists():
            continue
        row, per_cipher = cell_rows(d)
        if row:
            rows.append(row)
            ciphers += per_cipher
    if not rows:
        print("[FATAL] no built cells found")
        sys.exit(1)
    out = Path(args.output)
    write_csv(out, rows)
    write_csv(out.with_name(out.stem + "_by_cipher.csv"), ciphers)
    print(f"{'cell':40} {'backend':>8} {'bk_rt':>6} {'image':>7}  helpers")
    for r in rows:
        print(f"{r['cell']:40} {r['backend_flash']:8} {r['backend_runtime_flash']:6} {r['image_flash']:7}  {r['helpers']}")
    print(f"\nwrote {out} and {out.with_name(out.stem + '_by_cipher.csv')}")


if __name__ == "__main__":
    main()
