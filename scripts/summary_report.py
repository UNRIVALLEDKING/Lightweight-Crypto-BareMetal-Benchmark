#!/usr/bin/env python3
"""
Prints a formatted summary table from a run's metrics_summary.csv.
"""
import csv
import sys
from pathlib import Path


def main():
    if len(sys.argv) < 2:
        runs_dir = Path("results/runs")
        runs = sorted([d for d in runs_dir.iterdir() if d.is_dir()], key=lambda d: d.stat().st_mtime)
        if not runs:
            print("No runs found.")
            return
        run_dir = runs[-1]
    else:
        run_dir = Path(sys.argv[1])

    csv_path = run_dir / "metrics_summary.csv"
    if not csv_path.exists():
        print(f"File not found: {csv_path}")
        return

    print(f"\nRun Folder: {run_dir.name}\n")
    with open(csv_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    print(f"{'CELL / CONFIG':<34} | {'SIMON64 (cyc)':<13} | {'PRESENT80 (cyc)':<15} | {'ASCON 1KB (cyc)':<15} | {'STACK (B)':<9}")
    print("-" * 97)

    by_cell = {}
    for r in rows:
        cell_key = f"{r['target']}-{r['lang']}-{r['compiler']}-{r['profile']}"
        by_cell.setdefault(cell_key, {})[r["op"]] = r

    for cell, ops_map in by_cell.items():
        s_cyc = ops_map.get("SIMON64_ENC", {}).get("metric_median", "-")
        p_cyc = ops_map.get("PRESENT80_ENC", {}).get("metric_median", "-")
        a_cyc = ops_map.get("ASCON_AEAD128_ENC_1024B", {}).get("metric_median", "-")
        stk = ops_map.get("ASCON_AEAD128_ENC_1024B", {}).get("stack_bytes", "-")
        try:
            s_str = f"{float(s_cyc):,.0f}" if s_cyc != "-" else "-"
            p_str = f"{float(p_cyc):,.0f}" if p_cyc != "-" else "-"
            a_str = f"{float(a_cyc):,.0f}" if a_cyc != "-" else "-"
        except ValueError:
            s_str, p_str, a_str = s_cyc, p_cyc, a_cyc
        print(f"{cell:<34} | {s_str:<13} | {p_str:<15} | {a_str:<15} | {stk:<9}")


if __name__ == "__main__":
    main()
