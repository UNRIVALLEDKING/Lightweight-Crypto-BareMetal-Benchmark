#!/usr/bin/env python3
"""
Validate benchmark logs and turn them into CSV tables.

Input: a directory of logs written by run_qemu.py (<cell>.r<k>.log), or hardware logs written by
run_all.py hw-run (Pico 2), which start with "RUN,env,hardware", "RUN,cell,<id>", "RUN,board,...",
"RUN,arch,<arm|riscv>" and "RUN,elf_sha256,..." and contain the image's own "RUN,clock_hz,<Hz>".
One invocation validates logs of ONE env only: a mix of qemu and hardware logs is rejected.

A log is ACCEPTED only if all of these hold, otherwise every row of that cell is rejected:
  - RUN,env is "qemu" or "hardware"; LWC_BEGIN and LWC_END,ok present; no ERROR line;
    exit status 0 (QEMU)
  - the BUILD lines match build/cells/<cell>/manifest.json, and the ELF that ran has the
    SHA-256 of the current build
  - env=qemu only for QEMU targets, env=hardware only for hardware targets (rp2350_*);
    hardware: RUN,board / RUN,arch / RUN,clock_hz present, TIMER source DWT_CYCCNT, SYSTICK or
    MCYCLE with unit cpu_cycles; qemu: the unit is never cpu_cycles
  - every KAT passed, and the FUZZ digest equals the host reference
    (build/host/fuzz_digest.json, written by host/differential.py) with 0 errors
  - repeats of the same cell report identical SUMMARY lines (QEMU -icount is deterministic)

Units. Raw values are counter ticks (TIMER line). The "metric" columns convert them:
  env=qemu      -> "qemu_instructions": ticks x (instructions / ticks) from the image's own
                   CALIBRATION loop. QEMU executes, it does not model a pipeline: these
                   are instruction counts, NOT cycles.
  env=hardware  -> "cpu_cycles" (DWT CYCCNT, mcycle, or SysTick on the processor clock).
The metric_kind column carries the same name in every row, so a table can never mix the two
without saying so.
Medians are corrected by the measured timer overhead (TIMER_OVERHEAD median) before
conversion. Rows from different env values must never be compared.

Outputs (in --out-dir): benchmark.csv, stack.csv, checks.csv, coverage.csv
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lwc_matrix import BUILD_DIR, TARGETS  # noqa: E402

LOG_NAME = re.compile(r"^(?P<cell>.+)\.r(?P<rep>\d+)\.log$")
BUILD_KEYS_FROM_MANIFEST = ["cell", "target", "lang", "compiler", "profile", "opt_class", "safety"]
HW_TIMER_SOURCES = ("DWT_CYCCNT", "SYSTICK", "MCYCLE")
HW_RUN_KEYS = ("board", "arch", "clock_hz", "elf_sha256")


def read_log(path):
    log = {"run": {}, "build": {}, "kat": {}, "stack": {}, "summary": {}, "data": defaultdict(list),
           "errors": [], "begin": False, "end": None, "fuzz": None, "timer": None, "calib": None,
           "overhead": None, "bench_config": None}
    for line in Path(path).read_text(errors="replace").splitlines():
        f = line.rstrip("\r").split(",")
        tag = f[0]
        if tag == "RUN" and len(f) >= 3:
            log["run"][f[1]] = ",".join(f[2:])
        elif tag == "BUILD" and len(f) >= 3:
            log["build"][f[1]] = ",".join(f[2:])
        elif tag == "LWC_BEGIN":
            log["begin"] = True
        elif tag == "LWC_END":
            log["end"] = f[1] if len(f) > 1 else ""
        elif tag == "ERROR":
            log["errors"].append(line)
        elif tag == "TIMER" and len(f) == 4:
            log["timer"] = {"source": f[1], "unit": f[2], "mask": int(f[3], 16)}
        elif tag == "CALIBRATION" and len(f) == 4:
            log["calib"] = {"iterations": int(f[1]), "instructions": int(f[2]), "ticks": int(f[3])}
        elif tag == "KAT" and len(f) == 4:
            log["kat"][f[1]] = (int(f[2]), int(f[3]))
        elif tag == "FUZZ" and len(f) == 6:
            log["fuzz"] = {"iterations": int(f[1]), "SIMON64_128": f[2], "PRESENT80": f[3],
                           "ASCON_AEAD128": f[4], "errors": int(f[5])}
        elif tag == "STACK" and len(f) == 3:
            log["stack"][f[1]] = int(f[2])
        elif tag == "BENCH_CONFIG" and len(f) == 4:
            log["bench_config"] = tuple(int(x) for x in f[1:])
        elif tag == "TIMER_OVERHEAD" and len(f) == 3:
            log["overhead"] = {"min": int(f[1]), "median": int(f[2])}
        elif tag == "DATA" and len(f) == 4:
            log["data"][f[1]].append(int(f[3]))
        elif tag == "SUMMARY" and len(f) == 11:
            log["summary"][f[1]] = {"bytes": int(f[2]), "n": int(f[3]), "min": int(f[4]), "p5": int(f[5]),
                                    "median": int(f[6]), "p95": int(f[7]), "max": int(f[8]),
                                    "mean": float(f[9]), "outliers": int(f[10])}
    return log


def validate(log, host_digest):
    p = []
    env = log["run"].get("env")
    if env not in ("qemu", "hardware"):
        p.append(f"RUN,env missing or invalid ({env!r}): label every log 'qemu' or 'hardware'")
    if not log["begin"]:
        p.append("LWC_BEGIN missing (image did not start or output was lost)")
    if log["end"] != "ok":
        p.append(f"LWC_END is {log['end']!r}, expected 'ok'")
    if env == "qemu" and log["run"].get("exit_status") != "0":
        p.append(f"QEMU exit status {log['run'].get('exit_status')}")
    p += [f"image reported: {e}" for e in log["errors"]]

    cell = log["run"].get("cell") or log["build"].get("cell")
    manifest_path = BUILD_DIR / "cells" / str(cell) / "manifest.json"
    if manifest_path.exists():
        m = json.loads(manifest_path.read_text())
        for k in BUILD_KEYS_FROM_MANIFEST:
            if log["build"].get(k) != str(m.get(k)):
                p.append(f"BUILD,{k} = {log['build'].get(k)!r} but manifest says {m.get(k)!r}")
        if log["run"].get("elf_sha256") != m.get("elf_sha256"):
            p.append("the ELF that ran is not the current build of this cell (SHA-256 differs)")
        is_hw_target = "hardware" in TARGETS.get(m.get("target"), {})
        if env == "qemu" and is_hw_target:
            p.append(f"env=qemu log for hardware target {m.get('target')} (no QEMU machine for it)")
        if env == "hardware" and not is_hw_target:
            p.append(f"env=hardware log for QEMU target {m.get('target')}")
    else:
        p.append(f"no manifest for cell {cell!r}")

    for cipher in ("SIMON64_128", "PRESENT80", "ASCON_AEAD128"):
        passed, total = log["kat"].get(cipher, (0, -1))
        if total <= 0 or passed != total:
            p.append(f"KAT {cipher}: {passed}/{total}")
    fz = log["fuzz"]
    if not fz:
        p.append("FUZZ line missing")
    else:
        if fz["errors"]:
            p.append(f"fuzz round-trip/auth errors: {fz['errors']}")
        if host_digest:
            for k in ("SIMON64_128", "PRESENT80", "ASCON_AEAD128"):
                if fz[k] != host_digest[k]:
                    p.append(f"fuzz digest {k} {fz[k]} != host reference {host_digest[k]}")
            if fz["iterations"] != host_digest["iterations"]:
                p.append("fuzz iteration count differs from the host reference")
    if not log["timer"] or not log["calib"] or not log["overhead"]:
        p.append("TIMER / CALIBRATION / TIMER_OVERHEAD line missing")
    elif env == "hardware":
        if log["timer"]["source"] not in HW_TIMER_SOURCES or log["timer"]["unit"] != "cpu_cycles":
            p.append(f"hardware TIMER {log['timer']['source']},{log['timer']['unit']}: expected one of "
                     f"{HW_TIMER_SOURCES} with unit cpu_cycles")
    elif log["timer"]["unit"] == "cpu_cycles":
        p.append("a non-hardware log reports cpu_cycles (QEMU counts instructions, never cycles)")
    if env == "hardware":
        for k in HW_RUN_KEYS:
            if not log["run"].get(k):
                p.append(f"RUN,{k} missing (required on hardware logs)")
        if log["run"].get("arch") not in (None, "arm", "riscv"):
            p.append(f"RUN,arch {log['run'].get('arch')!r}: expected arm or riscv")
        if not str(log["run"].get("clock_hz", "")).isdigit():
            p.append(f"RUN,clock_hz {log['run'].get('clock_hz')!r} is not a frequency in Hz")
    if not log["summary"]:
        p.append("no SUMMARY rows")
    return p


def metric(log):
    """(metric name, factor converting raw ticks to that metric)."""
    if log["run"].get("env") == "qemu":
        c = log["calib"]
        return "qemu_instructions", c["instructions"] / c["ticks"]
    return "cpu_cycles", 1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="directory of <cell>.r<k>.log files (or one log)")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--host-digest", default=str(BUILD_DIR / "host" / "fuzz_digest.json"))
    ap.add_argument("--matrix", default=str(BUILD_DIR / "matrix.json"), help="for coverage.csv")
    ap.add_argument("--allow-no-host-digest", action="store_true",
                    help="accept logs without the host reference (digests are then only compared across logs)")
    args = ap.parse_args()

    inp = Path(args.input)
    paths = sorted(inp.glob("*.log")) if inp.is_dir() else [inp]
    host_digest = None
    if Path(args.host_digest).exists():
        host_digest = json.loads(Path(args.host_digest).read_text())
    elif not args.allow_no_host_digest:
        print(f"[FATAL] host reference digest {args.host_digest} not found: run host/differential.py first")
        sys.exit(1)

    by_cell = defaultdict(list)
    envs = set()
    for path in paths:
        log = read_log(path)
        cell = log["run"].get("cell") or log["build"].get("cell") or path.stem
        m = LOG_NAME.match(path.name)
        log["repeat"] = int(m.group("rep")) if m else 1
        log["path"] = path
        envs.add(log["run"].get("env"))
        by_cell[cell].append(log)
    if len(envs) > 1:
        print(f"[FATAL] logs of more than one env in {inp}: {sorted(map(str, envs))}. qemu instruction counts "
              "and hardware cycle counts must never go into one table: validate them separately.")
        sys.exit(2)

    rejected, bench_rows, stack_rows, check_rows = {}, [], [], []
    digests = set()
    for cell, logs in sorted(by_cell.items()):
        problems = []
        for log in logs:
            problems += [f"{log['path'].name}: {x}" for x in validate(log, host_digest)]
            if log["fuzz"]:
                digests.add((log["fuzz"]["SIMON64_128"], log["fuzz"]["PRESENT80"], log["fuzz"]["ASCON_AEAD128"]))
        first = logs[0]
        for other in logs[1:]:
            if other["summary"] != first["summary"] and first["run"].get("env") == "qemu":
                problems.append(f"{other['path'].name}: SUMMARY differs from {first['path'].name} "
                                "(QEMU -icount runs must be identical)")
        b, r = first["build"], first["run"]
        check_rows.append({
            "cell": cell, "env": r.get("env"), "target": b.get("target"), "lang": b.get("lang"),
            "compiler": b.get("compiler"), "profile": b.get("profile"), "runs": len(logs),
            "accepted": not problems, "kat": " ".join(f"{k}={v[0]}/{v[1]}" for k, v in first["kat"].items()),
            "fuzz_digest": "-".join(first["fuzz"][k] for k in ("SIMON64_128", "PRESENT80", "ASCON_AEAD128"))
            if first["fuzz"] else "", "timer_source": (first["timer"] or {}).get("source"),
            "problems": " | ".join(problems)})
        if problems:
            rejected[cell] = problems
            continue

        name, factor = metric(first)
        overhead = first["overhead"]["median"]
        common = {"env": r.get("env"), "cell": cell, "target": b.get("target"), "lang": b.get("lang"),
                  "compiler": b.get("compiler"), "compiler_version": b.get("compiler_version"),
                  "profile": b.get("profile"), "opt_class": b.get("opt_class"), "safety": b.get("safety"),
                  "backend_flags": b.get("backend_flags"), "harness_flags": b.get("harness_flags"),
                  "qemu_version": r.get("qemu_version", ""), "icount": r.get("icount", ""),
                  "board": r.get("board", ""), "clock_hz": r.get("clock_hz", ""),
                  "git_commit": b.get("git_commit"), "runs": len(logs)}
        for op, s in first["summary"].items():
            batches = first["data"].get(op, [])
            spread = (max(batches) - min(batches)) / s["median"] * 100 if batches and s["median"] else 0.0
            net = max(s["median"] - overhead, 0)
            value = net * factor
            bench_rows.append({
                **common, "op": op, "bytes": s["bytes"], "samples": s["n"],
                "timer_source": first["timer"]["source"], "raw_unit": first["timer"]["unit"],
                "raw_min": s["min"], "raw_p5": s["p5"], "raw_median": s["median"], "raw_p95": s["p95"],
                "raw_max": s["max"], "raw_mean": s["mean"], "outliers_over_4x_median": s["outliers"],
                "timer_overhead_median": overhead, "batch_median_spread_pct": round(spread, 3),
                "metric": name, "metric_kind": name, "ticks_to_metric": round(factor, 6),
                "median_metric": round(value, 1),
                "metric_per_byte": round(value / s["bytes"], 2) if s["bytes"] else "",
            })
        base = first["stack"].get("EMPTY_PROBE", 0)
        for op, depth in first["stack"].items():
            if op != "EMPTY_PROBE":
                stack_rows.append({**{k: common[k] for k in ("env", "cell", "target", "lang", "compiler",
                                                             "profile", "opt_class", "safety")},
                                   "op": op, "stack_bytes_incl_call": depth, "probe_baseline": base,
                                   "stack_bytes": depth - base})

    # Digest agreement across every accepted and rejected log, even without a host reference.
    if len(digests) > 1:
        print(f"[FAIL] images disagree on the fuzz digest: {sorted(digests)}")

    coverage = []
    if Path(args.matrix).exists():
        for c in json.loads(Path(args.matrix).read_text())["cells"]:
            ran = c["id"] in by_cell
            status = c["status"] if c["status"] != "built" else (
                "not run" if not ran else ("rejected" if c["id"] in rejected else "accepted"))
            coverage.append({"cell": c["id"], "target": c["target"], "lang": c["lang"], "compiler": c["compiler"],
                             "profile": c["profile"], "status": status,
                             "reason": c.get("reason", "") or " | ".join(rejected.get(c["id"], []))})

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("benchmark.csv", bench_rows), ("stack.csv", stack_rows),
                       ("checks.csv", check_rows), ("coverage.csv", coverage)):
        if rows:
            with open(out / name, "w", newline="", encoding="utf-8") as f:
                w = csv.DictWriter(f, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

    print(f"logs: {len(paths)}  cells: {len(by_cell)}  accepted: {len(by_cell) - len(rejected)}  "
          f"rejected: {len(rejected)}  benchmark rows: {len(bench_rows)}")
    for c in coverage:
        if c["status"] not in ("accepted",):
            print(f"  {c['status']:9} {c['cell']:40} {c['reason'][:110]}")
    for cell, problems in rejected.items():
        print(f"[REJECTED] {cell}")
        for x in problems[:8]:
            print("   -", x)
    print(f"CSV written to {out}")
    if rejected or len(digests) > 1:
        sys.exit(2)


if __name__ == "__main__":
    main()
