# Methodology

## 1. Question
Does the implementation language (C, C++, Rust, Zig), with its compiler and safety profile,
change the work done, the code size and the stack use of the same lightweight ciphers on
32-bit microcontroller cores? The algorithm structure, the harness, the inputs, the target
and the optimisation class are held fixed; only the backend changes.

## 2. Environments and what each may claim

| `env` label | Where | Timer | What a number means |
| :--- | :--- | :--- | :--- |
| `qemu` | QEMU 11.1 `mps2-an505` (Cortex-M33), `virt` (RV32) with `-icount shift=6` | Arm: SysTick (QEMU has no DWT CYCCNT); RV32: `mcycle` | **Instructions executed** (`metric = qemu_instructions`). Not cycles. |
| `hardware` | Raspberry Pi Pico 2 (RP2350), image in SRAM, log over UART0 (`run_all.py hw-run`) | Arm: DWT CYCCNT if it counts, else SysTick on the processor clock; Hazard3: `mcycle` | Core clock cycles (`metric_kind = cpu_cycles`). |

`run_qemu.py` labels every log it writes `RUN,env,qemu`. `parse_log.py` rejects a log with
no label, refuses to validate qemu and hardware logs together, and writes `metric_kind` in every row,
so a table can never mix the two silently. Physical hardware runs on the Raspberry Pi Pico 2 are documented in [Methodology.md](../Methodology.md).

### The Pico 2 (hardware) set-up, as built and statically checked
- Targets `rp2350_arm` and `rp2350_rv_zbb` use exactly the compiler flags of `armv8m` and `rv32imac_zbb`;
  `hw_check.py` confirms the backend object code is byte-identical to the QEMU cell's. Only start-up, linker
  script, console and timer differ (`harness/rp2350_*`); `harness/common` is shared unchanged.
- The image is loaded into SRAM (0x20000000-0x20082000, 520 KiB, datasheet 2.2.3) by the bootrom from a
  RAM-only UF2 and never executes from flash, so no XIP cache is in the measurement path. A bootrom IMAGE_DEF
  block (datasheet 5.9.5) declares it a Secure Arm or a RISC-V executable.
- Core clock 12 MHz: clk_sys = clk_ref = crystal oscillator, no PLL (`soc.c`; printed as `RUN,clock_hz`).
  SRAM has no wait states, so cycle counts should not depend on the clock; this is untested.
- Arm timer: the datasheet contradicts itself on the Cortex-M33 cycle counter (3.7.4.11 lists DWT CYCCNT;
  the DWT_CTRL table gives NOCYCCNT = 1). The image probes CYCCNT at run time regardless of the bit, prints
  `HWINFO,dwt_ctrl_at_start,...`, and falls back to SysTick with CLKSOURCE = processor clock (Table 195).
  Hazard3: `mcycle`, enabled by clearing `mcountinhibit.CY` (reset value 1, datasheet 3.8).
- Interrupts are masked before `main`; the watchdog is disabled.
- SRAM banks (datasheet 4.2): 0x20000000-0x2003ffff is word-striped across SRAM0-3, 0x20040000-0x2007ffff
  across SRAM4-7. Code and rodata (at most 141 KB from 0x20000000) are in SRAM0-3, .data/.bss/stack (0x20060000)
  in SRAM4-7, so instruction fetch never shares a bank with stack or buffer accesses; it can with rodata loads
  (S-boxes, round constants, KAT tables). Not controlled further; noted as a threat.

### Why `-icount`, and what was checked
Measured on this setup with a probe image (2026-10-09):
- QEMU's mps2-an505 does not implement DWT CYCCNT: `DWT_CTRL` reads 0 and `CYCCNT` never
  advances. `timing_armv8m.c` detects this at start-up and falls back to SysTick.
- Without `-icount` both counters follow host time: the same loop measured 15,000-80,000
  `mcycle` and the results were not monotonic in the work done. Such numbers are meaningless.
- With `-icount shift=s` QEMU advances virtual time by 2^s ns per executed instruction:
  - RV32 `mcycle` = instructions x 2^s exactly (a 5-instruction loop gave 5,014 for 1,000 passes at s=0);
  - Arm SysTick runs at 20 MHz of virtual time (50 ns per tick), so ticks = instructions x 2^s / 50,
    rounded down. `s = 6` gives 1.28 ticks per instruction (resolution about 0.8 instruction).
- Every image times a 2-instruction assembly loop (1,000,000 passes, `CALIBRATION` line);
  `parse_log.py` converts ticks to instructions with the ratio from the image itself, so no
  clock frequency is hard-coded. Observed: Arm 2,560,010 ticks, RV32 128,000,064 ticks for
  2,000,000 instructions.
- Under `-icount` repeated runs of one image in one session gave identical SUMMARY lines, and the samples
  of one operation differ by at most one tick. Across sessions RV32 results were identical; on Arm (SysTick,
  1.28 ticks per instruction) a raw median differed by one tick in 1 of 210 rows, and min/p5/p95/max by a tick
  in a few more (RUN-002 vs RUN-003). So Arm values are exact only to about one tick (0.8 instruction), and
  repeating a run adds no statistics: these are counts, there are no confidence intervals to compute.

### What instruction counts do and do not tell
They count the instructions each toolchain's code executes for the same work. That is a sound basis
for comparing code generation (e.g. a bounds check that survives, a helper call instead of
inline code). They ignore everything that makes instructions cost different numbers of cycles:
pipeline stalls, multi-cycle multiply/load/branch, flash wait states, caches. A 64-bit shift
done by a 3-instruction sequence and by a call to a 20-instruction helper are weighted by
instruction count only. **Do not report these numbers as cycles or as time.**

### Targets
| target | ISA | QEMU CPU | Why |
| :--- | :--- | :--- | :--- |
| `armv8m` | Cortex-M33 (Armv8-M Mainline, has `ROR`) | `-cpu cortex-m33` | |
| `rv32imac` | RV32IMAC, no bit-manipulation | `-cpu rv32,zbb=false` | baseline: no rotate instruction |
| `rv32imac_zbb` | RV32IMAC + Zbb (`ror`, `rori`, `rol`, ...) | `-cpu rv32,zbb=true` | the RP2350's Hazard3 core has Zbb; isolates the effect of rotate |

`build_all.py` verifies the ISA of every RV32 image by disassembly: the SIMON encrypt function must contain
`ror`/`rori` with Zbb (3, in all four languages) and none without. Control: a Zbb image run on a CPU with
Zbb off dies with an illegal-instruction fault (`mcause = 2`), so QEMU really switches the extension.

## 3. Implementations
All four backends implement the same algorithms with the same loop structure and export the
C ABI of `ciphers/include/lwc_api.h` under their own prefix.

| Cipher | Variant | Notes |
| :--- | :--- | :--- |
| SIMON | 64/128, 44 rounds | |
| PRESENT | PRESENT-80, 31 rounds | **Naive bit-by-bit pLayer**, deliberately: it measures how each compiler handles a bit loop, not the best PRESENT. |
| Ascon | **Ascon-AEAD128, NIST SP 800-232** | 128-bit rate, p12/p8, little-endian. Verified against all 1,089 official vectors on the host and inside every image. Ascon-128 v1.2 was removed. |

C++ is freestanding C++17: no exceptions, no RTTI, no standard library headers, `constexpr`
tables; its objects have no undefined symbols. Rust is `#![no_std]`, `panic = "abort"`; a
panic calls the harness (`lwc_panic`) and fails the run. Zig uses `std.debug.no_panic`: a safety
check traps and the harness fault handler fails the run.

## 4. Profiles: matched optimisation, separate safety

| opt class | C / C++ (gcc, clang) | Rust | Zig |
| :--- | :--- | :--- | :--- |
| `O3` | `-O3` | `opt-level = 3` (`O3`, `O3-ovf`) | `ReleaseFast`, `ReleaseSafe` |
| `Oz` | `-Oz` | `opt-level = "z"` (`Oz`, `Oz-ovf`) | `ReleaseSmall` |

- LLVM-level match, checked in the emitted LLVM IR: Zig ReleaseSmall gives functions the same
  `minsize optsize` attributes as clang `-Oz`; ReleaseFast/ReleaseSafe set neither (speed). The
  exact pass pipeline is each front end's own choice and was not compared.
- Safety column: C/C++ `none`; Rust `bounds` (slice bounds checks cannot be disabled) or
  `bounds+overflow` (`overflow-checks = true`); Zig `none` (ReleaseFast/Small) or `all` (ReleaseSafe).
  Zig has no safe size mode.
- **Inlining policy: hints only, in all four languages.** C/C++ use `static inline` / `inline`, Rust uses
  `#[inline]`, Zig uses plain `fn` (Zig has no hint: LLVM decides). Nothing is forced (`always_inline`,
  `#[inline(always)]`, Zig `inline fn`). The first version forced inlining in Rust and Zig only; that made their
  size-optimised Ascon 3-5x larger than C (Arm backend flash: Rust 6,332 B, Zig 5,532 B, clang C 1,788 B) and
  the numbers of RUN-002/RUN-003 must not be used. After the change (build of 2026-10-09): Rust 2,572 B,
  Zig 1,870 B, clang C 1,788 B on Arm; Rust 3,248 B, Zig 3,802 B, clang C 1,846 B on RV32. What is left is each
  compiler's own choice, not the source: the permutation is 630 B in both C and Rust on RV32; Rust adds slice
  bounds checks and keeps an out-of-line `load64_le` (266 B), and in the Zig image the permutation has no
  separate symbol, so LLVM placed its code inside both entry points (inferred from the symbol table).
- Rust: `lto = false`, `codegen-units = 1` (one object compiled once, like a C file);
  `-C target-cpu=cortex-m33` on Arm. `core` is the precompiled rustup copy (opt-level 3,
  generic CPU); what the backend pulls from it is counted as `backend_runtime` in the size report.
- Every image is linked by ld.lld with `--gc-sections`. The harness is compiled once per target
  with clang `-O2` and is byte-identical in every image of that target.
- Compiler runtime helpers: size-optimised builds call 64-bit shift helpers
  (`__aeabi_llsl`/`__aeabi_llsr`, `__ashldi3`/`__lshrdi3`) and Zig on Arm calls `__aeabi_memclr`. These
  and `memcpy`/`memset`/... are defined once in `harness/common/{rt,builtins}.c` and linked before
  every backend, so all languages use the same helper code. The size report lists, per image, which helpers it needed.

## 5. One backend per image, and the controls
Each image links exactly one backend. The controls:
1. **Symbol gate** (`check_symbols.py`, on every image): all 8 entry points of the expected backend
   are defined functions; no symbol of another backend's prefix and no legacy name is present.
2. **KATs inside the image**: SIMON, PRESENT and all 1,089 official Ascon-AEAD128 vectors, including
   a tampered tag that must be rejected and the plaintext wiped. A failure stops the run before timing.
3. **Differential fuzz inside the image**: 1,000 xorshift32-generated inputs per cipher, folded into one
   FNV-1a digest per cipher. Every image must print the digest of the four host libraries.
4. **Host tests**: JSON KATs, the official vectors and a 10,000-input random differential fuzz
   (seed printed) over the C, C++, Rust and Zig host libraries.
5. **Provenance**: every image prints its cell, compiler version, flags and git commit. `parse_log.py`
   checks them against the build manifest, checks that the ELF that ran is the current build (SHA-256),
   and requires repeated runs to be identical.
6. Every return code of every timed call is checked. A wrapped counter is reported as an error.

Each control was checked to fail when it should (2026-10-09): a corrupted Rust Ascon constant
gives KAT 0/1089; a Zig out-of-bounds read fails the KAT under ReleaseFast and traps under ReleaseSafe;
a Rust overflow panics under `O3-ovf` and fails the KAT under `O3`; an image with a foreign backend
symbol fails the gate; logs with a changed digest, a missing env label or a stale ELF are rejected.

## 6. Measurement protocol
- One call per sample: counter read, call through the backend table, counter read. 20 warm-up calls,
  then 10 batches x 100 calls (`--batches/--iters`; use more on hardware).
- Inputs change every call (block ciphers, Ascon encryption nonce). Ascon decryption is timed on the valid
  ciphertext and tag (success path). Buffers pass through compiler barriers.
- Arm reads are preceded by `isb` (ordering only). The timer overhead (two back-to-back reads) is
  measured and subtracted from the median.
- Reported: min, p5, median, p95, max, mean, samples > 4x median, per-batch medians and their spread.
  **The median is the primary statistic.**

## 7. Size and stack
- Size: from the ld.lld map after `--gc-sections`, per input section, attributed to `backend`,
  `backend_runtime`, `harness_runtime`, `harness_kat`, `harness`; backend split by cipher by section
  name (best effort; unattributed sections are `shared`).
- Stack: the free stack below the caller is painted, one call is made, and the deepest overwritten
  word gives the depth. The probe's own cost (`EMPTY_PROBE`) is subtracted in `stack.csv`.

## 8. Observed effects explained by disassembly
Checked in the disassembly (`llvm-objdump`), not assumed. Numbers are QEMU instruction counts.

- **Rust PRESENT encrypt on Arm is slower without overflow checks** (`O3` 68,240 vs `O3-ovf` 55,221). This is not
  a cost of the checks. LLVM unrolls the naive 64-step bit-permutation loop in both builds and replaces `(i*16) % 63`
  by a multiply-by-reciprocal. Without overflow checks it uses the 32-bit form (`umull` with the constant
  `0x04104105`, eight at a time, with many stack spills; 423 static instructions). With overflow checks it uses a cheap
  16-bit form (`uxth; mul; lsrs #21`; 351 static instructions, no `umull`). The checked build is faster, plausibly because
  the check lets the compiler assume `i*16` does not wrap (not proven). The same loop gives other
  differences in other cells (RV32 `O3-ovf` decrypt is 25% slower than `O3`), so PRESENT timings vary by up to
  about 25% with how `%63` is lowered. Do not quote them as a safety cost.
- **Zig SIMON encrypt is 14 instructions (4.5%) above clang C on Arm** (323 vs 309). Both compilers unroll four rounds
  per iteration. Zig's loop is 27 instructions against 26 (+11 over 11 iterations) and its prologue/epilogue 24
  against 19 (frame pointer `r7`, an extra saved `r11`, an alignment `nop`): +16 predicted, +14 measured, within the
  one-tick resolution. In the first runs ReleaseSafe looked faster than ReleaseFast; with matched inlining the two are
  identical (SIMON has no checks to add), so that was an artifact of forced inlining.
- **Ascon at `Oz`**: see the inlining policy in section 4. The remaining Rust/Zig size gap is compiler choice plus Rust bounds checks.
- **SIMON on RV32 with and without Zbb** (RUN-004, clang C O3; Rust, Zig and gcc agree to about 1%): encrypt takes 840 instructions
  without Zbb and 577 with it (-31%); Cortex-M33 takes 309. So the missing rotate instruction explains about half of the
  RV32-to-Arm gap (2.7x becomes 1.9x). The rest is the base ISA: Thumb-2 folds the rotate into the operand of `and`/`eor`
  (`and r5, r5, r3, ror #24`), which RISC-V cannot. PRESENT is unchanged by Zbb (no rotates); Ascon 1 KiB encrypt improves 7%
  (77,663 -> 72,143). The second reason is read from the disassembly of the Arm loop, not tested separately.

## 9. Threats to validity
- **QEMU is not a cycle model** (section 2). Instruction counts can rank toolchains differently from cycles.
- gcc cells link the rv32imc libgcc on RV32 (no rv32imac multilib in the xPack build); no image used it.
- Different back ends: GCC 15.2 (Arm 15.2.1), clang 23.1.2, rustc's LLVM 23.1.1, Zig 0.16.0's LLVM 21.1.0.
- Rust `core` is precompiled for a generic CPU; C/C++/Zig have no equivalent library.
- The shared helpers are plain C byte loops and shift routines; a toolchain's own optimised runtime
  (libgcc, compiler-rt) could be faster.
- PRESENT is the naive variant; Ascon is AEAD128 only; one key schedule per call for the block ciphers.
- Timing resolution on Arm is about 0.8 instruction: differences below about 2% on SIMON are at the limit.
- One version per toolchain; the optimiser's choices change between versions (the PRESENT effect above is an example).
- Single run environment (one QEMU version, one host). No energy, side-channel or constant-time analysis.
