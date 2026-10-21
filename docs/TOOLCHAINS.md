# Toolchains, flags and installation

The single source of truth for flags is `scripts/lwc_matrix.py`; every image also prints the
exact flags it was built with (`BUILD,backend_flags` / `BUILD,harness_flags`) and each cell's
`manifest.json` lists every command that ran.

## 1. Tools

| Tool | Used for | Version on the development machine (2026-10-09; xPack zips checked against their published SHA-256) | Install |
| :--- | :--- | :--- | :--- |
| clang / ld.lld / llvm-nm | C and C++ (clang cells), the harness, linking every image, symbol gate | clang 23.1.2 | `winget install LLVM.LLVM`; or set `LLVM_BIN` |
| arm-none-eabi-gcc / g++ | C and C++ gcc cells, Arm | xPack GNU Arm Embedded GCC 15.2.1 (20251203), `xpack-arm-none-eabi-gcc-15.2.1-1.1` | unzip the xPack release (https://github.com/xpack-dev-tools/arm-none-eabi-gcc-xpack/releases) into `~/xpack/` (found automatically), or set `ARM_GCC_BIN`; alternatively `scoop bucket add extras; scoop install gcc-arm-none-eabi` |
| riscv-none-elf-gcc / g++ | C and C++ gcc cells, RV32 | xPack GNU RISC-V Embedded GCC 15.2.0, `xpack-riscv-none-elf-gcc-15.2.0-1` | unzip the xPack release (https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases) into `~/xpack/`, or set `RISCV_GCC_BIN` (also found: `riscv32-unknown-elf-`, `riscv64-unknown-elf-`) |
| rustc / cargo | Rust cells, Rust host library | rustc 1.99.0 (LLVM 23.1.1), channel `stable` | https://rustup.rs, then `rustup target add thumbv8m.main-none-eabi riscv32imac-unknown-none-elf` |
| zig | Zig cells; also the C/C++/Zig **host** libraries (`zig cc`) | 0.16.0 (LLVM 21.1.0) | `scoop install zig` |
| QEMU | running the images | 11.1.0 (`qemu-system-arm`, `qemu-system-riscv32`) | `scoop install qemu` or `winget install SoftwareFreedomConservancy.QEMU`; or set `QEMU_BIN` |
| Python | all scripts | 3.11.9 | python.org / `scoop install python` |

Tools are looked up on PATH and in the usual Windows install directories (see
`lwc_matrix.py`). A missing compiler makes its cells *skipped*, with the install command in
`coverage.csv`; it never makes another compiler stand in.

Machine names were checked with `qemu-system-arm -machine help` (`mps2-an505  ARM MPS2 with
AN505 FPGA image for Cortex-M33`) and `qemu-system-riscv32 -machine help` (`virt`, `sifive_e`, ...).
`virt` is used for RV32 (RAM at 0x80000000, `-bios none`).

## 2. Targets

| | armv8m | rv32imac | rv32imac_zbb (adds the Zbb rotate extension) |
| :--- | :--- | :--- | :--- |
| clang | `--target=thumbv8m.main-none-eabi -mcpu=cortex-m33 -mthumb -mfloat-abi=soft` | `--target=riscv32-unknown-elf -march=rv32imac_zicsr -mabi=ilp32` | `--target=riscv32-unknown-elf -march=rv32imac_zicsr_zbb -mabi=ilp32` |
| gcc | `-mcpu=cortex-m33 -mthumb -mfloat-abi=soft` | `-march=rv32imac_zicsr -mabi=ilp32` | `-march=rv32imac_zicsr_zbb -mabi=ilp32` |
| Rust | `thumbv8m.main-none-eabi`, `-C target-cpu=cortex-m33` | `riscv32imac-unknown-none-elf` | `riscv32imac-unknown-none-elf`, `-C target-feature=+zbb` |
| Zig | `-target thumb-freestanding-eabi -mcpu cortex_m33` | `-target riscv32-freestanding-none -mcpu generic_rv32+m+a+c+zicsr` | `... -mcpu generic_rv32+m+a+c+zicsr+zbb` |
| QEMU | `-M mps2-an505 -cpu cortex-m33` | `-M virt -bios none -cpu rv32,zbb=false` | `-M virt -bios none -cpu rv32,zbb=true` |
| Memory | code 0x10000000 (4 MiB), data 0x38000000 (2 MiB), Secure aliases | code 0x80000000, data 0x80400000 | same |
| Console / exit | Arm semihosting (`BKPT 0xAB`) | RISC-V semihosting (`slli; ebreak; srai`) | same |
| Timer | DWT CYCCNT if it runs, else SysTick | `mcycle` | `mcycle` |

Hardware targets (Raspberry Pi Pico 2, built and checked by `run_all.py hw-build`, run only on the board):

| | rp2350_arm | rp2350_rv_zbb |
| :--- | :--- | :--- |
| compiler flags | identical to `armv8m` | identical to `rv32imac_zbb` (Hazard3 has C and Zbb, datasheet 3.8) |
| Memory | SRAM: code+rodata 0x20000000 (384 KiB), data+bss+stack 0x20060000 (136 KiB) | same |
| Boot | RAM-only UF2, family 0xe48bff59 (Arm Secure); IMAGE_DEF with VECTOR_TABLE item | family 0xe48bff5a; IMAGE_DEF with ENTRY_POINT item |
| Console / exit | UART0 on GP0/GP1, 115200 8N1; `EXIT,<code>` line, then a loop | same |
| Timer | DWT CYCCNT if it counts, else SysTick (processor clock) | `mcycle` |

Extra host tools for a board run: `pyserial` (`python -m pip install pyserial`); optional `picotool` or
OpenOCD as loader. The UF2 files are written by `scripts/rp2350_image.py` (no picotool needed).

QEMU options used for every run: `-nographic -monitor none -serial none -chardev
file,id=semihost,path=<log> -semihosting-config enable=on,target=native,chardev=semihost
-icount shift=6,align=off,sleep=off`. (On Windows the default semihosting console is not
captured when stdout is redirected, hence the chardev file.)

## 3. Backend flags per language

| Language | Flags (besides the target flags) |
| :--- | :--- |
| C | `-std=c99 -ffreestanding -ffunction-sections -fdata-sections -fno-common -Wall -Wextra -Wpedantic` + `-O3` / `-Oz` |
| C++ | `-std=c++17 -ffreestanding -fno-exceptions -fno-rtti -fno-threadsafe-statics -fno-use-cxa-atexit -nostdinc++ -ffunction-sections -fdata-sections -Wall -Wextra -Wpedantic` + `-O3` / `-Oz` |
| Rust | `cargo rustc --lib --crate-type staticlib --profile <speed, speed-ovf, size, size-ovf>`; profiles in `ciphers/rust/Cargo.toml`: opt-level 3 / "z", `overflow-checks` false / true, `lto = false`, `codegen-units = 1`, `panic = "abort"` |
| Zig | `zig build-lib -O <ReleaseFast, ReleaseSafe, ReleaseSmall> -ffunction-sections -fdata-sections -fno-PIC -fno-compiler-rt -fno-ubsan-rt -fsingle-threaded -fno-unwind-tables -fstrip` |
| Harness (all images) | clang `-O2 -std=c11 -ffreestanding -ffunction-sections -fdata-sections -Werror -fno-common -Wall -Wextra` |
| Link (all images) | clang driver: `-nostdlib -fuse-ld=lld -static -T harness/<arch>/link.ld --gc-sections -Map=... --fatal-warnings` (+ libgcc for gcc cells, after the shared helpers) |

libgcc for gcc cells: Arm uses the `thumb/v8-m.main/nofp` multilib. The xPack RISC-V GCC has no
`rv32imac` multilib and its default one is 64-bit, so `rv32imc/ilp32` (a strict subset) is used for
libgcc only; `build_all.py` refuses to link the default multilib. In RUN-002 no gcc image pulled any
code from libgcc (the shared helpers in `harness/common/builtins.c` come first).

`ciphers/zig/build.zig` is kept for convenience; the benchmark uses the `zig build-lib`
command above.

## 4. C ABI and prefixes

| Backend | Prefix | Declaration |
| :--- | :--- | :--- |
| C | `lwc_c_` | C function |
| C++ | `lwc_cpp_` | `extern "C"` function |
| Rust | `lwc_rs_` | `#[no_mangle] pub unsafe extern "C" fn` |
| Zig | `lwc_zig_` | `export fn ... callconv(.c)` |

## 5. Host libraries (correctness only, never timed)

`python scripts/build_all.py --target host` writes `build/host/lwc_{c,cpp,zig}.dll` (with `zig cc`,
`zig c++`, `zig build-lib -dynamic -O ReleaseSafe`) and `lwc_rust.dll` (cargo cdylib, release).
On Linux/macOS the same command produces `.so` files.
