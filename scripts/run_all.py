#!/usr/bin/env python3
"""
One entry point for the whole study. Wraps the existing steps; it does not reimplement them.

  python scripts/run_all.py qemu                 # host checks + build + run the 45 QEMU cells (--strict),
                                                 # validate, sizes, regression vs RUN-004, metrics_summary.csv
  python scripts/run_all.py hw-build             # build the 30 Pico 2 cells + static checks (no board needed)
  python scripts/run_all.py hw-run --port COM5 --confirm-hardware
                                                 # load each Pico 2 image, capture UART, validate (board needed)

Every invocation writes a NEW folder results/runs/<run id>/ (refuses to reuse one) containing what the
wrapped steps write plus:
  metrics_summary.csv   one row per cell x cipher x operation:
                        run_id, env, target, lang, compiler, profile, opt_class, safety, cipher, op, bytes,
                        metric_kind, metric_median, flash_bytes, static_ram_bytes, stack_bytes, git_commit
                        metric_kind is qemu_instructions (env=qemu) or cpu_cycles (env=hardware), never mixed.
  REPORT.md             gates passed/failed, headline metrics, file list
Options common to all modes: --run-id, --log (append a DRAFT row to docs/MEASUREMENT_LOG.md; never
rewrites an existing row). Exit status is non-zero if any gate fails.

Definitions used in metrics_summary.csv:
  metric_median    median per call, timer overhead subtracted (benchmark.csv median_metric)
  flash_bytes      backend text+rodata+data attributed to the cipher by section name
                   (size_report_by_cipher.csv; tables and helpers that name no cipher are in "shared")
  static_ram_bytes backend data+bss attributed to the cipher
  stack_bytes      stack watermark of the operation, probe baseline subtracted (stack.csv); Ascon is
                   probed once per direction with 1,024 B, that value is given for every Ascon length
"""

import argparse
import csv
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import BUILD_DIR, HW_TARGETS, QEMU_TARGETS, REPO_ROOT, TARGETS, git_commit  # noqa: E402

PY = sys.executable
RUNS = Path(os.environ.get("LWC_RUNS_DIR", REPO_ROOT / "results" / "runs"))   # override: tests only
BASELINE = REPO_ROOT / "results" / "runs" / "20261009T030619Z"               # RUN-004
HW_MATRIX = BUILD_DIR / "matrix_hw.json"
MEASUREMENT_LOG = REPO_ROOT / "docs" / "MEASUREMENT_LOG.md"
SUMMARY_COLS = ["run_id", "env", "target", "lang", "compiler", "profile", "opt_class", "safety", "cipher", "op",
                "bytes", "metric_kind", "metric_median", "flash_bytes", "static_ram_bytes", "stack_bytes", "git_commit"]
HEADLINE_OPS = {"SIMON64_128": "SIMON64_ENC", "PRESENT80": "PRESENT80_ENC", "ASCON_AEAD128": "ASCON_AEAD128_ENC_1024B"}
OPS_PER_CELL = 14
STACK_OPS_PER_CELL = 8


class Gates:
    """Every check of the run, in order; any failure makes the exit status non-zero."""

    def __init__(self, run_dir):
        self.run_dir, self.rows = run_dir, []

    def add(self, name, ok, detail=""):
        self.rows.append((name, "pass" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name}{': ' + detail if detail else ''}", flush=True)
        return ok

    @property
    def failed(self):
        return [r for r in self.rows if r[1] == "FAIL"]


def step(gates, name, cmd, log):
    """Runs one wrapped script, tees its output to run_dir/run_all.log, records a gate."""
    shown = " ".join(str(c) for c in cmd)
    print(f"\n=== {name}\n$ {shown}", flush=True)
    log.write(f"\n=== {name}\n$ {shown}\n")
    r = subprocess.run([str(c) for c in cmd], cwd=REPO_ROOT, capture_output=True, text=True)
    out = r.stdout + r.stderr
    log.write(out)
    log.flush()
    print(out[-4000:], end="", flush=True)
    gates.add(name, r.returncode == 0, f"exit {r.returncode}")
    return r


def new_run_dir(run_id):
    run_dir = RUNS / run_id
    if run_dir.exists():
        sys.exit(f"[FATAL] {run_dir} exists; a run never reuses or overwrites a results folder")
    return run_dir


def read_csv(path):
    if not Path(path).exists():
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, cols):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def cipher_of_op(op):
    for prefix, cipher in (("SIMON64_", "SIMON64_128"), ("PRESENT80_", "PRESENT80"), ("ASCON_AEAD128_", "ASCON_AEAD128")):
        if op.startswith(prefix):
            return cipher
    return None


def stack_op(op):
    """benchmark op -> stack.csv op (Ascon is probed once per direction, with 1,024 B)."""
    m = re.match(r"(ASCON_AEAD128_(?:ENC|DEC))_\d+B$", op)
    return m.group(1) if m else op


def metrics_summary(gates, run_dir, run_id):
    """metrics_summary.csv from benchmark.csv + size_report_by_cipher.csv + stack.csv; the completeness gate."""
    bench = read_csv(run_dir / "benchmark.csv")
    sizes = {(r["cell"], r["cipher"]): r for r in read_csv(run_dir / "size_report_by_cipher.csv")}
    stack = {(r["cell"], r["op"]): r["stack_bytes"] for r in read_csv(run_dir / "stack.csv")}
    accepted = [r["cell"] for r in read_csv(run_dir / "coverage.csv") if r["status"] == "accepted"]
    kinds = {r["metric_kind"] for r in bench}
    gates.add("one metric kind per table", len(kinds) <= 1, f"metric_kind values: {sorted(kinds)}")

    rows, missing = [], []
    for r in bench:
        cipher = cipher_of_op(r["op"])
        size = sizes.get((r["cell"], cipher))
        st = stack.get((r["cell"], stack_op(r["op"])))
        if size is None:
            missing.append(f"{r['cell']} {cipher}: size")
        if st is None:
            missing.append(f"{r['cell']} {r['op']}: stack")
        rows.append({
            "run_id": run_id, "env": r["env"], "target": r["target"], "lang": r["lang"], "compiler": r["compiler"],
            "profile": r["profile"], "opt_class": r["opt_class"], "safety": r["safety"], "cipher": cipher,
            "op": r["op"], "bytes": r["bytes"], "metric_kind": r["metric_kind"], "metric_median": r["median_metric"],
            "flash_bytes": size["flash"] if size else "",
            "static_ram_bytes": int(size["data"]) + int(size["bss"]) if size else "",
            "stack_bytes": st if st is not None else "", "git_commit": r["git_commit"]})
    per_cell = defaultdict(int)
    for r in bench:
        per_cell[r["cell"]] += 1
    for cell in accepted:
        if per_cell[cell] != OPS_PER_CELL:
            missing.append(f"{cell}: {per_cell[cell]} of {OPS_PER_CELL} operations")
        if sum(1 for (c, _) in stack if c == cell) != STACK_OPS_PER_CELL:
            missing.append(f"{cell}: stack probes incomplete")
    rows.sort(key=lambda r: (r["target"], r["lang"], r["compiler"], r["profile"], r["cipher"], r["op"]))
    write_csv(run_dir / "metrics_summary.csv", rows, SUMMARY_COLS)
    gates.add("metric completeness", bool(accepted) and not missing,
              f"{len(accepted)} accepted cells, {len(rows)} rows" + (f"; missing: {missing[:10]}" if missing else ""))
    return rows


def headline(rows):
    """Per target and cipher: range over cells of the headline op's metric, flash and stack."""
    lines = []
    by = defaultdict(list)
    for r in rows:
        if r["op"] == HEADLINE_OPS.get(r["cipher"]):
            by[(r["target"], r["cipher"])].append(r)
    for (target, cipher), rs in sorted(by.items()):
        def rng(key):
            v = sorted(float(r[key]) for r in rs if r[key] != "")
            return f"{v[0]:,.0f}-{v[-1]:,.0f}" if v else "-"
        lines.append(f"| {target} | {cipher} | {HEADLINE_OPS[cipher]} | {rs[0]['metric_kind']} | {rng('metric_median')} | "
                     f"{rng('flash_bytes')} | {rng('stack_bytes')} | {len(rs)} |")
    return ["| target | cipher | op | metric kind | median (min-max over cells) | flash B | stack B | cells |",
            "|---|---|---|---|---:|---:|---:|---:|"] + lines


def write_report(gates, run_dir, run_id, mode, rows, extra=()):
    cov = read_csv(run_dir / "coverage.csv")
    n_acc = sum(r["status"] == "accepted" for r in cov)
    lines = [f"# run_all.py {mode}: {run_id}", "",
             f"- git commit: `{git_commit()}`",
             f"- host: {platform.platform()}, Python {platform.python_version()}",
             f"- cells: {len(cov)} in coverage.csv, {n_acc} accepted, {len(cov) - n_acc} not accepted", ""]
    if rows:
        kind = rows[0]["metric_kind"]
        lines += [("**env=qemu: QEMU instruction counts (`-icount`), not CPU cycles.**" if kind == "qemu_instructions"
                   else "**env=hardware: core clock cycles on the Pico 2. Never compare with qemu rows.**"), ""]
        lines += ["## Headline metrics", ""] + headline(rows) + [""]
    lines += [*extra, "## Gates", "", "| gate | result | detail |", "|---|---|---|"]
    lines += [f"| {n} | {res} | {d.replace('|', '/')[:300]} |" for n, res, d in gates.rows]
    lines += ["", "## Files", ""] + [f"- `{p.relative_to(run_dir).as_posix()}`"
                                     for p in sorted(run_dir.iterdir()) if p.is_file()]
    (run_dir / "REPORT.md").write_text("\n".join(lines) + "\n", newline="\n", encoding="utf-8")


def append_measurement_log(run_dir, run_id, env, n_acc, n_all, note):
    """Appends a DRAFT row; never rewrites a row and never adds a second row for the same folder."""
    text = MEASUREMENT_LOG.read_text(encoding="utf-8")
    rel = f"results/runs/{run_id}/"
    if rel in text:
        print(f"[log] {MEASUREMENT_LOG.name} already has a row for {rel}; nothing added")
        return
    nums = [int(n) for n in re.findall(r"^\| RUN-(\d+) \|", text, re.M)]
    row = (f"| RUN-{max(nums, default=-1) + 1:03d} | {datetime.now(timezone.utc).date()} | {env} | `{rel}` | "
           f"{n_acc} / {n_all} | **DRAFT written by run_all.py, check before use.** git `{git_commit()[:12]}`. {note} |")
    lines = text.splitlines()
    last = max(i for i, ln in enumerate(lines) if ln.startswith("| RUN-"))
    lines.insert(last + 1, row)
    MEASUREMENT_LOG.write_text("\n".join(lines) + "\n", newline="\n", encoding="utf-8")
    print(f"[log] appended to {MEASUREMENT_LOG}: {row[:100]}...")


def finish(gates, run_dir, run_id, mode, rows, args, env, extra=()):
    write_report(gates, run_dir, run_id, mode, rows, extra)
    cov = read_csv(run_dir / "coverage.csv")
    n_acc = sum(r["status"] == "accepted" for r in cov)
    print("\n" + "=" * 78)
    print(f"run_all.py {mode}  run {run_id}")
    if cov:
        print(f"cells accepted: {n_acc}   rejected / not run: {len(cov) - n_acc}")
        for r in cov:
            if r["status"] != "accepted":
                print(f"   {r['status']:9} {r['cell']}  {r['reason'][:100]}")
    if rows:
        print("\n".join(headline(rows)))
    print(f"gates: {len(gates.rows) - len(gates.failed)} passed, {len(gates.failed)} failed")
    for n, _, d in gates.failed:
        print(f"   FAIL {n}: {d[:200]}")
    print(f"report: {run_dir / 'REPORT.md'}")
    if args.log:
        append_measurement_log(run_dir, run_id, env, n_acc, len(cov),
                               "; ".join(f"{n}: {res}" for n, res, _ in gates.rows if res == "FAIL") or "all gates passed")
    sys.exit(1 if gates.failed else 0)


# ---------------------------------------------------------------------------------------------
# qemu
# ---------------------------------------------------------------------------------------------
def mode_qemu(args):
    run_dir = new_run_dir(args.run_id)
    filters = []
    for opt in ("arch", "lang", "compiler", "profile"):
        if getattr(args, opt):
            filters += [f"--{opt}", *getattr(args, opt)]
    cmd = [PY, "scripts/run_pipeline.py", "--strict", "--run-id", args.run_id, "--repeats", str(args.repeats),
           *(["--skip-host"] if args.skip_host else []), *filters]
    print(f"$ {' '.join(map(str, cmd))}", flush=True)
    r = subprocess.run([str(c) for c in cmd], cwd=REPO_ROOT)   # streams; also writes run_dir/pipeline.log
    if not run_dir.exists():
        sys.exit(f"[FATAL] run_pipeline.py did not create {run_dir} (exit {r.returncode})")
    gates = Gates(run_dir)
    gates.add("run_pipeline.py --strict (host KATs, 1,089 vectors, fuzz, build, symbol gate, QEMU, parse_log)",
              r.returncode == 0, f"exit {r.returncode}; see pipeline.log")
    with open(run_dir / "run_all.log", "w", encoding="utf-8") as log:
        cov = read_csv(run_dir / "coverage.csv")
        n_acc = sum(c["status"] == "accepted" for c in cov)
        full = not filters
        gates.add("cells accepted", bool(cov) and n_acc == len(cov) and (not full or n_acc == 45),
                  f"{n_acc} of {len(cov)} (full matrix: 45)")
        if args.no_baseline or filters:
            print("[note] regression check skipped (" + ("--no-baseline" if args.no_baseline else
                                                         "subset of cells; compare by hand with compare_runs.py") + ")")
        elif not Path(args.baseline, "benchmark.csv").exists():
            gates.add("regression vs baseline", False, f"{args.baseline}/benchmark.csv not found "
                      "(restore it: git checkout HEAD -- results/runs/20261009T030619Z)")
        else:
            cmp = [PY, "scripts/compare_runs.py", "--baseline", args.baseline, "--new", run_dir]
            res = step(gates, f"regression vs baseline {Path(args.baseline).name} (RV32 exact, Arm <= 1 tick)", cmp, log)
            (run_dir / "regression.txt").write_text(res.stdout, newline="\n", encoding="utf-8")
        rows = metrics_summary(gates, run_dir, args.run_id)
    finish(gates, run_dir, args.run_id, "qemu", rows, args, "qemu")


# ---------------------------------------------------------------------------------------------
# hw-build
# ---------------------------------------------------------------------------------------------
def mode_hw_build(args):
    run_dir = new_run_dir(args.run_id)
    run_dir.mkdir(parents=True)
    gates = Gates(run_dir)
    with open(run_dir / "run_all.log", "w", encoding="utf-8") as log:
        step(gates, "build the Pico 2 cells", [PY, "scripts/build_all.py", "--target", "embedded", "--arch", *HW_TARGETS,
                                               "--strict", "--matrix-out", HW_MATRIX], log)
        if not HW_MATRIX.exists():
            finish(gates, run_dir, args.run_id, "hw-build", [], args, "hardware (build only)")
        shutil.copyfile(HW_MATRIX, run_dir / "matrix_hw.json")
        built = [c["id"] for c in json.loads(HW_MATRIX.read_text())["cells"] if c["status"] == "built"]
        mdir = run_dir / "manifests"
        mdir.mkdir()
        for cid in built:
            shutil.copyfile(BUILD_DIR / "cells" / cid / "manifest.json", mdir / f"{cid}.json")
            shutil.copyfile(BUILD_DIR / "cells" / cid / "symbol_gate.txt", mdir / f"{cid}.symbol_gate.txt")
        step(gates, "static checks (hw_check.py)", [PY, "scripts/hw_check.py", "--matrix", HW_MATRIX,
                                                     "--out-dir", run_dir], log)
        step(gates, "size report (linker maps)", [PY, "scripts/size_report.py", "--cells",
                                                   *[BUILD_DIR / "cells" / c for c in built],
                                                   "--output", run_dir / "size_report.csv"], log)
        pre = step(gates, "hardware preflight checklist", [PY, "scripts/hw_preflight.py", "--matrix", HW_MATRIX], log)
        (run_dir / "preflight.txt").write_text(pre.stdout, newline="\n", encoding="utf-8")
    checks = read_csv(run_dir / "hw_static_checks.csv")
    extra = ["## Static checks per cell", "",
             f"{sum(r['result'] == 'pass' for r in checks)} passed, {sum(r['result'] == 'FAIL' for r in checks)} failed, "
             f"{sum(r['result'] == 'skipped' for r in checks)} skipped; details in `hw_static_checks.csv`.", "",
             "No image has run. Nothing in this folder is a measurement.", ""]
    finish(gates, run_dir, args.run_id, "hw-build", [], args, "hardware (build only)", extra)


# ---------------------------------------------------------------------------------------------
# hw-run
# ---------------------------------------------------------------------------------------------
def open_port(port, baud, timeout):
    """The serial port (pyserial). Separate function so tests can replace it."""
    try:
        import serial  # noqa: PLC0415
    except ImportError:
        sys.exit("[FATAL] pyserial is not installed: python -m pip install pyserial")
    return serial.Serial(port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=timeout)


def loader_command(args, cell_dir):
    """The command that loads one image into the board's SRAM and starts it (None = manual)."""
    uf2, elf = cell_dir / "firmware.uf2", cell_dir / "firmware.elf"
    if args.loader == "picotool":
        return [args.picotool, "load", "-x", str(uf2), "-t", "uf2"]
    if args.loader == "openocd":
        from rp2350_image import Elf
        elf_obj = Elf(elf)
        entry = elf_obj.entry
        # Arm Thumb requires odd address for resume; RISC-V uses even address
        is_arm = "arm" in cell_dir.name
        pc = (entry | 1) if is_arm else entry
        ocd_cmd = (
            f"adapter speed 5000; init; reset halt; "
            f"load_image {elf.as_posix()}; "
            f"resume 0x{pc:x}; exit"
        )
        return [args.openocd, *args.openocd_args, "-c", ocd_cmd]
    return None


def load_image(args, cell_dir):
    """Puts one image on the board. uf2-drive: copy to the bootrom's USB drive (datasheet 5.5);
    picotool/openocd: run the tool; manual: ask the operator. Separate function so tests can replace it."""
    uf2 = cell_dir / "firmware.uf2"
    if args.loader == "uf2-drive":
        drive = Path(args.uf2_drive)
        t0 = time.time()
        while not (drive / "INFO_UF2.TXT").exists():
            if time.time() - t0 > args.load_timeout:
                raise RuntimeError(f"{drive} did not appear (board not in BOOTSEL mode?)")
            time.sleep(0.5)
        shutil.copyfile(uf2, drive / "firmware.uf2")
        return f"copy {uf2.name} -> {drive}"
    cmd = loader_command(args, cell_dir)
    if cmd is None:
        input(f"Load {uf2} onto the board now (e.g. drag it onto the RP2350 drive), then press Enter... ")
        return "manual"
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=args.load_timeout)
    if r.returncode != 0:
        raise RuntimeError(f"loader failed ({r.returncode}): {(r.stdout + r.stderr)[-500:]}")
    return " ".join(cmd)


def capture(ser, timeout):
    """Reads lines until the image's EXIT line or the timeout. Returns (lines, status)."""
    lines, buf, t0 = [], b"", time.time()
    while time.time() - t0 < timeout:
        chunk = ser.read(256)
        if not chunk:
            continue
        buf += chunk
        while b"\n" in buf:
            raw, buf = buf.split(b"\n", 1)
            line = raw.decode("ascii", errors="replace").rstrip("\r")
            lines.append(line)
            if line.startswith("EXIT,"):
                return lines, "exit"
    if buf:
        lines.append(buf.decode("ascii", errors="replace").rstrip("\r"))
    return lines, "timeout"


def mode_hw_run(args):
    if not args.confirm_hardware:
        print("[REFUSED] hw-run loads and runs images on a connected Pico 2. Add --confirm-hardware to proceed.")
        sys.exit(2)
    if not HW_MATRIX.exists():
        sys.exit(f"[FATAL] {HW_MATRIX} not found: run `python scripts/run_all.py hw-build` first")
    check = subprocess.run([PY, "scripts/hw_check.py", "--matrix", HW_MATRIX], cwd=REPO_ROOT,
                           capture_output=True, text=True)
    if check.returncode != 0:
        print(check.stdout[-3000:])
        sys.exit("[FATAL] static checks fail on the current hardware build; not loading anything")
    cells = [c for c in json.loads(HW_MATRIX.read_text())["cells"] if c["status"] == "built"]
    if args.cells:
        cells = [c for c in cells if c["id"] in args.cells]
        if {c["id"] for c in cells} != set(args.cells):
            sys.exit(f"[FATAL] not built: {sorted(set(args.cells) - {c['id'] for c in cells})}")
    try:
        ser = open_port(args.port, args.baud, 0.2)
    except Exception as e:  # noqa: BLE001 -- any failure to open the port stops the run
        sys.exit(f"[FATAL] cannot open serial port {args.port}: {e}")

    run_dir = new_run_dir(args.run_id)
    raw = run_dir / "raw"
    raw.mkdir(parents=True)
    gates = Gates(run_dir)
    shutil.copyfile(HW_MATRIX, run_dir / "matrix_hw.json")
    mdir = run_dir / "manifests"
    mdir.mkdir()
    for c in cells:
        shutil.copyfile(BUILD_DIR / "cells" / c["id"] / "manifest.json", mdir / f"{c['id']}.json")
    for c in cells:
        cdir = BUILD_DIR / "cells" / c["id"]
        hw = TARGETS[c["target"]]["hardware"]
        for rep in range(1, args.repeats + 1):
            if args.loader != "manual" and not args.no_prompt:
                input(f"[{c['id']} r{rep}] put the Pico 2 in BOOTSEL mode, then press Enter... ")
            ser.reset_input_buffer()
            t0 = time.time()
            try:
                how = load_image(args, cdir)
                lines, status = capture(ser, args.timeout)
            except Exception as e:  # noqa: BLE001 -- recorded in the log, the cell is then rejected
                how, lines, status = f"failed: {e}", [], "load_failed"
            header = [
                "RUN,env,hardware", f"RUN,cell,{c['id']}", f"RUN,repeat,{rep}",
                f"RUN,date_utc,{datetime.now(timezone.utc).isoformat(timespec='seconds')}",
                f"RUN,board,{hw['board']}", f"RUN,arch,{hw['arch']}",
                f"RUN,elf_sha256,{hashlib.sha256((cdir / 'firmware.elf').read_bytes()).hexdigest()}",
                f"RUN,uf2_sha256,{hashlib.sha256((cdir / 'firmware.uf2').read_bytes()).hexdigest()}",
                f"RUN,serial,{args.port} {args.baud} 8N1", f"RUN,loader,{how}",
                f"RUN,host,{platform.platform()}", f"RUN,capture_status,{status}",
                f"RUN,wall_seconds,{time.time() - t0:.1f}"]
            (raw / f"{c['id']}.r{rep}.log").write_text("\n".join(header + lines) + "\n", newline="\n", encoding="utf-8")
            print(f"  [{'OK  ' if status == 'exit' and 'LWC_END,ok' in lines else 'FAIL'}] {c['id']}.r{rep} "
                  f"{status} {time.time() - t0:.1f}s", flush=True)
    ser.close()
    with open(run_dir / "run_all.log", "w", encoding="utf-8") as log:
        step(gates, "validate logs (parse_log.py, same validator as QEMU)",
             [PY, "scripts/parse_log.py", "--input", raw, "--out-dir", run_dir, "--matrix", HW_MATRIX,
              "--host-digest", args.host_digest], log)
        step(gates, "size report (linker maps)", [PY, "scripts/size_report.py", "--cells",
                                                   *[BUILD_DIR / "cells" / c["id"] for c in cells],
                                                   "--output", run_dir / "size_report.csv"], log)
        rows = metrics_summary(gates, run_dir, args.run_id)
    finish(gates, run_dir, args.run_id, "hw-run", rows, args, "hardware")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="mode")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--run-id", default=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
                        help="results/runs/<run id> (default: UTC timestamp); must not exist")
    common.add_argument("--log", action="store_true", help="append a DRAFT row to docs/MEASUREMENT_LOG.md")

    q = sub.add_parser("qemu", parents=[common], help="the 45 QEMU cells (default)")
    q.add_argument("--repeats", type=int, default=2)
    q.add_argument("--skip-host", action="store_true")
    q.add_argument("--baseline", default=str(BASELINE), help="run folder to compare with (default RUN-004)")
    q.add_argument("--no-baseline", action="store_true")
    q.add_argument("--arch", nargs="*", choices=QEMU_TARGETS)
    q.add_argument("--lang", nargs="*")
    q.add_argument("--compiler", nargs="*")
    q.add_argument("--profile", nargs="*")

    sub.add_parser("hw-build", parents=[common], help="build + statically check the Pico 2 images")

    h = sub.add_parser("hw-run", parents=[common], help="run on the Pico 2 (needs the board)")
    h.add_argument("--port", required=True, help="serial port of the USB-UART adapter on GP0/GP1, e.g. COM5")
    h.add_argument("--confirm-hardware", action="store_true", help="required: confirms a board is connected")
    h.add_argument("--baud", type=int, default=115200)
    h.add_argument("--repeats", type=int, default=2)
    h.add_argument("--cells", nargs="*")
    h.add_argument("--loader", choices=["uf2-drive", "picotool", "openocd", "manual"], default="uf2-drive")
    h.add_argument("--uf2-drive", default="E:/", help="mount point of the RP2350 BOOTSEL drive")
    h.add_argument("--picotool", default="picotool")
    h.add_argument("--openocd", default="openocd")
    h.add_argument("--openocd-args", nargs="*", default=["-f", "interface/cmsis-dap.cfg", "-f", "target/rp2350.cfg"])
    h.add_argument("--no-prompt", action="store_true", help="do not wait for Enter before each load")
    h.add_argument("--timeout", type=int, default=1800, help="seconds to wait for one image to finish")
    h.add_argument("--load-timeout", type=int, default=60)
    h.add_argument("--host-digest", default=str(BUILD_DIR / "host" / "fuzz_digest.json"))

    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0].startswith("-") and argv[0] not in ("-h", "--help"):
        argv = ["qemu", *argv]
    args = ap.parse_args(argv)
    os.chdir(REPO_ROOT)
    {"qemu": mode_qemu, "hw-build": mode_hw_build, "hw-run": mode_hw_run}[args.mode](args)


if __name__ == "__main__":
    main()
