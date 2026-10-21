#!/usr/bin/env python3
"""
End-to-end pipeline: host correctness -> build matrix -> QEMU -> validate -> sizes -> summary.

  1. host libraries (C, C++, Rust, Zig) + KATs, 1,089 official Ascon-AEAD128 vectors,
     differential fuzz (writes the reference digest)
  2. build every cell of language x compiler x profile x target (skips cells whose
     compiler is not installed, and says so)
  3. run every built image under QEMU (--repeats times)
  4. validate the logs and write CSVs (parse_log.py), size report from the maps
  5. write results/runs/<run id>/SUMMARY.md

Everything of one run goes to results/runs/<run id>/:
  raw/*.log  benchmark.csv  stack.csv  checks.csv  coverage.csv  size_report*.csv
  matrix.json  manifests/  host_digest.json  pipeline.log  SUMMARY.md

All numbers produced here are labelled env=qemu. QEMU is not cycle-accurate; read
docs/METHODOLOGY.md before using them.
"""

import argparse
import csv
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import BUILD_DIR, LANGS, QEMU_TARGETS, REPO_ROOT, TARGETS  # noqa: E402

PY = sys.executable


class Pipeline:
    def __init__(self, run_dir):
        self.run_dir = run_dir
        self.log = open(run_dir / "pipeline.log", "w", encoding="utf-8")
        self.failed = []

    def step(self, name, cmd, fatal=True):
        banner = f"\n{'=' * 78}\n  STEP: {name}\n  $ {' '.join(str(c) for c in cmd)}\n{'=' * 78}"
        print(banner, flush=True)
        self.log.write(banner + "\n")
        r = subprocess.run([str(c) for c in cmd], cwd=REPO_ROOT, capture_output=True, text=True)
        out = r.stdout + r.stderr
        print(out[-6000:], end="", flush=True)
        self.log.write(out)
        self.log.flush()
        if r.returncode != 0:
            msg = f"[{'FATAL' if fatal else 'FAILED'}] {name} (exit {r.returncode})"
            print(msg)
            self.log.write(msg + "\n")
            self.failed.append(name)
            if fatal:
                sys.exit(r.returncode)
        return r.returncode


def write_summary(run_dir, run_id, args):
    matrix = json.loads((run_dir / "matrix.json").read_text())
    rows = list(csv.DictReader(open(run_dir / "benchmark.csv"))) if (run_dir / "benchmark.csv").exists() else []
    sizes = {r["cell"]: r for r in csv.DictReader(open(run_dir / "size_report.csv"))} \
        if (run_dir / "size_report.csv").exists() else {}
    stack = defaultdict(int)
    if (run_dir / "stack.csv").exists():
        for r in csv.DictReader(open(run_dir / "stack.csv")):
            stack[r["cell"]] = max(stack[r["cell"]], int(r["stack_bytes"]))
    coverage = list(csv.DictReader(open(run_dir / "coverage.csv"))) if (run_dir / "coverage.csv").exists() else []
    med = {(r["cell"], r["op"]): float(r["median_metric"]) for r in rows}
    qemu = rows[0]["qemu_version"] if rows else "?"

    ops = [("SIMON64_ENC", 8), ("PRESENT80_ENC", 8), ("ASCON_AEAD128_ENC_16B", 16), ("ASCON_AEAD128_ENC_1024B", 1024)]
    lines = [
        f"# Run {run_id}",
        "",
        "**Environment: `qemu`. These are QEMU instruction counts (`-icount`), not CPU cycles.**",
        "They measure how many instructions each build executes; they say nothing about pipeline",
        "stalls, memory wait states or branch costs of real silicon. See docs/METHODOLOGY.md.",
        "",
        f"- git commit: `{matrix.get('git_commit')}`",
        f"- QEMU: {qemu}, `-icount {rows[0]['icount'] if rows else '?'}`",
        f"- repeats per image: {args.repeats} (required to be identical)",
    ]
    for k, v in matrix["tool_versions"].items():
        lines.append(f"- {k}: {v}")
    lines += ["", "## Coverage", "", "| cell | status | reason |", "|---|---|---|"]
    for c in coverage:
        lines.append(f"| {c['cell']} | {c['status']} | {c['reason'][:120]} |")
    for target in TARGETS:
        cells = [c["id"] for c in matrix["cells"] if c["target"] == target and any(k[0] == c["id"] for k in med)]
        if not cells:
            continue
        lines += ["", f"## {target}: {TARGETS[target]['desc']}", "",
                  "Median instructions per call, timer overhead subtracted (Ascon 1024 B also per byte). "
                  "Backend flash = backend text+rodata+data from the linker map (excludes the shared "
                  "harness helpers). Stack = deepest call of any operation, probe baseline subtracted.", "",
                  "| cell | SIMON enc | PRESENT enc | Ascon enc 16 B | Ascon enc 1 KiB | per byte | backend flash B | + runtime B | stack B |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
        for cid in cells:
            vals = [med.get((cid, op)) for op, _ in ops]
            per_byte = vals[3] / 1024 if vals[3] else None
            s = sizes.get(cid, {})
            fmt = lambda v: f"{v:,.0f}" if v is not None else "-"  # noqa: E731
            lines.append(f"| {cid} | " + " | ".join(fmt(v) for v in vals) +
                         f" | {per_byte:.1f} | {s.get('backend_flash', '-')} | {s.get('backend_runtime_flash', '-')} | "
                         f"{stack.get(cid, '-')} |")
    (run_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", newline="\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--arch", nargs="*", choices=QEMU_TARGETS, help="QEMU targets only (default: all three)")
    ap.add_argument("--lang", nargs="*", choices=list(LANGS))
    ap.add_argument("--compiler", nargs="*", choices=["gcc", "clang", "rustc", "zig"])
    ap.add_argument("--profile", nargs="*")
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--skip-host", action="store_true", help="reuse build/host and its fuzz digest")
    ap.add_argument("--strict", action="store_true", help="fail if any cell is skipped (e.g. gcc missing)")
    ap.add_argument("--run-id", help="name of the results/runs/ folder (default: UTC timestamp); must not exist")
    args = ap.parse_args()

    run_id = args.run_id or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = REPO_ROOT / "results" / "runs" / run_id
    run_dir.mkdir(parents=True)   # FileExistsError if it exists: a run never overwrites another
    p = Pipeline(run_dir)
    print(f"Pipeline run {run_id} -> {run_dir}")

    if not args.skip_host:
        p.step("1a. Build host libraries", [PY, "scripts/build_all.py", "--target", "host"])
        p.step("1b. Host KATs (vectors/*.json)", [PY, "host/run_vectors.py"])
        p.step("1c. Official Ascon-AEAD128 KAT (1,089 vectors)", [PY, "host/run_official_ascon_kat.py"])
        p.step("1d. Host differential fuzz + reference digest", [PY, "host/differential.py"])

    filters = []
    for opt in ("arch", "lang", "compiler", "profile"):
        if getattr(args, opt):
            filters += [f"--{opt}", *getattr(args, opt)]
    p.step("2. Build the embedded matrix", [PY, "scripts/build_all.py", "--target", "embedded", *filters,
                                            *(["--strict"] if args.strict else [])])
    shutil.copyfile(BUILD_DIR / "matrix.json", run_dir / "matrix.json")
    shutil.copyfile(BUILD_DIR / "host" / "fuzz_digest.json", run_dir / "host_digest.json")
    mdir = run_dir / "manifests"
    mdir.mkdir()
    built = [c["id"] for c in json.loads((BUILD_DIR / "matrix.json").read_text())["cells"] if c["status"] == "built"]
    for cid in built:
        shutil.copyfile(BUILD_DIR / "cells" / cid / "manifest.json", mdir / f"{cid}.json")
        shutil.copyfile(BUILD_DIR / "cells" / cid / "symbol_gate.txt", mdir / f"{cid}.symbol_gate.txt")

    p.step("3. Run every image under QEMU", [PY, "scripts/run_qemu.py", "--cells", *built,
                                             "--repeats", str(args.repeats), "--out-dir", run_dir / "raw"], fatal=False)
    p.step("4a. Validate logs -> CSV", [PY, "scripts/parse_log.py", "--input", run_dir / "raw", "--out-dir", run_dir,
                                        "--host-digest", run_dir / "host_digest.json"], fatal=False)
    p.step("4b. Size report from linker maps", [PY, "scripts/size_report.py", "--cells",
                                                *[BUILD_DIR / "cells" / c for c in built],
                                                "--output", run_dir / "size_report.csv"], fatal=False)
    write_summary(run_dir, run_id, args)
    print(f"\nSummary: {run_dir / 'SUMMARY.md'}")
    if p.failed:
        print(f"[FAIL] steps with errors: {p.failed}")
        sys.exit(1)
    print("[OK] pipeline finished; every accepted row is labelled env=qemu")


if __name__ == "__main__":
    main()
