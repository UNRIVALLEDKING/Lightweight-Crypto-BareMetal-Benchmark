# lwc-lang-bench

Empirical multi-language benchmarking of lightweight cryptography on bare-metal microcontroller silicon.

Does the implementation language and its safety invariants change the real CPU cycle cost, memory depth, and code size of lightweight ciphers on 32-bit embedded cores? **SIMON-64/128**, **PRESENT-80**, and **Ascon-AEAD128** (NIST SP 800-232) are implemented with identical algorithmic structure in **C, C++, Rust (safe idiomatic), Rust (hardware-optimized), and Zig**.

Measurements are conducted across two complementary environments:
1. **Physical Microcontroller Silicon (`env=hardware`):** Real CPU cycles via `DWT_CYCCNT` on **Raspberry Pi Pico 2 (RP2350, ARM Cortex-M33 @ 12 MHz)** loaded into SRAM over SWD via OpenOCD.
2. **Deterministic Virtual Emulation (`env=qemu`):** Instruction counts under QEMU `-icount` across Cortex-M33 and RISC-V RV32IMAC (with and without the Zbb rotate extension).

For the complete theoretical foundation, experimental setup, and verification criteria, see [**Methodology.md**](Methodology.md).

---

## The Matrix

| Axis | Values |
| :--- | :--- |
| **Targets** | **Physical Silicon (`env=hardware`):**<br>- `rp2350_arm` (Raspberry Pi Pico 2, ARM Cortex-M33 @ 12 MHz crystal, SRAM execution)<br><br>**Deterministic Emulation (`env=qemu`):**<br>- `armv8m` (QEMU `mps2-an505` Cortex-M33)<br>- `rv32imac` (QEMU `virt`, baseline RISC-V RV32 without rotate)<br>- `rv32imac_zbb` (QEMU `virt`, Hazard3 RISC-V RV32 with Zbb bitmanip rotate extension) |
| **Languages & Compilers** | **C & C++** with GCC and Clang<br>**Rust** (safe idiomatic) with `rustc`<br>**Rust (opt)** (hardware-optimized raw pointers & unchecked indexing) with `rustc`<br>**Zig** with `zig` |
| **Optimization Profiles** | **O3 (Speed):** `-O3` (C/C++), `O3`/`O3-ovf` (Rust safe), `O3` (Rust opt), `ReleaseFast` / `ReleaseSafe` (Zig)<br>**Oz (Code Size):** `-Oz` (C/C++), `Oz`/`Oz-ovf` (Rust safe), `Oz` (Rust opt), `ReleaseSmall` (Zig) |

---

## Repository Layout

```text
ciphers/include/lwc_api.h      C ABI shared across all backends: lwc_c_ lwc_cpp_ lwc_rs_ lwc_rso_ lwc_zig_
ciphers/c/                     C99 implementations (freestanding)
ciphers/cpp/                   C++17 implementations (freestanding, no exceptions/RTTI)
ciphers/rust/                  Safe idiomatic Rust (#![forbid(unsafe_op_in_unsafe_fn)], slice bounds checked)
ciphers/rust_opt/              Hardware-optimized Rust (raw pointers, unchecked indexing, minimal stack)
ciphers/zig/                   Zig 0.16 implementations (ReleaseFast, ReleaseSafe, ReleaseSmall)
harness/common/                Shared harness: KATs, fuzz digest, dynamic stack watermarking, timing
harness/arm/                   Armv8-M Cortex-M33: startup, semihosting, DWT CYCCNT, SysTick
harness/riscv/                 RISC-V RV32: startup, mcycle timer, link.ld
harness/rp2350_{arm,rv,common} Raspberry Pi Pico 2: direct SRAM execution, clocks, UART0 console
host/                          Differential fuzzing (10k random iterations) and official NIST vectors
scripts/run_all.py             Unified coordinator: qemu, hw-build, and hw-run modes
scripts/build_all.py           Cross-compiler manager: builds host DLLs and embedded firmware cells
run_hw_benchmark.ps1           1-command automated hardware runner for Pico 2 over Debug Probe SWD
run_qemu_benchmark.ps1         1-command automated QEMU simulation pipeline runner
Methodology.md                 Detailed empirical methodology, verification gates, and findings
```

---

## 4 Verification Gates

To ensure zero experimental contamination, every image must pass 4 verification gates before any metric is accepted:
1. **Symbol Purity Gate (`check_symbols.py`):** Verified via `llvm-nm` that the image contains exactly the 8 required entry points of its declared backend and zero foreign or legacy symbols.
2. **On-Chip Known Answer Tests (`kat.c`):** All 1,089 official NIST Ascon-AEAD128 vectors (encryption, decryption, and tag tampering plaintext-zeroing) must pass on the microcontroller.
3. **Differential PRNG Fuzzing:** A 1,000-iteration deterministic PRNG stream (xorshift32) must produce a digest identical to the host reference.
4. **Linker Map Attribution (`size_report.py`):** LLD map file is parsed after `--gc-sections` to classify Flash footprint into cipher backend, runtime, and harness.

---

## How to Run

### 1. Physical Hardware Benchmark (Raspberry Pi Pico 2 - ARM Cortex-M33)

Connect the **Raspberry Pi Debug Probe** to your Pico 2 (SWD + UART on GP0/GP1) and run:

```powershell
# Automatically builds missing cells, verifies connection, flashes SRAM, and benchmarks:
.\run_hw_benchmark.ps1 -Port COM3
```

To force recompilation of all 17 firmware cells:
```powershell
.\run_hw_benchmark.ps1 -Port COM3 -Rebuild
```

### 2. Virtual Emulation Pipeline (QEMU - ARM & RISC-V)

Run the full automated matrix across Cortex-M33, RV32 baseline, and RV32+Zbb under QEMU:

```powershell
.\run_qemu_benchmark.ps1
```

Or invoke the Python coordinator directly:
```bash
uv run python scripts/run_all.py qemu
```

### 3. Cross-Language Host Differential Fuzzing

Verify mathematical equivalence across C, C++, Safe Rust, Rust (opt), and Zig on the host:

```bash
uv run python scripts/build_all.py --target host
uv run python host/differential.py
```

---

## Physical Hardware Findings (RP2350 Cortex-M33 @ 12 MHz)

Measured directly on physical ARM Cortex-M33 silicon using `DWT_CYCCNT` (Run `20261021T214313Z`, all 17 cells passed all 4 verification gates, 238 rows accepted):

| Configuration | Profile / Safety | SIMON-64 Enc (cycles) | PRESENT-80 Enc (cycles) | ASCON 1KB Enc (cycles) | ASCON 1KB Dec (cycles) | Net Stack (Bytes) | Backend Flash (Bytes) | Total Linked Flash (Bytes)* |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **`C (GCC -O3)`** | Speed / none | 510 | 64,845 | **65,727** | **65,598** | **124 B** | 8,814 | 8,814 |
| **`C (Clang -O3)`** | Speed / none | **427** | 59,445 | 70,168 | 69,886 | 232 B | 10,756 | 10,756 |
| **`C++ (GCC -O3)`** | Speed / none | 510 | 64,844 | **65,727** | **65,598** | **124 B** | 8,814 | 8,814 |
| **`C++ (Clang -O3)`** | Speed / none | **427** | 59,447 | 70,168 | 69,886 | 232 B | 10,756 | 10,756 |
| **`Rust (Safe -O3)`** | Speed / bounds | 433 | 67,707 | 69,655 | 71,848 | 236 B | 11,506 | 11,506 |
| **`Rust (Safe -O3-ovf)`** | Speed / bounds+ovf | 433 | **59,246** | 74,024 | 73,641 | 224 B | 9,164 | 9,164 |
| **`Rust (Opt -O3)`** | Speed / unchecked | 433 | 67,707 | 73,205 | 73,444 | 240 B | 11,426 | 11,426 |
| **`Zig (ReleaseFast)`** | Speed / none | 433 | 59,406 | 73,212 | 71,557 | 300 B | 10,534 | 10,534 |
| **`Zig (ReleaseSafe)`** | Speed / all | 433 | 59,402 | 75,789 | 70,745 | 296 B | 9,820 | 9,820 |
| | | | | | | | | |
| **`C (GCC -Oz)`** | Size / none | 577 | 74,649 | 87,689 | 88,074 | 252 B | 3,600 | 3,600 |
| **`C (Clang -Oz)`** | Size / none | 605 | 110,006 | 87,988 | 87,850 | 256 B | 2,930 | 2,930 |
| **`C++ (GCC -Oz)`** | Size / none | 584 | 76,108 | 87,752 | 88,330 | 252 B | 3,616 | 3,616 |
| **`C++ (Clang -Oz)`** | Size / none | **604** | 116,727 | 87,724 | 87,906 | 256 B | 2,854 | 2,854 |
| **`Rust (Safe -Oz)`** | Size / bounds | 751 | 115,761 | 109,349 | 109,290 | 268 B | 4,540 | 7,218* |
| **`Rust (Safe -Oz-ovf)`** | Size / bounds+ovf | 751 | 114,682 | 109,551 | 109,493 | 272 B | 4,628 | 7,417* |
| **`Rust (Opt -Oz)`** | Size / unchecked | 611 | 115,633 | **86,202** | **86,219** | 268 B | 2,906 | 2,906 |
| **`Zig (ReleaseSmall)`** | Size / none | 605 | 119,540 | **84,538** | **84,493** | 256 B | **2,780** | **2,780** |

*\*Total Linked Flash includes `backend_runtime_flash` (e.g. 2,678 B of `compiler_builtins` / `core` runtime linked by Safe Rust `-Oz`).*

### Key Takeaways:
1. **Inlining Policy & Code Size at -Oz:** Converting `#[inline(always)]` to advisory `#[inline]` in `ciphers/rust_opt` enabled LLVM to optimize for code size under `-Oz`. Backend flash dropped from **6,752 B down to 2,906 B (-57%)**, achieving footprint and throughput comparable to C Clang `-Oz` (2,930 B and 87,988 cycles) and beating C GCC `-Oz` (3,600 B and 87,689 cycles). Meanwhile, Zig `ReleaseSmall` produced the single most compact binary (**2,780 B**) and fastest size-optimized throughput on Ascon (**84,538 cycles**).
2. **Stack Attribution & Safety Invariants:** `Rust (opt)` `-O3` stack depth measured **240 B**, closely matching Safe Rust (**236 B**) and Clang C (**232 B**). This empirical result does not support the hypothesis that Rust's stack usage is inherently inflated by language safety invariants or slice bounds checks. Stack consumption is governed by LLVM helper inlining (`ascon_absorb_ad`) and call-frame construction, where GCC allocates 124 B and LLVM allocates ~232-240 B.
3. **C++ Abstraction Overheads:** At `-O3`, freestanding C++17 matches C cycle-for-cycle and byte-for-byte across GCC and Clang. At `-Oz`, minor compiler code-generation divergences emerge on the bit-permutation layer of PRESENT-80 (+6.1% cycles in Clang, +2.0% in GCC), while SIMON and Ascon remain within 0.1% of C.
4. **Rust Overflow Checks & The PRESENT-80 Compiler Effect:** Enabling arithmetic overflow checks (`-ovf`) added 0% overhead on SIMON-64 (433 vs 433 cycles) and a modest 6.2% overhead on Ascon-1024B (74,024 vs 69,655 cycles). Counter-intuitively, on PRESENT-80, the overflow-checked binary executed **12.5% faster** on silicon (59,246 vs 67,707 cycles) and compiled **20.4% smaller** (9,164 B vs 11,506 B), matching a 19.1% instruction reduction in QEMU. Observed disassembly reveals that LLVM emitted a 351-instruction sequence using 16-bit multiplies (`uxth; mul`) for checked builds vs. a 423-instruction sequence with 32-bit `umull` operations and register spills for unchecked builds; while we hypothesize that overflow tracking altered the cost model for lowering `(i * 16) % 63`, the exact compiler heuristic linking the overflow intrinsic to this choice remains unproven, and it is reported strictly as an observed compiler artifact.
5. **Zig Safety Efficiency & Compactness:** Zig `ReleaseSafe` incurred zero penalty on SIMON (433 vs 433 cycles) and PRESENT (59,402 vs 59,406 cycles), and a measured 3.5% cycle overhead (6.8% in QEMU instructions) on Ascon-1024B encryption. Zig `ReleaseSmall` produced the single most compact binary across the entire suite (**2,780 B**).

---

## License
MIT for benchmark implementations and harness. Official Ascon vectors are CC0 (`vectors/official/`).
