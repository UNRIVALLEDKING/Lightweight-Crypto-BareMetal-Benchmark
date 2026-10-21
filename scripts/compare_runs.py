#!/usr/bin/env python3
"""
Regression check: compare the benchmark.csv of a new run with a baseline run.

Rows are matched on (cell, op). The raw counter columns are compared, not the converted
metric (the conversion uses each image's own calibration, which can move by a fraction).
Tolerance per target, from the methodology (docs/METHODOLOGY.md section 2):
  RV32 targets (mcycle, -icount)   identical raw values
  armv8m (SysTick, 1.28 ticks/insn) at most --arm-ticks (default 1) tick per column
Every difference is printed, also those within tolerance. Exit status 0 if all rows are
within tolerance and both runs have the same set of rows, 1 otherwise.

  python scripts/compare_runs.py --baseline results/runs/20261009T030619Z --new results/runs/<id>
"""

import argparse
import csv
import sys
from pathlib import Path

RAW = ["raw_min", "raw_p5", "raw_median", "raw_p95", "raw_max", "timer_overhead_median"]


def load(run_dir):
    with open(Path(run_dir) / "benchmark.csv", newline="", encoding="utf-8") as f:
        return {(r["cell"], r["op"]): r for r in csv.DictReader(f)}


def compare(base, new, arm_ticks):
    """Returns (report lines, number of out-of-tolerance problems)."""
    lines, bad = [], 0
    for key in sorted(set(base) - set(new)):
        lines.append(f"MISSING in new run: {key[0]} {key[1]}")
        bad += 1
    for key in sorted(set(new) - set(base)):
        lines.append(f"EXTRA in new run (not in baseline): {key[0]} {key[1]}")
    n_diff = 0
    for key in sorted(set(base) & set(new)):
        b, n = base[key], new[key]
        if b.get("env") != n.get("env"):
            lines.append(f"ENV differs {key}: {b.get('env')} vs {n.get('env')}")
            bad += 1
            continue
        tol = arm_ticks if b["target"] == "armv8m" else 0
        for col in RAW:
            d = int(n[col]) - int(b[col])
            if d:
                n_diff += 1
                ok = abs(d) <= tol
                bad += not ok
                lines.append(f"{'within tol' if ok else 'OUT OF TOL'}: {key[0]:34} {key[1]:26} {col:22} "
                             f"{b[col]} -> {n[col]} ({d:+d} tick)  metric {b['median_metric']} -> {n['median_metric']}")
    lines.insert(0, f"rows: baseline {len(base)}, new {len(new)}, common {len(set(base) & set(new))}; "
                    f"differing raw values: {n_diff}; out of tolerance: {bad}")
    return lines, bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True, help="run directory with benchmark.csv")
    ap.add_argument("--new", required=True, help="run directory with benchmark.csv")
    ap.add_argument("--arm-ticks", type=int, default=1, help="allowed SysTick difference on armv8m")
    args = ap.parse_args()
    lines, bad = compare(load(args.baseline), load(args.new), args.arm_ticks)
    print("\n".join(lines))
    print("[OK] within tolerance" if not bad else f"[FAIL] {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
