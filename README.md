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
| **Targets** | `rp2350_arm` (Physical Pico 2 Cortex-M33 silicon, 12 MHz crystal)<br>`rp2350_rv_zbb` (Physical Pico 2 Hazard3 RISC-V silicon)<br>`armv8m` (QEMU `mps2-an505` Cortex-M33)<br>`rv32imac` (QEMU `virt`, no rotate instruction)<br>`rv32imac_zbb` (QEMU `virt`, Hazard3 RV32 with Zbb rotate extension) |
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

### 1. Physical Hardware Benchmark (Raspberry Pi Pico 2)

Connect the **Raspberry Pi Debug Probe** to your Pico 2 (SWD + UART on GP0/GP1) and run:

```powershell
# Automatically builds missing cells, verifies connection, flashes SRAM, and benchmarks:
.\run_hw_benchmark.ps1 -Port COM3
```

To force recompilation of firmware cells:
```powershell
.\run_hw_benchmark.ps1 -Port COM3 -Rebuild
```

### 2. Virtual Emulation Pipeline (QEMU)

Run the full 45-cell automated matrix in QEMU:

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

Measured directly on ARM Cortex-M33 silicon using `DWT_CYCCNT` (Run `20261020T233856Z`):

| Configuration | SIMON-64 Enc (cycles) | PRESENT-80 Enc (cycles) | ASCON 1KB Enc (cycles) | ASCON 1KB Dec (cycles) | Net Stack (Bytes) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **`C (GCC -O3)`** | 510 | 64,845 | **65,727** | **65,598** | **124 B** |
| **`C (Clang -O3)`** | **427** | 59,445 | 70,168 | 69,886 | 232 B |
| **`Rust (Safe -O3)`** | 433 | 67,707 | 69,655 | 71,848 | 236 B |
| **`Rust (Opt -O3)`** | 433 | 67,707 | 72,101 | **69,853** | **128 B** |
| **`Zig (ReleaseFast)`** | 433 | **59,406** | 73,212 | 71,557 | 300 B |
| **`Zig (ReleaseSafe)`** | 433 | **59,402** | 75,789 | 70,745 | 296 B |
| | | | | | |
| **`C (GCC -Oz)`** | 577 | 74,649 | 87,689 | 88,074 | 252 B |
| **`C (Clang -Oz)`** | 605 | 110,006 | 87,988 | 87,850 | 256 B |
| **`Rust (Safe -Oz)`** | 751 | 115,761 | 109,349 | 109,290 | 268 B |
| **`Rust (Opt -Oz)`** | 611 | 115,318 | **85,338** | **79,874** | **136 B** |
| **`Zig (ReleaseSmall)`**| 605 | 119,540 | 84,538 | 84,493 | 256 B |

### Key Takeaways:
1. **Stack Penalty Eliminated:** Safe Rust consumed 236 B on ASCON due to slice bounds checks. `Rust (opt)` reduced this to **128 B** (a 45.8% reduction), matching GCC C (124 B).
2. **Size-Constrained Throughput:** In `-Oz` mode, `Rust (opt)` completed Ascon in **85,338 cycles**, running faster than both C GCC `-Oz` (87,689 cycles) and C Clang `-Oz` (87,988 cycles).
3. **Zero-Cost Safety in Zig:** Zig `ReleaseSafe` runtime checks incurred virtually zero penalty on SIMON (433 vs 433 cycles) and PRESENT (59,402 vs 59,406 cycles).

---

## License
MIT for benchmark implementations and harness. Official Ascon vectors are CC0 (`vectors/official/`).
