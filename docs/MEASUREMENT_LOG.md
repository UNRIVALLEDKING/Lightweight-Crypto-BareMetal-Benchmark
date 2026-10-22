# Measurement log

One row per run, written right after the run from the run directory, never from a template.
Nothing here may describe equipment that was not used.

## Runs

| Run ID | Date (UTC) | env | Directory | Cells accepted | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| RUN-000 | 2026-10-04 | qemu (ESP32 fork) | removed from the tree; in git commit `97bc51c` (`results/_INVALID_pre_symbol_fix/`) | none | **INVALID** (the first, ESP32-era campaign: its Rust and Zig rows measured the C code). |
| RUN-001 | 2026-10-09 | qemu | removed from the tree; in git commit `e1cacd4` (`results/runs/20261009T011756Z/`) | 22 / 30 | First run of the new matrix. git `f241453` (clean). Host: Windows 10, QEMU 11.1.0, clang 23.1.2, rustc 1.99.0, zig 0.16.0. 2 repeats per image, identical. 8 gcc cells skipped: arm-none-eabi-gcc and riscv-none-elf-gcc not installed. |
| RUN-002 | 2026-10-09 | qemu | removed from the tree; in git commit `35c46d7` (`results/runs/20261009T014812Z/`) | 30 / 30 | Full matrix after installing xPack GCC (arm-none-eabi 15.2.1, riscv-none-elf 15.2.0). git `75ecce3` (clean), `--strict`. 2 repeats per image, identical. The 22 non-gcc cells reproduce RUN-001 exactly. |
| RUN-003 | 2026-10-09 | qemu | `results/runs/20261009T021521Z/` | 30 / 30 | **Superseded by RUN-004. Baseline before the inlining and Zbb changes; superseded by the next run.** Same code as RUN-002 (git `b0b6772`, stamped `-dirty` only because the old results had been deleted from the tree); compared with RUN-002 (different session): all RV32 rows are identical; on Arm 1 of 210 raw medians differs by 1 SysTick tick (`armv8m-c-gcc-Oz` ASCON_AEAD128_ENC_64B, 12794 vs 12793), 3 rows differ in min/p5/p95/max by 1 tick, and converted values differ by at most 0.1 (per-image calibration). So Arm numbers are exact only to the 1-tick (~0.8 instruction) resolution across sessions; repeats within one session were identical. A second run made minutes earlier (`20261009T021139Z`) matched it in all 420 rows and was not kept. Host: Windows 10, Python 3.12, QEMU 11.1.0. |
| RUN-004 | 2026-10-09 | qemu | `results/runs/20261009T030619Z/` | 45 / 45 | **Superseded by RUN-007.** Baseline before C++ and Rust -ovf expansion. 45 cells. |
| RUN-005 | 2026-10-21 | hardware | `results/runs/20261020T233856Z/` | 11 / 11 | **Superseded by RUN-006.** Raspberry Pi Pico 2 (RP2350, ARM Cortex-M33 @ 12.0 MHz, crystal oscillator, DWT_CYCCNT, image in SRAM, OpenOCD over SWD via Debug Probe). Benchmarks C (GCC, Clang), Rust (Safe & Hardware-Optimized), and Zig across O3 and Oz. 11 cells passed (154 rows accepted). |
| RUN-006 | 2026-10-21 | hardware | `results/runs/20261021T214313Z/` | 17 / 17 | **Current ARM Hardware Baseline.** Raspberry Pi Pico 2 (RP2350, ARM Cortex-M33 @ 12.0 MHz, crystal oscillator, DWT_CYCCNT, image in SRAM, OpenOCD over SWD via Debug Probe). Expanded full suite adding C++ (GCC, Clang) and Rust overflow checks (`rustc-O3-ovf`, `rustc-Oz-ovf`). Incorporates the inlining policy fix (`#[inline(always)]` -> `#[inline]` in `ciphers/rust_opt`), slashing Rust Opt `-Oz` flash by 57% (down to 2,906 B). All 17 cells passed all 4 verification gates (238 rows accepted, 0 rejected). |
| RUN-007 | 2026-10-21 | qemu | `results/runs/20261021T220250Z/` | 51 / 51 | **Current QEMU Baseline.** Expanded full matrix across `armv8m`, `rv32imac`, and `rv32imac_zbb` (17 cells per target, 51 cells total). Incorporates C++ (GCC, Clang), Rust overflow checks, and the inlining policy fix (`#[inline]`). Isolates the exact instruction savings of the RISC-V Zbb rotate extension and Thumb-2 flexible barrel shifters. All 51 cells passed all verification gates. |

`results/runs/<id>/` holds the raw logs, `manifests/` (every command and tool version per image),
the symbol-gate report of each image, the CSVs and `SUMMARY.md`.

## Rules
- A row counts only if `parse_log.py` accepted it (env label, KATs, fuzz digest equal to the host
  reference, ELF hash equal to the build, BUILD lines equal to the manifest, identical repeats)
  and the symbol gate passed for that image. `coverage.csv` lists every cell that did not.
- `qemu` rows are instruction counts. Never compare a `qemu` row with a `hardware` row, and never
  call a `qemu` number "cycles".
- Report the run ID with every number taken from this repository.

## Hardware Run Protocol (RP2350 ARM Cortex-M33 Silicon)
The physical silicon target is the Raspberry Pi Pico 2 (RP2350, ARM Cortex-M33); the hardware suite encompasses all 17 `rp2350_arm-*` cells.  
*(Engineering Note on RISC-V: Physical silicon attempts to flash the Hazard3 RISC-V cells directly into SRAM over OpenOCD SWD failed because the RP2350 powers on in ARM mode with the Hazard3 cores clock-gated. Switching active cores on the RP2350 requires the internal Bootrom to parse a UF2 image containing an `IMAGE_DEF` block. To maintain zero-wait-state SRAM execution without flash latency or bootrom jitter, physical silicon testing focuses on ARM Cortex-M33, while RISC-V RV32 baseline and Zbb are evaluated systematically under QEMU instruction counting).*
1. `powershell .\run_hw_benchmark.ps1 -Port COM3` (or `python scripts/run_all.py hw-build && python scripts/run_all.py hw-run --port <COMx> --confirm-hardware`).
2. The runner loads each image into SRAM over SWD via OpenOCD, captures UART0 (GP0/GP1, 115200 8N1) into `raw/<cell>.r<k>.log` with standard run headers, and validates logs with `parse_log.py`.
3. Check the `TIMER` line (`DWT_CYCCNT`, unit `cpu_cycles`) and `HWINFO,dwt_ctrl_at_start` to verify cycle counting on the core processor clock.
4. Complete the row with supply and temperature as measured, and record accepted cells in `MEASUREMENT_LOG.md`.
