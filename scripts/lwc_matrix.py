"""
The benchmark matrix (language x compiler x profile x target) and tool discovery.

Shared by build_all.py, run_qemu.py, parse_log.py, size_report.py and run_pipeline.py.
Every image ("cell") contains the common harness plus exactly ONE cipher backend.
"""

import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUILD_DIR = REPO_ROOT / "build"

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
TARGETS = {
    "armv8m": {
        "desc": "Arm Cortex-M33 (Armv8-M Mainline), QEMU mps2-an505",
        "dir": "arm",
        "platform_srcs": ["harness/arm/startup.c", "harness/arm/timing_armv8m.c"],
        "clang": ["--target=thumbv8m.main-none-eabi", "-mcpu=cortex-m33", "-mthumb", "-mfloat-abi=soft"],
        "gcc_prefixes": ["arm-none-eabi-"],
        "gcc_env": "ARM_GCC_BIN",
        "gcc": ["-mcpu=cortex-m33", "-mthumb", "-mfloat-abi=soft"],
        "gcc_libgcc": ["-mcpu=cortex-m33", "-mthumb", "-mfloat-abi=soft"],   # multilib thumb/v8-m.main/nofp
        "rust_target": "thumbv8m.main-none-eabi",
        "rust_flags": ["-C", "target-cpu=cortex-m33"],
        "zig": ["-target", "thumb-freestanding-eabi", "-mcpu", "cortex_m33"],
        "qemu_bin": "qemu-system-arm",
        "qemu_args": ["-M", "mps2-an505", "-cpu", "cortex-m33"],
    },
    "rv32imac": {
        "desc": "RISC-V RV32IMAC, QEMU virt",
        "dir": "riscv",
        "platform_srcs": ["harness/riscv/startup.S", "harness/riscv/platform.c", "harness/riscv/timing_rv32.c"],
        "clang": ["--target=riscv32-unknown-elf", "-march=rv32imac_zicsr", "-mabi=ilp32"],
        "gcc_prefixes": ["riscv-none-elf-", "riscv32-unknown-elf-", "riscv64-unknown-elf-"],
        "gcc_env": "RISCV_GCC_BIN",
        "gcc": ["-march=rv32imac_zicsr", "-mabi=ilp32"],
        # xPack riscv-none-elf-gcc 15 has no rv32imac multilib (its default is rv64): use the
        # rv32imc/ilp32 libgcc, a strict subset (libgcc needs no atomics).
        "gcc_libgcc": ["-march=rv32imc", "-mabi=ilp32"],
        "rust_target": "riscv32imac-unknown-none-elf",
        "rust_flags": [],
        "zig": ["-target", "riscv32-freestanding-none", "-mcpu", "generic_rv32+m+a+c+zicsr"],
        "qemu_bin": "qemu-system-riscv32",
        # zbb pinned off so the no-rotate baseline never depends on a QEMU default
        "qemu_args": ["-M", "virt", "-bios", "none", "-cpu", "rv32,zbb=false"],
        "rotate_insns": False,   # build_all.py checks the SIMON encrypt code has no ror/rori
    },
    "rv32imac_zbb": {
        "desc": "RISC-V RV32IMAC + Zbb (rotate; as in the RP2350's Hazard3 core), QEMU virt",
        "dir": "riscv",
        "platform_srcs": ["harness/riscv/startup.S", "harness/riscv/platform.c", "harness/riscv/timing_rv32.c"],
        "clang": ["--target=riscv32-unknown-elf", "-march=rv32imac_zicsr_zbb", "-mabi=ilp32"],
        "gcc_prefixes": ["riscv-none-elf-", "riscv32-unknown-elf-", "riscv64-unknown-elf-"],
        "gcc_env": "RISCV_GCC_BIN",
        "gcc": ["-march=rv32imac_zicsr_zbb", "-mabi=ilp32"],
        # the multilib lookup for ..._zbb falls back to the rv64 default: use rv32imc (libgcc only)
        "gcc_libgcc": ["-march=rv32imc", "-mabi=ilp32"],
        "rust_target": "riscv32imac-unknown-none-elf",
        "rust_flags": ["-C", "target-feature=+zbb"],
        "zig": ["-target", "riscv32-freestanding-none", "-mcpu", "generic_rv32+m+a+c+zicsr+zbb"],
        "qemu_bin": "qemu-system-riscv32",
        "qemu_args": ["-M", "virt", "-bios", "none", "-cpu", "rv32,zbb=true"],
        "rotate_insns": True,    # build_all.py checks the SIMON encrypt code does contain ror/rori
    },
}

# Hardware targets: Raspberry Pi Pico 2 (RP2350). Built and statically checked here, run only on
# the board (scripts/run_all.py hw-run); there is no QEMU machine for this chip. The compiler flags
# are taken from the QEMU target with the same core, so the backend code is the same: only start-up,
# linker script, console (UART instead of semihosting) and timer differ (harness/rp2350_*).
_SAME_CODE = ("clang", "gcc_prefixes", "gcc", "gcc_libgcc", "gcc_env", "rust_target", "rust_flags", "zig")
RP2350 = {
    "board": "Raspberry Pi Pico 2 (RP2350)",
    # RP2350 datasheet 2.2.3 / Pico SDK addressmap.h: SRAM_BASE, SRAM_END (520 KiB)
    "sram": (0x20000000, 0x20082000),
    # the two MEMORY regions of harness/rp2350_*/link.ld
    "regions": {"FLASH": (0x20000000, 0x20060000), "RAM": (0x20060000, 0x20082000)},
    "core_clock_hz": 12000000,            # clk_sys = XOSC, harness/rp2350_common/soc.c
    "uart": {"tx_pin": "GP0", "rx_pin": "GP1", "baud": 115200, "format": "8N1"},
}
TARGETS["rp2350_arm"] = {
    **{k: TARGETS["armv8m"][k] for k in _SAME_CODE if k in TARGETS["armv8m"]},
    "desc": "Raspberry Pi Pico 2 (RP2350) Cortex-M33, image in SRAM, UART console (hardware only)",
    "dir": "rp2350_arm",
    "platform_srcs": ["harness/rp2350_arm/startup.c", "harness/rp2350_arm/timing.c",
                      "harness/rp2350_common/soc.c"],
    "ld_search": ["harness/rp2350_common"],
    "harness_includes": ["-Iharness/rp2350_common"],
    "same_code_as": "armv8m",
    "hardware": {**RP2350, "arch": "arm", "uf2_family": 0xe48bff59,   # rp2350_arm_s (datasheet Table 469)
                 "image_type": 0x1021, "timer": "DWT_CYCCNT if it counts, else SYSTICK (processor clock)"},
}
TARGETS["rp2350_rv_zbb"] = {
    **{k: TARGETS["rv32imac_zbb"][k] for k in _SAME_CODE if k in TARGETS["rv32imac_zbb"]},
    "desc": "Raspberry Pi Pico 2 (RP2350) Hazard3 RV32IMAC + Zbb, image in SRAM, UART console (hardware only)",
    "dir": "rp2350_rv",
    "platform_srcs": ["harness/rp2350_rv/startup.S", "harness/rp2350_rv/platform.c", "harness/rp2350_rv/timing.c",
                      "harness/rp2350_common/soc.c"],
    "ld_search": ["harness/rp2350_common"],
    "harness_includes": ["-Iharness/rp2350_common"],
    "rotate_insns": True,
    "same_code_as": "rv32imac_zbb",
    # Hazard3 on RP2350: RV32I M A C Zicsr Zifencei Zba Zbb Zbs Zbkb Zcb Zcmp (datasheet 3.8, 3.8.1.1)
    "hardware": {**RP2350, "arch": "riscv", "uf2_family": 0xe48bff5a,  # rp2350_riscv (datasheet Table 469)
                 "image_type": 0x1101, "timer": "MCYCLE",
                 "isa": ["i", "m", "a", "c", "zicsr", "zifencei", "zba", "zbb", "zbs", "zbkb", "zca", "zcb", "zcmp",
                         "zmmul", "zaamo", "zalrsc"]},   # zmmul/zaamo/zalrsc: subsets of M and A
}

QEMU_TARGETS = [t for t in TARGETS if "qemu_bin" in TARGETS[t]]
HW_TARGETS = [t for t in TARGETS if "hardware" in TARGETS[t]]

# QEMU timing mode: deterministic instruction counting (see docs/METHODOLOGY.md).
QEMU_ICOUNT = "shift=6,align=off,sleep=off"

# ---------------------------------------------------------------------------
# Languages, compilers, profiles
#   opt_class: the optimisation level the profile is matched to across languages
#   safety:    the language's run-time safety checks in this profile
# ---------------------------------------------------------------------------
LANGS = {
    "C":          {"id": "c",        "prefix": "lwc_c",      "compilers": ["gcc", "clang"]},
    "C++":        {"id": "cpp",      "prefix": "lwc_cpp",    "compilers": ["gcc", "clang"]},
    "Rust":       {"id": "rust",     "prefix": "lwc_rs",     "compilers": ["rustc"]},
    "Rust (opt)": {"id": "rust_opt", "prefix": "lwc_rso",    "compilers": ["rustc"]},
    "Zig":        {"id": "zig",      "prefix": "lwc_zig",    "compilers": ["zig"]},
}

PROFILES = {
    "C": {
        "O3": {"opt_class": "O3", "safety": "none", "flags": ["-O3"]},
        "Oz": {"opt_class": "Oz", "safety": "none", "flags": ["-Oz"]},
    },
    "Rust": {
        "O3":     {"opt_class": "O3", "safety": "bounds", "cargo_profile": "speed"},
        "O3-ovf": {"opt_class": "O3", "safety": "bounds+overflow", "cargo_profile": "speed-ovf"},
        "Oz":     {"opt_class": "Oz", "safety": "bounds", "cargo_profile": "size"},
        "Oz-ovf": {"opt_class": "Oz", "safety": "bounds+overflow", "cargo_profile": "size-ovf"},
    },
    "Rust (opt)": {
        "O3":     {"opt_class": "O3", "safety": "unchecked", "cargo_profile": "speed"},
        "Oz":     {"opt_class": "Oz", "safety": "unchecked", "cargo_profile": "size"},
    },
    "Zig": {
        "ReleaseFast":  {"opt_class": "O3", "safety": "none", "mode": "ReleaseFast"},
        "ReleaseSafe":  {"opt_class": "O3", "safety": "all", "mode": "ReleaseSafe"},
        "ReleaseSmall": {"opt_class": "Oz", "safety": "none", "mode": "ReleaseSmall"},
    },
}
PROFILES["C++"] = PROFILES["C"]

C_SOURCES = ["ciphers/c/simon64_128.c", "ciphers/c/present80.c", "ciphers/c/ascon_aead128.c"]
CPP_SOURCES = ["ciphers/cpp/simon64_128.cpp", "ciphers/cpp/present80.cpp", "ciphers/cpp/ascon_aead128.cpp"]
C_FLAGS = ["-std=c99", "-ffreestanding", "-ffunction-sections", "-fdata-sections", "-fno-common",
           "-Wall", "-Wextra", "-Wpedantic"]
CPP_FLAGS = ["-std=c++17", "-ffreestanding", "-fno-exceptions", "-fno-rtti", "-fno-threadsafe-statics",
             "-fno-use-cxa-atexit", "-nostdinc++", "-ffunction-sections", "-fdata-sections",
             "-Wall", "-Wextra", "-Wpedantic"]
ZIG_FLAGS = ["-ffunction-sections", "-fdata-sections", "-fno-PIC", "-fno-compiler-rt", "-fno-ubsan-rt",
             "-fsingle-threaded", "-fno-unwind-tables", "-fstrip"]

# The harness is identical in every image: one compiler, one set of flags.
HARNESS_FLAGS = ["-O2", "-std=c11", "-ffreestanding", "-ffunction-sections", "-fdata-sections", "-Werror",
                 "-fno-common", "-Wall", "-Wextra"]


@dataclass
class Cell:
    target: str
    lang: str
    compiler: str
    profile: str
    status: str = "pending"            # built | skipped | failed
    reason: str = ""
    info: dict = field(default_factory=dict)

    @property
    def id(self):
        return f"{self.target}-{LANGS[self.lang]['id']}-{self.compiler}-{self.profile}"

    @property
    def dir(self):
        return BUILD_DIR / "cells" / self.id

    @property
    def elf(self):
        return self.dir / "firmware.elf"

    @property
    def map(self):
        return self.dir / "firmware.map"

    @property
    def prof(self):
        return PROFILES[self.lang][self.profile]


def all_cells(targets=None, langs=None, compilers=None, profiles=None):
    """The cells of the given targets (default: the QEMU targets, i.e. the 45-cell matrix)."""
    cells = []
    for t in targets or QEMU_TARGETS:
        for lang in langs or LANGS:
            for comp in LANGS[lang]["compilers"]:
                if compilers and comp not in compilers:
                    continue
                for prof in PROFILES[lang]:
                    if profiles and prof not in profiles:
                        continue
                    cells.append(Cell(t, lang, comp, prof))
    return cells


# ---------------------------------------------------------------------------
# Tool discovery
# ---------------------------------------------------------------------------
INSTALL_HINTS = {
    "clang": "winget install LLVM.LLVM   (or set LLVM_BIN to the LLVM bin directory)",
    "arm-gcc": "scoop install gcc-arm-none-eabi   or   winget install Arm.GnuArmEmbeddedToolchain"
               "   (or set ARM_GCC_BIN)",
    "riscv-gcc": "download xPack riscv-none-elf-gcc: https://github.com/xpack-dev-tools/riscv-none-elf-gcc-xpack/releases"
                 "   (unzip, then set RISCV_GCC_BIN to its bin directory)",
    "cargo": "https://rustup.rs, then: rustup target add thumbv8m.main-none-eabi riscv32imac-unknown-none-elf",
    "zig": "scoop install zig   (or https://ziglang.org/download/)",
    "qemu": "scoop install qemu   or   winget install SoftwareFreedomConservancy.QEMU",
}

_EXE = ".exe" if sys.platform == "win32" else ""


def _which_in(name, dirs):
    for d in dirs:
        if d:
            p = Path(d) / (name + _EXE)
            if p.is_file():
                return str(p)
    return shutil.which(name)


def find_llvm(tool):
    dirs = [os.environ.get("LLVM_BIN"), "C:/Program Files/LLVM/bin", "/usr/lib/llvm/bin", "/opt/homebrew/opt/llvm/bin"]
    return _which_in(tool, dirs)


def find_gcc(target, tool="gcc"):
    """Returns the path of <prefix><tool> for the target, or None."""
    env = os.environ.get(TARGETS[target]["gcc_env"])
    xpack = sorted(str(d) for d in (Path.home() / "xpack").glob("xpack-*-gcc-*/bin"))
    for prefix in TARGETS[target]["gcc_prefixes"]:
        p = _which_in(prefix + tool, [env, *xpack])
        if p:
            return p
    return None


def find_qemu(target):
    name = TARGETS[target]["qemu_bin"]
    dirs = [os.environ.get("QEMU_BIN"), str(Path.home() / "scoop/apps/qemu/current"),
            "C:/Program Files/qemu", "C:/qemu"]
    return _which_in(name, dirs)


def find_tool(name):
    return _which_in(name, [str(Path.home() / ".cargo/bin"), str(Path.home() / "scoop/shims")])


def first_line(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        out = (r.stdout or r.stderr).strip()
        return out.splitlines()[0].strip() if out else "unknown"
    except (OSError, subprocess.TimeoutExpired):
        return "unavailable"


def git_commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=REPO_ROOT,
                               capture_output=True, text=True).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except OSError:
        return "unknown"
