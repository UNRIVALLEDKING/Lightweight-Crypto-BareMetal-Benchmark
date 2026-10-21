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
| RUN-004 | 2026-10-09 | qemu | `results/runs/20261009T030619Z/` | 45 / 45 | **Current QEMU baseline.** After the review fixes: hint-only inlining in all languages and the new `rv32imac_zbb` target (45 cells). git `902ef6f` (clean, no `-dirty`), `--strict`, built from an empty `build/`. 2 repeats per image, identical. Tools: clang 23.1.2, rustc 1.99.0 (LLVM 23.1.1), zig 0.16.0, xPack GCC 15.2.1 (Arm) / 15.2.0 (RISC-V), QEMU 11.1.0. 161 s. All 45 cells pass the symbol gate, in-image KATs and the fuzz digest; the 15 Zbb cells contain rotate instructions, the 30 others none. |
| RUN-005 | 2026-10-21 | hardware | `results/runs/20261020T233856Z/` | 11 / 11 | **Physical Hardware Campaign.** Raspberry Pi Pico 2 (RP2350, ARM Cortex-M33 @ 12.0 MHz, crystal oscillator, DWT_CYCCNT, image in SRAM, OpenOCD over SWD via Debug Probe). Benchmarks C (GCC, Clang), Rust (Safe & Hardware-Optimized), and Zig across O3 and Oz. All 11 cells passed all 4 verification gates (154 rows accepted, 0 rejected). |

`results/runs/<id>/` holds the raw logs, `manifests/` (every command and tool version per image),
the symbol-gate report of each image, the CSVs and `SUMMARY.md`.

## Rules
- A row counts only if `parse_log.py` accepted it (env label, KATs, fuzz digest equal to the host
  reference, ELF hash equal to the build, BUILD lines equal to the manifest, identical repeats)
  and the symbol gate passed for that image. `coverage.csv` lists every cell that did not.
- `qemu` rows are instruction counts. Never compare a `qemu` row with a `hardware` row, and never
  call a `qemu` number "cycles".
- Report the run ID with every number taken from this repository.

## Recording a hardware run (none made yet)
The board is a Raspberry Pi Pico 2 (RP2350); the hardware cells are `rp2350_arm-*` and `rp2350_rv_zbb-*`.
1. `python scripts/run_all.py hw-build` (build + static checks) and `python scripts/hw_preflight.py`.
2. `python scripts/run_all.py hw-run --port <COMx> --confirm-hardware [--log]`. It loads each image into
   SRAM, captures UART0 (GP0/GP1, 115200 8N1) into `raw/<cell>.r<k>.log` with the header lines
   `RUN,env,hardware`, `RUN,cell`, `RUN,board`, `RUN,arch`, `RUN,elf_sha256`, ...; the image itself prints
   `RUN,clock_hz`. `parse_log.py` validates them with the same rules as QEMU logs plus the hardware ones.
3. Check the `TIMER` line (`DWT_CYCCNT`, `SYSTICK` on the processor clock, or `MCYCLE`, unit `cpu_cycles`)
   and the `HWINFO,dwt_ctrl_at_start` line: they settle the datasheet's contradiction on the M33 cycle counter.
4. Complete the row (the `--log` draft) with supply and temperature *as measured*, and record which
   `TODO(verify)` items the run confirmed.
