#!/usr/bin/env python3
"""
Build coordinator for the LWC language benchmark.

  --target host       C, C++, Rust and Zig shared libraries in build/host/ (correctness tests only)
  --target embedded   one firmware image per matrix cell (target x language x compiler x profile)
                      in build/cells/<cell>/: firmware.elf, firmware.map, manifest.json, build.log
                      (default: the QEMU targets; --arch rp2350_arm rp2350_rv_zbb builds the Pico 2
                      images, which also get firmware.uf2; use --matrix-out build/matrix_hw.json for
                      them so the QEMU matrix in build/matrix.json is kept)

Every image = the common harness (always the same compiler and flags) + exactly one
backend. Each cell is rebuilt from an empty directory. Commands run from the repository
root with relative paths; the exact command lines, flags and tool versions are written to
the cell's manifest.json and compiled into the image (printed as BUILD lines).

A cell whose compiler is not installed is SKIPPED (reported with an install hint), never
substituted. Use --strict to make any skipped or failed cell an error.
"""

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_symbols  # noqa: E402
import rp2350_image  # noqa: E402
from lwc_matrix import (BUILD_DIR, C_FLAGS, C_SOURCES, CPP_FLAGS, CPP_SOURCES, HARNESS_FLAGS,  # noqa: E402
                        INSTALL_HINTS, LANGS, PROFILES, QEMU_TARGETS, REPO_ROOT, TARGETS, ZIG_FLAGS, Cell,
                        all_cells, find_gcc, find_llvm, find_tool, first_line, git_commit)

HARNESS_SOURCES = ["harness/common/main.c", "harness/common/io.c", "harness/common/rt.c", "harness/common/builtins.c",
                   "harness/common/stats.c", "harness/common/backend.c", "harness/common/kat.c",
                   "harness/common/fuzz.c", "harness/common/stack.c", "harness/common/bench.c"]
KAT_HEADER = BUILD_DIR / "gen" / "lwc_kat_vectors.h"


class BuildError(Exception):
    pass


def rel(p):
    return Path(p).resolve().relative_to(REPO_ROOT).as_posix()


def run(cmd, log, env=None):
    """Runs cmd from the repository root, appends it and its output to the cell log."""
    cmd = [str(c) for c in cmd]
    log.append({"cmd": cmd})
    r = subprocess.run(cmd, cwd=REPO_ROOT, capture_output=True, text=True, env=env)
    out = (r.stdout + r.stderr).strip()
    if out:
        log[-1]["output"] = out
    if r.returncode != 0:
        raise BuildError(f"command failed ({r.returncode}): {' '.join(cmd)}\n{out[-3000:]}")
    return r


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def c_string(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
def tools(targets=None):
    t = {"clang": find_llvm("clang"), "clang++": find_llvm("clang++"), "llvm-nm": find_llvm("llvm-nm"), "llvm-objdump": find_llvm("llvm-objdump"),
         "cargo": find_tool("cargo"), "rustc": find_tool("rustc"), "zig": find_tool("zig")}
    for target in targets or QEMU_TARGETS:
        t[f"gcc:{target}"] = find_gcc(target, "gcc")
        t[f"g++:{target}"] = find_gcc(target, "g++")
    return t


def versions(t, targets=None):
    v = {}
    if t["clang"]:
        v["clang"] = first_line([t["clang"], "--version"])
    if t["rustc"]:
        out = subprocess.run([t["rustc"], "-vV"], capture_output=True, text=True).stdout
        kv = dict(line.split(": ", 1) for line in out.splitlines() if ": " in line)
        v["rustc"] = f"{first_line([t['rustc'], '--version'])} (LLVM {kv.get('LLVM version', '?')})"
    if t["zig"]:
        v["zig"] = f"zig {first_line([t['zig'], 'version'])} ({first_line([t['zig'], 'cc', '--version'])})"
    for target in targets or QEMU_TARGETS:
        if t[f"gcc:{target}"]:
            v[f"gcc:{target}"] = first_line([t[f"gcc:{target}"], "--version"])
    return v


def missing_tool(cell, t):
    """Returns (tool-key, hint) if a tool this cell needs is not installed."""
    if not t["clang"]:
        return "clang (harness compiler and linker driver)", INSTALL_HINTS["clang"]
    if not t["llvm-nm"] or not t["llvm-objdump"]:
        return "llvm-nm / llvm-objdump (symbol gate, rotate check)", INSTALL_HINTS["clang"]
    if cell.compiler == "gcc":
        key = ("gcc:" if cell.lang == "C" else "g++:") + cell.target
        if not t[key]:
            return key, INSTALL_HINTS["arm-gcc" if TARGETS[cell.target]["gcc_env"] == "ARM_GCC_BIN" else "riscv-gcc"]
    if cell.compiler == "rustc" and not (t["cargo"] and t["rustc"]):
        return "cargo/rustc", INSTALL_HINTS["cargo"]
    if cell.compiler == "zig" and not t["zig"]:
        return "zig", INSTALL_HINTS["zig"]
    return None


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------
def build_backend_c_like(cell, t, log):
    tgt = TARGETS[cell.target]
    is_cpp = cell.lang == "C++"
    sources, lang_flags = (CPP_SOURCES, CPP_FLAGS) if is_cpp else (C_SOURCES, C_FLAGS)
    if cell.compiler == "clang":
        cc, arch = t["clang++" if is_cpp else "clang"], tgt["clang"]
    else:
        cc, arch = t[("g++:" if is_cpp else "gcc:") + cell.target], tgt["gcc"]
    flags = arch + cell.prof["flags"] + lang_flags + ["-Iciphers/include"]
    objs = []
    for src in sources:
        obj = cell.dir / "obj" / "backend" / (Path(src).stem + ".o")
        obj.parent.mkdir(parents=True, exist_ok=True)
        run([cc, *flags, "-c", src, "-o", rel(obj)], log)
        objs.append(rel(obj))
    return objs, flags


def build_backend_rust(cell, t, log):
    tgt = TARGETS[cell.target]
    profile = cell.prof["cargo_profile"]
    is_opt = cell.lang == "Rust (opt)"
    sub_dir = "rust_opt" if is_opt else "rust"
    stem = "liblwc_rust_opt.a" if is_opt else "liblwc_rust.a"
    target_dir = BUILD_DIR / "cargo" / cell.target   # own dir per target: rustflags differ, the cargo triple does not
    cmd = [t["cargo"], "rustc", "--manifest-path", f"ciphers/{sub_dir}/Cargo.toml", "--lib",
           "--crate-type", "staticlib", "--profile", profile, "--target", tgt["rust_target"],
           "--target-dir", rel(target_dir), "--", *tgt["rust_flags"]]
    run(cmd, log)
    lib = target_dir / tgt["rust_target"] / profile / stem
    out = cell.dir / "lib" / stem
    out.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(lib, out)
    cargo = (REPO_ROOT / f"ciphers/{sub_dir}/Cargo.toml").read_text()
    section = cargo.split(f"[profile.{profile}]", 1)[1].split("\n[", 1)[0].strip()
    flags = [f"--profile {profile}", f"--target {tgt['rust_target']}", *tgt["rust_flags"],
             f"[profile.{profile}] {' '.join(section.split())}"]
    return [rel(out)], flags


def build_backend_zig(cell, t, log):
    tgt = TARGETS[cell.target]
    out = cell.dir / "lib" / "liblwc_zig.a"
    out.parent.mkdir(parents=True, exist_ok=True)
    flags = ["-O", cell.prof["mode"], *tgt["zig"], *ZIG_FLAGS]
    run([t["zig"], "build-lib", *flags, "--name", "lwc_zig", "--cache-dir", rel(BUILD_DIR / "zig-cache"),
         f"-femit-bin={rel(out)}", "ciphers/zig/src/main.zig"], log)
    return [rel(out)], flags


# ---------------------------------------------------------------------------
# Image
# ---------------------------------------------------------------------------
def write_headers(cell, backend_flags, ver, args):
    gen = cell.dir / "gen"
    gen.mkdir(parents=True, exist_ok=True)
    compiler_version = {"clang": ver.get("clang"), "rustc": ver.get("rustc"), "zig": ver.get("zig"),
                        "gcc": ver.get(f"gcc:{cell.target}")}[cell.compiler]
    info = [
        ("cell", cell.id), ("target", cell.target), ("lang", cell.lang), ("compiler", cell.compiler),
        ("compiler_version", compiler_version or "unknown"), ("profile", cell.profile),
        ("opt_class", cell.prof["opt_class"]), ("safety", cell.prof["safety"]),
        ("backend_flags", " ".join(backend_flags)),
        ("harness_compiler", ver["clang"]), ("harness_flags", " ".join(TARGETS[cell.target]["clang"] + HARNESS_FLAGS)),
        ("git_commit", git_commit()),
    ]
    rows = "\n".join(f"    {{{c_string(k)}, {c_string(v)}}}," for k, v in info)
    (gen / "build_info.h").write_text(
        "/* GENERATED by scripts/build_all.py -- do not edit. */\n"
        f"static const char *const lwc_build_info[][2] = {{\n{rows}\n}};\n", newline="\n")
    return dict(info)


def count_rotates(cell, objdump, log):
    """Number of RISC-V rotate instructions in the SIMON encrypt function (the cipher built from rotates)."""
    sym = f"{LANGS[cell.lang]['prefix']}_simon64_128_encrypt_block"
    out = run([objdump, "-d", "--no-show-raw-insn", f"--disassemble-symbols={sym}", rel(cell.elf)], log).stdout
    return len(re.findall(r"(?<![a-z])(?:ror|rori|rol)(?![a-z])", out))


def build_cell(cell, t, ver, args):
    if cell.dir.exists():
        shutil.rmtree(cell.dir)
    cell.dir.mkdir(parents=True)
    log = []
    tgt = TARGETS[cell.target]
    try:
        if cell.lang in ("C", "C++"):
            backend, backend_flags = build_backend_c_like(cell, t, log)
        elif cell.lang in ("Rust", "Rust (opt)"):
            backend, backend_flags = build_backend_rust(cell, t, log)
        else:
            backend, backend_flags = build_backend_zig(cell, t, log)
        info = write_headers(cell, backend_flags, ver, args)

        defines = [f"-DLWC_BACKEND_PREFIX={LANGS[cell.lang]['prefix']}",
                   f"-DLWC_BACKEND_LANG={c_string(cell.lang)}",
                   f"-DLWC_BATCHES={args.batches}", f"-DLWC_ITERS={args.iters}"]
        includes = ["-Iharness/common", *tgt.get("harness_includes", []), "-Iciphers/include",
                    f"-I{rel(cell.dir / 'gen')}", f"-I{rel(KAT_HEADER.parent)}"]
        hobjs = []
        for src in HARNESS_SOURCES + tgt["platform_srcs"]:
            obj = cell.dir / "obj" / "harness" / (Path(src).name + ".o")
            obj.parent.mkdir(parents=True, exist_ok=True)
            run([t["clang"], *tgt["clang"], *HARNESS_FLAGS, *defines, *includes, "-c", src, "-o", rel(obj)], log)
            hobjs.append(rel(obj))

        link = [t["clang"], *tgt["clang"], "-nostdlib", "-fuse-ld=lld", "-static",
                f"-Wl,-T,harness/{tgt['dir']}/link.ld", *[f"-Wl,-L,{d}" for d in tgt.get("ld_search", [])],
                "-Wl,-L,harness/common",
                "-Wl,--gc-sections", f"-Wl,-Map={rel(cell.map)}", "-Wl,--fatal-warnings",
                *hobjs, *backend]
        if cell.compiler == "gcc":   # gcc-compiled code may call libgcc helpers
            gcc = t[("g++:" if cell.lang == "C++" else "gcc:") + cell.target]
            multi = run([gcc, *tgt["gcc_libgcc"], "-print-multi-directory"], log).stdout.strip()
            if multi == ".":
                raise BuildError(f"no libgcc multilib for {tgt['gcc_libgcc']} (would link the default one)")
            libgcc = run([gcc, *tgt["gcc_libgcc"], "-print-libgcc-file-name"], log).stdout.strip()
            link.append(libgcc)
        link += ["-o", rel(cell.elf)]
        run(link, log)

        gate_ok, gate_report = check_symbols.gate(cell.elf, cell.lang, t["llvm-nm"])
        (cell.dir / "symbol_gate.txt").write_text(gate_report + "\n")
        if not gate_ok:
            raise BuildError("symbol gate failed:\n" + gate_report)

        rotates = None
        if tgt.get("rotate_insns") is not None:
            rotates = count_rotates(cell, t["llvm-objdump"], log)
            sym = f"{LANGS[cell.lang]['prefix']}_simon64_128_encrypt_block"
            (cell.dir / "symbol_gate.txt").write_text(
                gate_report + f"\nrotate instructions (ror/rori/rol) in {sym}: {rotates}\n")
            if tgt["rotate_insns"] and rotates == 0:
                raise BuildError(f"{cell.target} should use Zbb rotates but {cell.id} has none (extension not applied?)")
            if not tgt["rotate_insns"] and rotates > 0:
                raise BuildError(f"{cell.target} has no Zbb but {cell.id} contains {rotates} rotate instruction(s)")

        backend_hash = hashlib.sha256(b"".join(Path(REPO_ROOT / b).read_bytes() for b in backend)).hexdigest()
        cell.status = "built"
        cell.info = {"elf_sha256": sha256(cell.elf), "backend_sha256": backend_hash}
        if "hardware" in tgt:   # Pico 2: UF2 for the bootrom's USB drive / picotool (RAM-only image)
            uf2 = cell.dir / "firmware.uf2"
            n_blocks = rp2350_image.write_uf2(cell.elf, uf2, tgt["hardware"]["uf2_family"])
            log.append({"cmd": ["(rp2350_image.write_uf2)", rel(cell.elf), rel(uf2),
                                hex(tgt["hardware"]["uf2_family"])], "output": f"{n_blocks} UF2 blocks"})
            cell.info["uf2_sha256"] = sha256(uf2)
        manifest = {
            "cell": cell.id, "status": "built", "built_utc": datetime.now(timezone.utc).isoformat(),
            "target": cell.target, "target_desc": tgt["desc"], "lang": cell.lang, "compiler": cell.compiler,
            "profile": cell.profile, **cell.prof, "build_info": info, "tool_versions": ver,
            "elf": rel(cell.elf), "map": rel(cell.map), "rotate_instructions_simon_enc": rotates, **cell.info,
            "bench": {"batches": args.batches, "iters": args.iters},
            "commands": log,
        }
        (cell.dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    except BuildError as e:
        cell.status, cell.reason = "failed", str(e).splitlines()[0]
        (cell.dir / "manifest.json").write_text(json.dumps(
            {"cell": cell.id, "status": "failed", "error": str(e), "commands": log}, indent=2) + "\n")
    (cell.dir / "build.log").write_text("\n\n".join(
        "$ " + " ".join(e["cmd"]) + ("\n" + e["output"] if "output" in e else "") for e in log) + "\n")


def build_embedded(args):
    targets = args.arch or QEMU_TARGETS
    t = tools(targets)
    ver = versions(t, targets)
    run([sys.executable, "scripts/gen_kat_header.py", rel(KAT_HEADER)], [])
    cells = all_cells(targets, args.lang, args.compiler, args.profile)
    print(f"Building {len(cells)} cell(s). Tool versions:")
    for k, v in ver.items():
        print(f"  {k:16} {v}")
    for cell in cells:
        miss = missing_tool(cell, t)
        if miss:
            cell.status, cell.reason = "skipped", f"{miss[0]} not found; install: {miss[1]}"
            if cell.dir.exists():
                shutil.rmtree(cell.dir)
        else:
            build_cell(cell, t, ver, args)
        mark = {"built": "OK  ", "skipped": "SKIP", "failed": "FAIL"}[cell.status]
        print(f"[{mark}] {cell.id:40} {cell.reason}")

    # Report profiles whose backend code came out byte-identical (a finding, not an error).
    seen = {}
    for c in cells:
        if c.status == "built":
            seen.setdefault((c.target, c.lang, c.compiler, c.info["backend_sha256"]), []).append(c.profile)
    for (target, lang, comp, _), profs in seen.items():
        if len(profs) > 1:
            print(f"[INFO] {target} {lang}/{comp}: profiles {profs} produced identical backend code")

    matrix = {"generated_utc": datetime.now(timezone.utc).isoformat(), "git_commit": git_commit(),
              "tool_versions": ver,
              "cells": [{"id": c.id, "target": c.target, "lang": c.lang, "compiler": c.compiler,
                         "profile": c.profile, "status": c.status, "reason": c.reason, **c.info} for c in cells]}
    BUILD_DIR.mkdir(exist_ok=True)
    matrix_out = Path(args.matrix_out)
    matrix_out.write_text(json.dumps(matrix, indent=2) + "\n")
    n = {s: sum(c.status == s for c in cells) for s in ("built", "skipped", "failed")}
    print(f"\nbuilt={n['built']} skipped={n['skipped']} failed={n['failed']}  ({rel(matrix_out)})")
    if n["failed"] or (args.strict and n["skipped"]):
        sys.exit(1)


# ---------------------------------------------------------------------------
# Host libraries (correctness only)
# ---------------------------------------------------------------------------
def build_host(args):
    t = tools()
    out = BUILD_DIR / "host"
    out.mkdir(parents=True, exist_ok=True)
    ext = ".dll" if sys.platform == "win32" else ".so"
    log = []
    problems = []
    zig = t["zig"]
    if zig:
        run([zig, "cc", "-shared", "-O2", *C_FLAGS, "-Iciphers/include", *C_SOURCES,
             "-o", rel(out / f"lwc_c{ext}")], log)
        run([zig, "c++", "-shared", "-O2", *CPP_FLAGS, "-Iciphers/include", *CPP_SOURCES,
             "-o", rel(out / f"lwc_cpp{ext}")], log)
        run([zig, "build-lib", "-dynamic", "-O", "ReleaseSafe", "--name", "lwc_zig",
             "--cache-dir", rel(BUILD_DIR / "zig-cache"), f"-femit-bin={rel(out / f'lwc_zig{ext}')}",
             "ciphers/zig/src/main.zig"], log)
    else:
        problems.append(f"zig not found (used for the C, C++ and Zig host libraries): {INSTALL_HINTS['zig']}")
    if t["cargo"]:
        run([t["cargo"], "rustc", "--manifest-path", "ciphers/rust/Cargo.toml", "--lib", "--crate-type", "cdylib",
             "--release", "--target-dir", rel(BUILD_DIR / "cargo")], log)
        name = "lwc_rust.dll" if sys.platform == "win32" else "liblwc_rust.so"
        shutil.copyfile(BUILD_DIR / "cargo" / "release" / name, out / name)
        run([t["cargo"], "rustc", "--manifest-path", "ciphers/rust_opt/Cargo.toml", "--lib", "--crate-type", "cdylib",
             "--release", "--target-dir", rel(BUILD_DIR / "cargo")], log)
        name_opt = "lwc_rust_opt.dll" if sys.platform == "win32" else "liblwc_rust_opt.so"
        shutil.copyfile(BUILD_DIR / "cargo" / "release" / name_opt, out / name_opt)
    else:
        problems.append(f"cargo not found: {INSTALL_HINTS['cargo']}")
    for junk in list(out.glob("*.pdb")) + list(out.glob("*.lib")) + list(out.glob("*.exp")):
        junk.unlink()
    print("host libraries:", sorted(p.name for p in out.iterdir() if p.suffix in (".dll", ".so")))
    for p in problems:
        print("[MISSING]", p)
    if problems:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", choices=["host", "embedded", "all"], default="embedded")
    ap.add_argument("--arch", nargs="*", choices=list(TARGETS),
                    help=f"default: the QEMU targets {QEMU_TARGETS}; hardware: rp2350_arm rp2350_rv_zbb")
    ap.add_argument("--lang", nargs="*", choices=list(LANGS), help="default: all languages")
    ap.add_argument("--compiler", nargs="*", choices=["gcc", "clang", "rustc", "zig"])
    ap.add_argument("--profile", nargs="*", help="e.g. O3 Oz O3-ovf ReleaseSafe (default: all)")
    ap.add_argument("--batches", type=int, default=10, help="timing batches per operation")
    ap.add_argument("--iters", type=int, default=100, help="timed calls per batch")
    ap.add_argument("--strict", action="store_true", help="fail if any cell is skipped")
    ap.add_argument("--matrix-out", default=str(BUILD_DIR / "matrix.json"),
                    help="where to write the list of cells built (default build/matrix.json)")
    args = ap.parse_args()
    if args.profile:
        known = {p for lang in PROFILES.values() for p in lang}
        bad = set(args.profile) - known
        if bad:
            ap.error(f"unknown profile(s) {sorted(bad)}; known: {sorted(known)}")
    if args.target in ("host", "all"):
        build_host(args)
    if args.target in ("embedded", "all"):
        build_embedded(args)


if __name__ == "__main__":
    main()
