# Physical Pico 2 (RP2350) Hardware Execution & Rust (opt) Backend (2026-10-21)

Physical bare-metal silicon benchmarking executed live on Raspberry Pi Pico 2 (RP2350, Cortex-M33 @ 12 MHz) and introduction of the hardware-optimized Rust backend.

## What changed
1. **Physical Hardware Execution (`RUN-005`, `run_hw_benchmark.ps1`):**
   - Live execution on RP2350 Cortex-M33 using the Raspberry Pi Debug Probe over SWD (OpenOCD @ 5000 kHz).
   - High-speed direct-to-SRAM boot (`0x20000000`) without flash erase, eliminating flash wait states and XIP cache misses.
   - Core clock pinned at 12.0 MHz (direct crystal oscillator, PLL disabled).
   - High-precision cycle counting via ARM Cortex-M33 `DWT_CYCCNT` with baseline overhead subtraction.
   - All 11 hardware cells passed all 4 verification gates (symbol gate, 1,089 NIST Ascon KAT vectors, PRNG fuzz digest, and size report), accepting 154 benchmark rows.
2. **Hardware-Optimized Rust Backend (`Rust (opt)`, `ciphers/rust_opt/`):**
   - New isolated backend exporting prefix `lwc_rso_` without altering core cipher algorithms.
   - Replaced slice windowing and bounds checking with raw unaligned pointer arithmetic (`core::ptr::read_unaligned`, `write_unaligned`) and unchecked lookup table indexing.
   - Constant-time tag verification with zeroing of plaintext on authentication failure.
   - Cut Ascon stack memory depth from 236 B down to 128 B (-45.8%), matching GCC C (124 B).
   - Achieved 85,338 cycles on Ascon-1024B in size-constrained mode (`-Oz`), beating C GCC -Oz (87,689 cyc) and C Clang -Oz (87,988 cyc).
3. **One-Command Automation & Methodological Documentation:**
   - Created `run_hw_benchmark.ps1` for 1-command end-to-end SWD flashing, execution, and tabular reporting.
   - Authored `Methodology.md` in repository root providing full empirical research documentation.

# Verification and Pico 2 (RP2350) hardware preparation (2026-10-14, branch `hw-prep`)

No cipher backend and no build flag of the 45 QEMU cells changed.

## What changed
1. **Verification** (`results/verification/VERIFICATION_REPORT.md`): toolchains, host tests, full strict
   QEMU matrix, regression against RUN-004 (`scripts/compare_runs.py`), controls, metric completeness and a
   code review for hardware risks.
2. **Pico 2 harness** (`harness/rp2350_arm`, `harness/rp2350_rv`, `harness/rp2350_common`): image in SRAM with a
   bootrom IMAGE_DEF block, clocks from the 12 MHz crystal, UART0 console on GP0/GP1 (115200 8N1) instead of
   semihosting, cycle timers (Arm: DWT CYCCNT probed at run time, SysTick fallback; Hazard3: mcycle), unit
   `cpu_cycles`. Every register value cites the RP2350 datasheet or the Pico SDK; the rest is `TODO(verify)`.
3. **Two hardware targets** `rp2350_arm` and `rp2350_rv_zbb` (30 cells, build only; the default matrix is still
   the 45 QEMU cells). Flags copied from `armv8m` / `rv32imac_zbb`; the backend code is byte-identical.
   UF2 files written by `scripts/rp2350_image.py`; static checks by `scripts/hw_check.py`.
4. **`parse_log.py`**: `metric_kind` column (`qemu_instructions` / `cpu_cycles`), hardware log rules, refuses
   to validate qemu and hardware logs together, ELF hash checked for hardware logs too.
5. **`scripts/run_all.py`** (`qemu`, `hw-build`, `hw-run`), `scripts/hw_preflight.py`, `metrics_summary.csv`,
   `run_pipeline.py --run-id`; tests in `tests/` that need no board.

## Not tested
- Nothing ran on a Pico 2. `hw-run`, the UART/clock code, the IMAGE_DEF/UF2 boot and both timers on silicon
  are untested; `hw_preflight.py` lists the open `TODO(verify)` items.

# Fixes after external review of RUN-002 (2026-10-09)

RUN-002 and RUN-003 are **superseded**: their Rust/Zig numbers used forced inlining that C/C++ did not.

## What changed
1. **Inlining policy matched (hints only).** Rust `#[inline(always)]` -> `#[inline]` and Zig `inline fn` -> `fn`
   (17 sites each); C/C++ unchanged. Backend flash of Ascon at Oz on Arm: Rust 6,332 -> 2,572 B, Zig 5,532 -> 1,870 B
   (clang C 1,788 B). The remaining differences are explained in `docs/METHODOLOGY.md` section 4.
2. **New target `rv32imac_zbb`** (RV32IMAC + Zbb rotate, as in the RP2350's Hazard3 core): 15 more cells, 45 in total.
   The plain `rv32imac` target now pins `zbb=false` in QEMU. Every RV32 image is checked by disassembly for rotate
   instructions (present with Zbb in all four languages, absent without). A Zbb image on a CPU without Zbb faults,
   proving QEMU applies the extension.
3. **The two unexplained results were explained from the disassembly** (methodology section 8): Rust PRESENT is a
   `%63` lowering effect (32-bit `umull` + spills vs a 16-bit multiply), not a safety cost; the Zig SIMON ReleaseSafe/
   ReleaseFast difference was an inlining artifact and disappeared, and Zig's remaining +4.5% over clang C is a longer
   prologue plus one extra instruction per loop iteration.
4. **Records**: old result folders removed from the tree (still in git history, pointers in `docs/MEASUREMENT_LOG.md`);
   RUN-003 logged as the superseded baseline. Correction: cross-session runs are identical on RV32 but can differ by one
   SysTick tick on Arm, so "deterministic" was too strong; stated in the methodology. Timing resolution (about 0.8
   instruction on Arm), "counts, not samples, so no confidence intervals" and one-version-per-toolchain added to the threats.

## Result
RUN-004 (`results/runs/20261009T030619Z`, git 902ef6f, clean): 45/45 cells built, gated, run twice and accepted. SIMON on RV32 drops from 840 to 577
instructions with Zbb (Cortex-M33: 309).

## Still open
- The `%63` PRESENT cause is consistent with the code but not proven (no-wrap assumption); a table-driven PRESENT would remove it.
- Hardware run; `LICENSE` copyright holder ("Bare-Metal LWC Research Group") is for the authors to decide.

# Migration to a runtime-free QEMU build: C, C++, Rust, Zig on Cortex-M33 and RV32 (2026-10-09)

## What changed
1. **ESP32 / ESP-IDF / FreeRTOS / Xtensa removed.** The CMake firmware build, toolchain file and
   old harness are gone; ESP and "Bare-Metal" naming removed from Cargo.toml, README, CITATION,
   rust-toolchain.toml (now `stable`, `thumbv8m.main-none-eabi` + `riscv32imac-unknown-none-elf`),
   .gitignore and the docs. (`LICENSE` still names "Bare-Metal LWC Research Group" as copyright
   holder: not changed, it is a legal decision for the authors.)
2. **Ascon-AEAD128 (NIST SP 800-232)** replaces Ascon-128 v1.2 in every backend
   (`<prefix>_ascon_aead128_{encrypt,decrypt}`). Official vectors: all 1,089 from ascon-c commit
   446347f2 (`crypto_aead/asconaead128`), cross-checked with the designers' pyascon. v1.2 removed
   (nothing compares against it). Fixed on the way: the C null check used `&&` between `pt` and
   `ct`; Rust and Zig no longer form slices from null pointers for zero lengths.
3. **New C++ backend** `ciphers/cpp` (`lwc_cpp_`): freestanding C++17, `-fno-exceptions -fno-rtti`,
   `constexpr` tables, no standard library; mirrors the C code.
4. **New harness** (`harness/common`, `harness/arm`, `harness/riscv`): start-up, linker scripts,
   semihosting console/exit, fault reporting; `timing_armv8m.c` (DWT CYCCNT with SysTick
   fallback) and `timing_rv32.c` (mcycle); in-image KATs (all 1,089 Ascon vectors), deterministic
   fuzz digest, stack watermark, integer-only statistics, timer calibration. One backend per image.
   Shared `memcpy`/`memset`/shift helpers so no language gets a different runtime.
5. **Build matrix** language x compiler x profile x target (`scripts/lwc_matrix.py`,
   `scripts/build_all.py`, direct compiler calls, no CMake): C/C++ with gcc and clang at O3/Oz;
   Rust O3/Oz with overflow-checks off/on; Zig ReleaseFast/ReleaseSafe/ReleaseSmall. Exact tool
   versions and every flag go into each image (`BUILD` lines) and `manifest.json`.
6. **Controls kept and extended**: symbol gate on every image (exactly one backend), KATs and the
   fuzz digest inside QEMU compared with the four host libraries, ELF-hash and manifest checks on
   every log, identical-repeat check, env label (`qemu`/`hardware`) required on every log.
7. **Size from the linker map** (`--gc-sections`, by component and cipher); **stack watermark**.
8. **Scripts**: `run_qemu.py`, `parse_log.py`, `run_pipeline.py` rewritten for the matrix; results
   go to `results/runs/<run id>/`. Host tests rewritten on a shared `host/lwc_host.py`; the
   MSVC/CMake host runner removed (host libraries are built with `zig cc` / cargo).
9. Docs rewritten: README, METHODOLOGY, TOOLCHAINS, MEASUREMENT_LOG, vectors/SOURCES.

## Tested (2026-10-09, Windows 10, QEMU 11.1.0, clang 23.1.2, rustc 1.99.0, zig 0.16.0)
- Host: C, C++, Rust, Zig pass the JSON KATs, 1,089/1,089 official vectors (encrypt, decrypt,
  tampered tag) and a 10,000-input random differential fuzz.
- QEMU: 22 of 30 cells built, passed the symbol gate, ran twice with identical results, passed all
  in-image KATs and printed the host's fuzz digest (run RUN-001, `results/runs/20261009T011756Z`).
- The controls fail when they should: corrupted Rust constant, Zig out-of-bounds read (ReleaseFast
  and ReleaseSafe), Rust overflow (O3 and O3-ovf), a foreign symbol in an image, tampered logs.
- Measured, not assumed: QEMU mps2-an505 has no working DWT CYCCNT (SysTick fallback is used);
  without `-icount` counters follow host time; with `-icount shift=6` they count instructions.

## Update: full matrix (RUN-002, `results/runs/20261009T014812Z`)
- Installed xPack arm-none-eabi-gcc 15.2.1 and riscv-none-elf-gcc 15.2.0 (SHA-256 verified) in `~/xpack/`.
- RV32: no `rv32imac` multilib in that GCC (default is 64-bit); libgcc taken from `rv32imc/ilp32`,
  and `build_all.py` now refuses the default multilib. No gcc image pulled code from libgcc.
- `--strict` pipeline: 30/30 built, gated, run twice (identical), accepted; the 22 non-gcc cells
  reproduce RUN-001 exactly.

## Not tested / could not be done
- (Resolved in RUN-002: xPack GCC installed, all 30 cells built, ran and were accepted.)
- **No hardware run.** All results are `env=qemu` instruction counts; no number here is a cycle count.
  The hardware path (DWT CYCCNT, mcycle as cycles, `env=hardware` logs) is written but never ran.
- The DWT branch of `timing_armv8m.c` never executed (QEMU lacks CYCCNT).
- Linux/macOS: scripts written to be portable, run only on Windows.

## Still open
- A hardware run (Cortex-M33 board, RV32 board) before any cycle or time claim.
- RUN-001 shows effects that need a disassembly-level explanation before they are written up, e.g.
  Rust `O3` PRESENT encryption executes more instructions on Arm than Rust `O3-ovf` (68,240 vs
  55,221), and Rust `Oz` pulls 2.6 KiB (Arm) / 1.9 KiB (RV32) of `core` that `O3` does not.
- A table-driven PRESENT variant; confirm `CITATION.cff` authors and URL; LICENSE holder.

# Changes after the first measurement campaign (ESP32 era, superseded by the section above)

## What was wrong
1. **Rust and Zig were never measured.** All three languages exported identical symbol names and
   `main.c` passed the same function pointers under the labels "C", "Rust" and "Zig". The linker
   keeps one definition (first library wins, silently), so one function was timed three times.
2. **Stale configuration.** An existing `sdkconfig` overrides `SDKCONFIG_DEFAULTS`; the `-O0` and
   `-Os` runs were the same ELF (same SHA-256), and the size reports were identical for all profiles.
3. **Libraries not matched to the profile.** The Rust CMake always linked `release/`, and the Zig
   build was never given an Xtensa target; a failed Zig build was only "skipped".
4. **Cycle counter.** QEMU's counter is not a stable cycle clock (the same binary reported SIMON at
   48 to 80 cycles in archived runs; a later build reported 832).
5. **Statistics.** Means and standard deviations were dominated by outliers (max 61,024 vs ~1,000).
6. **Test harness.** `run_vectors.py` exited 0 even when a KAT failed; `differential.py` exited 0
   when fewer than two libraries were present; the ASCON decrypt benchmark timed tampered input; the
   decrypt function pointer used the encrypt prototype; key-schedule "cycles per byte" was meaningless.
7. **Documentation.** `MEASUREMENT_LOG.md` described a physical board, supply voltage and ambient
   temperature that were never used; "cycle-accurate / hardware-accurate" described QEMU data; the
   ASCON variant was cited to the wrong standard; several tool versions disagreed with the logs.

## What was changed
- Per-language symbol prefixes (`lwc_c_`, `lwc_rs_`, `lwc_zig_`) in all sources, `lwc_api.h`
  (`LWC_DECLARE_BACKEND`), the host tests and the C KAT runner.
- `main.c`: calls the right backend per section; a missing backend prints SKIPPED; prints a `BUILD` line.
- `report.h/.c`, `bench.c`: single stats type, median/p5/p95/outlier count, per-batch medians in `DATA`,
  timer-overhead calibration, valid-path ASCON decrypt, corrected function-pointer type.
- Component CMake: profile-matched Rust/Zig library paths, `LWC_HAVE_*` definitions, `LWC_PLATFORM`.
- `build_all.py`: clean `sdkconfig` per profile, optimisation assertion, stale-library deletion, hard
  failures, symbol gate, manifest, duplicate-ELF rejection. `--zig skip` and `--platform` options.
- `check_symbols.py` (new), `parse_log.py` (validates the run), `size_report.py` (per-prefix classes),
  `run_pipeline.py` (forwards options, validates).
- Host tests fail loudly; `run_official_ascon_kat.py` and the official KAT file added.
- Docs rewritten: README, METHODOLOGY, TOOLCHAINS, MEASUREMENT_LOG, vectors/SOURCES. Old results moved
  to `results/_INVALID_pre_symbol_fix/` with an explanation.

## Tested vs untested
Tested on x86-64 in a sandbox: the three libraries build, pass all vectors and the differential fuzz;
a deliberately corrupted Rust cipher is caught (non-zero exit); C, Rust and Zig link into one binary
with distinct symbols and identical output; the symbol gate passes and fails correctly; the harness
statistics code compiles warning-free and its log parses (with the mock timer on the host).

**NOT tested (no ESP-IDF, QEMU, Xtensa Rust or Xtensa Zig available):** the ESP-IDF build, the
CMake `LWC_HAVE_*`/`LWC_OPT` plumbing, `build_all.py` on Windows, the Xtensa Zig flags
(`-Dtarget=xtensa-freestanding -Dcpu=esp32`), `run_qemu.py`, and every number the firmware will print.
Expect to debug these first. If something fails, fix it; do not bypass a gate.

## Still open
- A table-driven PRESENT variant (the naive one measures a deliberately slow implementation).
- A real ESP32 board for any absolute-cycle claim.
- Decide whether to keep Ascon-128 v1.2 or move to Ascon-AEAD128 (SP 800-232), consistently with paper 1.
- Confirm `CITATION.cff` authors and repository URL.
