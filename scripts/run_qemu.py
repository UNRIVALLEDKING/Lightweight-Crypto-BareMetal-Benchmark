#!/usr/bin/env python3
"""
Run built images under QEMU and capture their output.

For every built cell (build/matrix.json) this starts QEMU with semihosting and
deterministic instruction counting (-icount), waits for the image to exit, and writes
  <out-dir>/<cell>.r<k>.log
which starts with RUN lines added here (env=qemu, QEMU version, exact command line,
exit status, SHA-256 of the ELF that ran), followed by the image's own output.

Every log produced here is labelled env=qemu. QEMU is not cycle-accurate: under -icount
its counters advance with executed instructions (see docs/METHODOLOGY.md).

Examples:
  python scripts/run_qemu.py                         # all built cells, 2 repeats
  python scripts/run_qemu.py --cells armv8m-c-clang-O3 --repeats 1
"""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import BUILD_DIR, INSTALL_HINTS, QEMU_ICOUNT, REPO_ROOT, TARGETS, find_qemu, first_line  # noqa: E402


def qemu_command(qemu, target, elf, chardev_path):
    return [qemu, *TARGETS[target]["qemu_args"], "-nographic", "-monitor", "none", "-serial", "none",
            "-chardev", f"file,id=semihost,path={chardev_path}",
            "-semihosting-config", "enable=on,target=native,chardev=semihost",
            "-icount", QEMU_ICOUNT, "-kernel", str(elf)]


def run_one(cell, qemu, qemu_version, out_dir, repeat, timeout):
    elf = REPO_ROOT / cell["elf"] if "elf" in cell else BUILD_DIR / "cells" / cell["id"] / "firmware.elf"
    log_path = out_dir / f"{cell['id']}.r{repeat}.log"
    with tempfile.TemporaryDirectory() as tmp:
        capture = Path(tmp) / "semihost.txt"
        cmd = qemu_command(qemu, cell["target"], elf, capture.as_posix())
        start = time.time()
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            status, stderr = r.returncode, (r.stdout + r.stderr).strip()
        except subprocess.TimeoutExpired:
            status, stderr = "timeout", f"killed after {timeout}s"
        elapsed = time.time() - start
        body = capture.read_text(errors="replace") if capture.exists() else ""

    shown = [Path(cmd[0]).name] + [c if c != str(elf) else elf.relative_to(REPO_ROOT).as_posix() for c in cmd[1:]]
    shown = [c if not c.startswith("file,id=semihost") else "file,id=semihost,path=<capture>" for c in shown]
    header = [
        "RUN,env,qemu",
        f"RUN,cell,{cell['id']}",
        f"RUN,repeat,{repeat}",
        f"RUN,date_utc,{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"RUN,qemu_version,{qemu_version}",
        f"RUN,qemu_cmd,{' '.join(shown)}",
        f"RUN,icount,{QEMU_ICOUNT}",
        f"RUN,elf_sha256,{hashlib.sha256(elf.read_bytes()).hexdigest()}",
        f"RUN,host,{platform.platform()}",
        f"RUN,exit_status,{status}",
        f"RUN,wall_seconds,{elapsed:.1f}",
    ]
    if stderr:
        header.append("RUN,qemu_stderr," + stderr.replace("\n", " | ")[:500])
    log_path.write_text("\n".join(header) + "\n" + body, newline="\n")
    ok = status == 0 and "LWC_END,ok" in body
    return cell["id"], repeat, ok, status, elapsed


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cells", nargs="*", help="cell ids (default: every built cell in build/matrix.json)")
    ap.add_argument("--out-dir", default=None, help="default: results/runs/<UTC timestamp>/raw")
    ap.add_argument("--repeats", type=int, default=2, help="runs per image (identical under -icount)")
    ap.add_argument("--timeout", type=int, default=600, help="seconds per run")
    ap.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) // 2))
    args = ap.parse_args()

    matrix_file = BUILD_DIR / "matrix.json"
    if not matrix_file.exists():
        print("[FATAL] build/matrix.json not found: run scripts/build_all.py first")
        sys.exit(1)
    cells = [c for c in json.loads(matrix_file.read_text())["cells"] if c["status"] == "built"]
    if args.cells:
        cells = [c for c in cells if c["id"] in args.cells]
        missing = set(args.cells) - {c["id"] for c in cells}
        if missing:
            print(f"[FATAL] not built: {sorted(missing)}")
            sys.exit(1)

    qemu = {t: find_qemu(t) for t in {c["target"] for c in cells}}
    for t, q in qemu.items():
        if not q:
            print(f"[FATAL] {TARGETS[t]['qemu_bin']} not found. Install: {INSTALL_HINTS['qemu']}")
            sys.exit(1)
    versions = {t: first_line([q, "--version"]) for t, q in qemu.items()}

    out_dir = Path(args.out_dir) if args.out_dir else \
        REPO_ROOT / "results" / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"Running {len(cells)} image(s) x {args.repeats} under QEMU ({args.jobs} parallel) -> {out_dir}")
    for t, v in versions.items():
        print(f"  {t}: {v}")

    jobs = [(c, r) for c in cells for r in range(1, args.repeats + 1)]
    failures = []
    with ThreadPoolExecutor(max_workers=args.jobs) as pool:
        futures = [pool.submit(run_one, c, qemu[c["target"]], versions[c["target"]], out_dir, r, args.timeout)
                   for c, r in jobs]
        for f in futures:
            cid, rep, ok, status, elapsed = f.result()
            print(f"  [{'OK  ' if ok else 'FAIL'}] {cid}.r{rep}  exit={status}  {elapsed:.1f}s")
            if not ok:
                failures.append(f"{cid}.r{rep}")
    print(f"\nlogs: {out_dir}")
    if failures:
        print(f"[FAIL] {len(failures)} run(s) did not finish cleanly: {failures}")
        sys.exit(1)


if __name__ == "__main__":
    main()
