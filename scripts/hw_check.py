#!/usr/bin/env python3
"""
Static validation of the Raspberry Pi Pico 2 (RP2350) images, without the board.

For every built hardware cell (build/matrix_hw.json, written by
`build_all.py --arch rp2350_arm rp2350_rv_zbb --matrix-out build/matrix_hw.json`):

  sram_budget     image fits each MEMORY region of the linker script, with --min-margin bytes left;
                  margins reported per region and for the whole 520 KiB SRAM
  sections_in_ram every allocated section (run and load address) lies in SRAM 0x20000000-0x20082000
                  and in the region the linker script gives it
  entry           Arm: vector table at 0x20000000 with SP = __stack_top and PC = Reset_Handler (Thumb);
                  RISC-V: ELF entry = _start = lowest load address
  image_def       exactly one IMAGE_DEF block loop with the right IMAGE_TYPE (0x1021 Arm Secure /
                  0x1101 RISC-V) and a VECTOR_TABLE item -> lwc_vectors (Arm) or an ENTRY_POINT item
                  -> _start, __stack_top (RISC-V), self-linked (datasheet 5.9.3, 5.9.5)
  uf2             UF2 blocks valid: magic, family ID of the core, 256-byte payloads, every target address
                  in SRAM, contents equal to the ELF's loaded bytes (datasheet 5.5.2, 5.5.3)
  map_sections    output sections only .text .rodata .data .bss .stack (+ non-loaded metadata); every
                  loaded input section of the map is attributed to a known component
  symbol_gate     exactly one backend (check_symbols.py), re-run on the final ELF
  rotate          Zbb targets: ror/rori/rol present in the SIMON encrypt function
  isa             disassembly decodes completely for the target core (no <unknown>); Arm: no FP/VFP
                  instruction (the FPU is not enabled), no BKPT (semihosting); RISC-V: the ELF ISA
                  attribute is a subset of Hazard3's extensions, no EBREAK, only CSRs the harness needs
  same_backend    backend library/object bytes identical to the QEMU cell built with the same flags
                  (if that cell is in build/cells)

  python scripts/hw_check.py [--matrix build/matrix_hw.json] [--out-dir <dir>]
Exit status 1 if any check fails.
"""

import argparse
import csv
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_symbols  # noqa: E402
import rp2350_image  # noqa: E402
import size_report  # noqa: E402
from lwc_matrix import BUILD_DIR, LANGS, REPO_ROOT, TARGETS, find_llvm  # noqa: E402

EXPECTED_ALLOC = {".text", ".rodata", ".data", ".bss", ".stack"}
EXPECTED_META = {".ARM.attributes", ".riscv.attributes", ".symtab", ".strtab", ".shstrtab", ".comment", ""}
CODE_SECTIONS = {".text", ".rodata"}
# CSRs the RISC-V harness itself uses; all are implemented by Hazard3 (datasheet 3.8.6 CSR list)
RV_CSRS = {"mstatus", "mtvec", "mcause", "mepc", "mtval", "mcycle", "mcountinhibit"}


def objdump(elf, mcpu=None):
    cmd = [find_llvm("llvm-objdump"), "-d", "--no-show-raw-insn", str(elf)]
    if mcpu:
        cmd.insert(2, f"--mcpu={mcpu}")
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def mnemonics(disasm):
    out = []
    for line in disasm.splitlines():
        m = re.match(r"^\s*([0-9a-f]+):\s+([a-z][\w.]*)", line)
        if m:
            out.append((int(m.group(1), 16), m.group(2), line.strip()))
    return out


def rv_arch_extensions(elf):
    out = subprocess.run([find_llvm("llvm-readobj"), "--arch-specific", str(elf)],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r"Value:\s*(rv32\S+)", out)
    if not m:
        return None, out
    exts = []
    for i, tok in enumerate(m.group(1).split("_")):
        if i == 0:
            tok = tok[4:]            # 'rv32i2p1' -> 'i2p1'
        exts.append(re.sub(r"\d+p\d+$", "", tok))
    return exts, m.group(1)


def backend_digest(cell_dir):
    """SHA-256 over the backend's object code: the .o files of C/C++, the member contents of the
    Rust/Zig static library (llvm-ar p), in name order. Unlike the archive bytes this ignores
    member names and archive headers."""
    h = hashlib.sha256()
    for f in sorted((cell_dir / "obj" / "backend").glob("*.o")):
        h.update(f.read_bytes())
    for a in sorted((cell_dir / "lib").glob("*.a")):
        h.update(subprocess.run([find_llvm("llvm-ar"), "p", str(a)], capture_output=True, check=True).stdout)
    return h.hexdigest()


def check_cell(cell, matrix_cells):
    tgt = TARGETS[cell["target"]]
    hw = tgt["hardware"]
    cdir = BUILD_DIR / "cells" / cell["id"]
    elf_path, man = cdir / "firmware.elf", json.loads((cdir / "manifest.json").read_text())
    elf = rp2350_image.Elf(elf_path)
    sym = elf.symbols
    lo, hi = hw["sram"]
    res = []

    def add(name, ok, detail):
        res.append({"cell": cell["id"], "check": name, "result": "pass" if ok else "FAIL", "detail": detail})

    # sram_budget
    secs = elf.alloc_sections()
    used = {r: 0 for r in hw["regions"]}
    region_of = {}
    for name, vma, lma, size, flags in secs:
        for r, (a, b) in hw["regions"].items():
            if a <= vma < b:
                region_of[name] = r
                used[r] = max(used[r], vma + size - a)
            if lma != vma and a <= lma < b:
                used[r] = max(used[r], lma + size - a)
    parts, ok = [], True
    for r, (a, b) in hw["regions"].items():
        margin = (b - a) - used[r]
        ok &= margin >= ARGS.min_margin
        parts.append(f"{r} 0x{a:08x}: used {used[r]:,} of {b - a:,} B, margin {margin:,} B ({margin * 100 // (b - a)}%)")
    total = sum(used.values())
    parts.append(f"SRAM total used {total:,} of {hi - lo:,} B, margin {hi - lo - total:,} B")
    add("sram_budget", ok, "; ".join(parts))

    # sections_in_ram
    bad = []
    for name, vma, lma, size, flags in secs:
        for what, addr in (("run", vma), ("load", lma)):
            if not (lo <= addr and addr + size <= hi):
                bad.append(f"{name} {what} 0x{addr:08x}+{size}")
        want = "FLASH" if name in CODE_SECTIONS else "RAM"
        if region_of.get(name) != want:
            bad.append(f"{name} in region {region_of.get(name)}, expected {want}")
    add("sections_in_ram", not bad, "; ".join(bad) or
        "all allocated sections: " + ", ".join(f"{n} 0x{v:08x}-0x{v + s:08x}" + (f" (load 0x{l:08x})" if l != v else "")
                                            for n, v, l, s, _ in secs))

    # entry + image_def
    load_lo = min(a for a, _ in elf.load_segments())
    blocks = rp2350_image.find_image_defs(elf_path)
    items = {it["type"]: it for it in blocks[0]["items"]} if len(blocks) == 1 else {}
    problems = []
    if len(blocks) != 1:
        problems.append(f"{len(blocks)} valid blocks found (expected 1)")
    else:
        if blocks[0]["link"] != 0:
            problems.append(f"block link {blocks[0]['link']} (expected 0: loop to itself)")
        if items.get("IMAGE_TYPE", {}).get("value") != hw["image_type"]:
            problems.append(f"IMAGE_TYPE {items.get('IMAGE_TYPE')} != 0x{hw['image_type']:04x}")
    if hw["arch"] == "arm":
        vt = sym.get("lwc_vectors")
        img_base, img = elf.flat_image()
        sp0, pc0 = (rp2350_image.struct.unpack_from("<II", img, vt - img_base) if vt is not None else (None, None))
        e_ok = (vt == lo == load_lo and elf.entry == sym.get("Reset_Handler")
                and sp0 == sym.get("__stack_top") and pc0 == (sym.get("Reset_Handler", 0) | 1))
        add("entry", e_ok, f"vector table lwc_vectors at 0x{vt or 0:08x} (lowest load address 0x{load_lo:08x}); "
            f"[0] SP=0x{sp0 or 0:08x} (__stack_top 0x{sym.get('__stack_top', 0):08x}), [1] PC=0x{pc0 or 0:08x} "
            f"(Reset_Handler 0x{sym.get('Reset_Handler', 0):08x} | 1 Thumb); ELF entry 0x{elf.entry:08x}")
        if items and items.get("VECTOR_TABLE", {}).get("vector_table") != vt:
            problems.append(f"VECTOR_TABLE item {items.get('VECTOR_TABLE')} != lwc_vectors 0x{vt:08x}")
    else:
        st = sym.get("_start")
        add("entry", st == elf.entry == load_lo == lo,
            f"_start 0x{st or 0:08x}, ELF entry 0x{elf.entry:08x}, lowest load address 0x{load_lo:08x}")
        ep = items.get("ENTRY_POINT", {})
        if items and (ep.get("pc") != st or ep.get("sp") != sym.get("__stack_top")):
            problems.append(f"ENTRY_POINT item {ep} != _start/__stack_top")
    add("image_def", not problems, "; ".join(problems) or
        f"1 block at 0x{blocks[0]['addr']:08x}, self-linked: " +
        ", ".join(f"{it['type']}" + "".join(f" {k}=0x{v:x}" for k, v in it.items() if k not in ("type", "words"))
                  for it in blocks[0]["items"]))

    # uf2
    uf2 = rp2350_image.read_uf2(cdir / "firmware.uf2")
    base, img = elf.flat_image()
    rebuilt = b"".join(b["data"] for b in sorted(uf2, key=lambda b: b["block_no"]))[:len(img)]
    u_problems = []
    if not all(b["magic_ok"] for b in uf2):
        u_problems.append("bad magic")
    if {b["family"] for b in uf2} != {hw["uf2_family"]}:
        u_problems.append(f"family {sorted({hex(b['family']) for b in uf2})}")
    if {b["size"] for b in uf2} != {256} or [b["block_no"] for b in uf2] != list(range(len(uf2))) \
            or {b["num_blocks"] for b in uf2} != {len(uf2)}:
        u_problems.append("payload size / numbering")
    if not all(lo <= b["addr"] and b["addr"] + b["size"] <= hi for b in uf2):
        u_problems.append("block outside SRAM")
    if uf2[0]["addr"] != base or rebuilt != img:
        u_problems.append("contents differ from the ELF")
    add("uf2", not u_problems, "; ".join(u_problems) or
        f"{len(uf2)} blocks x 256 B, family 0x{hw['uf2_family']:08x}, 0x{uf2[0]['addr']:08x}-"
        f"0x{uf2[-1]['addr'] + 256:08x}, contents = ELF load image")

    # map_sections
    meta = {s["name"] for s in elf.sections if not s["flags"] & rp2350_image.SHF_ALLOC}
    debug = sorted(m for m in meta if m.startswith(".debug_"))   # not loaded; e.g. from rustup's core
    alloc = {n for n, *_ in secs}
    unexpected = sorted((alloc - EXPECTED_ALLOC) | (meta - EXPECTED_META - set(debug)))
    # Input sections of the map that size_report.py cannot attribute to a component. lld's merged
    # string/constant pools (<internal>:(.rodata.str*/.rodata.cst*), the harness's printf strings)
    # are expected; anything else is reported.
    merged, other = 0, []
    out_sec = None
    for raw in (cdir / "firmware.map").read_text(errors="replace").splitlines():
        m = size_report.LINE.match(raw)
        if not m:
            continue
        size, indent, rest = int(m.group(3), 16), len(m.group(5)), m.group(6)
        if indent <= 2:
            out_sec = rest.split()[0]
        elif ":(" in rest and size and out_sec in EXPECTED_ALLOC:
            path, sec = rest.rsplit(":(", 1)
            if size_report.component(path) == "linker":
                if path == "<internal>" and sec.startswith((".rodata.str", ".rodata.cst", ".srodata.cst")):
                    merged += size
                else:
                    other.append(f"{rest} ({size} B)")
    add("map_sections", not unexpected and not other,
        (f"unexpected sections {unexpected}; " if unexpected else "") +
        f"output sections {sorted(alloc)}; non-loaded debug sections: {len(debug)}; "
        f"merged string/constant pools {merged} B; "
        f"other unattributed input sections: {other or 'none'}")

    # symbol_gate
    gate_ok, report = check_symbols.gate(elf_path, cell["lang"])
    add("symbol_gate", gate_ok and "lwc_semihost_call" not in sym, report.splitlines()[-1] +
        ("; semihosting entry present" if "lwc_semihost_call" in sym else "; no semihosting code"))

    # rotate
    if tgt.get("rotate_insns") is not None:
        name = f"{LANGS[cell['lang']]['prefix']}_simon64_128_encrypt_block"
        out = subprocess.run([find_llvm("llvm-objdump"), "-d", "--no-show-raw-insn", f"--disassemble-symbols={name}",
                              str(elf_path)], capture_output=True, text=True, check=True).stdout
        n = len(re.findall(r"(?<![a-z])(?:ror|rori|rol)(?![a-z])", out))
        add("rotate", (n > 0) == tgt["rotate_insns"], f"{n} rotate instruction(s) in {name} (build manifest: "
            f"{man.get('rotate_instructions_simon_enc')})")

    # isa
    if hw["arch"] == "arm":
        dis = objdump(elf_path, "cortex-m33")   # RP2350 M33: FPU, DSP, Security Extension (datasheet 3.7.2)
        mn = mnemonics(dis)
        unknown = dis.count("<unknown>")
        fp = sorted({m for _, m, _ in mn if m.startswith("v")})
        bkpt = [ln for _, m, ln in mn if m == "bkpt"]
        add("isa", unknown == 0 and not fp and not bkpt,
            f"llvm-objdump --mcpu=cortex-m33: {len(mn)} instructions, <unknown> {unknown}, FP/VFP {fp or 'none'}, "
            f"BKPT {len(bkpt)}")
    else:
        exts, raw = rv_arch_extensions(elf_path)
        extra = sorted(set(exts or ["?"]) - set(hw["isa"]))
        dis = objdump(elf_path)                  # decodes with the ELF's own ISA attribute
        mn = mnemonics(dis)
        unknown = dis.count("<unknown>")
        ebreak = [ln for _, m, ln in mn if m in ("ebreak", "c.ebreak")]
        csrs = set()
        for _, m, ln in mn:
            if m.startswith("csr"):
                c = re.search(r"\b(m\w+|0x[0-9a-f]+)\b", ln.split(m, 1)[1])
                csrs.add(c.group(1) if c else "?")
        add("isa", not extra and unknown == 0 and not ebreak and csrs <= RV_CSRS,
            f"ELF ISA attribute {raw}; outside Hazard3: {extra or 'none'}; <unknown> {unknown}; EBREAK {len(ebreak)}; "
            f"CSRs used {sorted(csrs)}")

    # same_backend
    twin = cell["id"].replace(cell["target"], tgt["same_code_as"], 1)
    twin_man = BUILD_DIR / "cells" / twin / "manifest.json"
    if twin_man.exists() and json.loads(twin_man.read_text()).get("status") == "built":
        mine, other = backend_digest(cdir), backend_digest(BUILD_DIR / "cells" / twin)
        add("same_backend", mine == other,
            f"backend object contents sha256 {mine[:16]}... vs {twin} {other[:16]}... "
            "(archive members compared by content: Zig names its member after a random cache tmp dir)")
    else:
        res.append({"cell": cell["id"], "check": "same_backend", "result": "skipped",
                    "detail": f"{twin} not built in build/cells"})
    return res


def main():
    global ARGS
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--matrix", default=str(BUILD_DIR / "matrix_hw.json"))
    ap.add_argument("--out-dir", help="write hw_static_checks.csv / .md here")
    ap.add_argument("--min-margin", type=int, default=16 * 1024, help="bytes that must stay free in each region")
    ARGS = ap.parse_args()
    matrix = json.loads(Path(ARGS.matrix).read_text())
    cells = [c for c in matrix["cells"] if "hardware" in TARGETS.get(c["target"], {})]
    rows = []
    for c in cells:
        if c["status"] != "built":
            rows.append({"cell": c["id"], "check": "build", "result": "FAIL", "detail": f"{c['status']}: {c['reason']}"})
            continue
        rows += check_cell(c, cells)
    fails = [r for r in rows if r["result"] == "FAIL"]
    for r in rows:
        print(f"[{r['result']:7}] {r['cell']:36} {r['check']:16} {r['detail'][:150]}")
    print(f"\ncells: {len(cells)}  checks: {len(rows)}  failed: {len(fails)}  "
          f"skipped: {sum(r['result'] == 'skipped' for r in rows)}")
    if ARGS.out_dir:
        out = Path(ARGS.out_dir)
        out.mkdir(parents=True, exist_ok=True)
        with open(out / "hw_static_checks.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["cell", "check", "result", "detail"])
            w.writeheader()
            w.writerows(rows)
        print(f"wrote {out / 'hw_static_checks.csv'}")
    sys.exit(1 if fails or not cells else 0)


ARGS = None

if __name__ == "__main__":
    main()
