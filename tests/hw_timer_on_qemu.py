#!/usr/bin/env python3
"""
Unit test of the Pico 2 timer logic under QEMU (labelled env=qemu; NOT a hardware run).

QEMU 11.1 has no RP2040/RP2350 machine, so the RP2350 start-up, clocks and UART cannot run under it.
What can run is the timer code: harness/rp2350_arm/timing.c on mps2-an505 (Cortex-M33; QEMU has no
running DWT CYCCNT, so the run-time probe must fall back to SysTick) and harness/rp2350_rv/timing.c on
virt (mcycle). Both are linked with the QEMU start-up and semihosting of harness/arm / harness/riscv.

  python tests/hw_timer_on_qemu.py [--out results/verification/unit_tests/hw_timer_qemu.txt]
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
from lwc_matrix import HARNESS_FLAGS, TARGETS, find_llvm, find_qemu  # noqa: E402

CASES = {
    "arm": {"qemu_target": "armv8m", "hw_target": "rp2350_arm", "expect_source": "SYSTICK",
            "srcs": ["harness/arm/startup.c", "harness/rp2350_arm/timing.c"], "ld": "harness/arm/link.ld"},
    "riscv": {"qemu_target": "rv32imac_zbb", "hw_target": "rp2350_rv_zbb", "expect_source": "MCYCLE",
              "srcs": ["harness/riscv/startup.S", "harness/riscv/platform.c", "harness/rp2350_rv/timing.c"],
              "ld": "harness/riscv/link.ld"},
}
COMMON = ["tests/hw_logic/timer_main.c", "harness/common/io.c", "harness/common/rt.c", "harness/common/builtins.c"]


def run_case(name, c, tmp, report):
    tgt = TARGETS[c["qemu_target"]]
    elf = tmp / f"{name}.elf"
    cmd = [find_llvm("clang"), *TARGETS[c["hw_target"]]["clang"], *HARNESS_FLAGS, "-Iharness/common",
           "-nostdlib", "-fuse-ld=lld", "-static", f"-Wl,-T,{c['ld']}", "-Wl,-L,harness/common", "-Wl,--gc-sections",
           *COMMON, *c["srcs"], "-o", str(elf)]
    report.append("$ " + " ".join(Path(x).name if x.startswith(str(tmp)) else x for x in cmd))
    subprocess.run(cmd, cwd=REPO, check=True)
    cap = tmp / f"{name}.txt"
    q = [find_qemu(c["qemu_target"]), *tgt["qemu_args"], "-nographic", "-monitor", "none", "-serial", "none",
         "-chardev", f"file,id=semihost,path={cap.as_posix()}",
         "-semihosting-config", "enable=on,target=native,chardev=semihost",
         "-icount", "shift=6,align=off,sleep=off", "-kernel", str(elf)]
    report.append("$ " + " ".join([Path(q[0]).name, *tgt["qemu_args"], "...", "-kernel", elf.name]))
    r = subprocess.run(q, capture_output=True, text=True, timeout=120)
    out = cap.read_text() if cap.exists() else ""
    report += [f"exit status {r.returncode}", *out.strip().splitlines()]
    timer = next((ln for ln in out.splitlines() if ln.startswith("TIMER,")), "")
    ok = (r.returncode == 0 and "UNIT_TEST_RESULT,pass" in out
          and timer.startswith(f"TIMER,{c['expect_source']},cpu_cycles"))
    report.append(f"=> {name}: {'PASS' if ok else 'FAIL'} (expected TIMER source {c['expect_source']}, unit cpu_cycles)\n")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out")
    args = ap.parse_args()
    report = ["# Pico 2 timer logic under QEMU -- env=qemu, unit test only, NOT a hardware measurement", ""]
    with tempfile.TemporaryDirectory() as t:
        ok = all([run_case(n, c, Path(t), report) for n, c in CASES.items()])
    text = "\n".join(report) + f"\nOVERALL: {'PASS' if ok else 'FAIL'}\n"
    print(text)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text, newline="\n")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
