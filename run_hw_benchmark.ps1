<#
.SYNOPSIS
    Automated Physical Hardware Runner for Raspberry Pi Pico 2 (RP2350)
    Benchmarks C, C++, Rust, and Zig across ARM Cortex-M33 & RISC-V Hazard3.

.EXAMPLE
    .\run_hw_benchmark.ps1 -Port COM3
    .\run_hw_benchmark.ps1 -Port COM3 -Arch arm
    .\run_hw_benchmark.ps1 -Port COM3 -Arch rv
#>
[CmdletBinding()]
param(
    [string]$Port = "COM3",
    [int]$Baud = 115200,
    [ValidateSet("all", "arm", "rv")]
    [string]$Arch = "arm",
    [int]$Repeats = 1,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $RepoRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  LWC Multi-Language Hardware Benchmark (RP2350 Pico 2)   " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Serial Port : $Port @ $Baud 8N1"
Write-Host "Target Arch : $Arch"
Write-Host "Repeats     : $Repeats per cell"
Write-Host ""

# 1. Ensure OpenOCD is in PATH
if (-not (Get-Command openocd -ErrorAction SilentlyContinue)) {
    $searchDirs = @("$env:LOCALAPPDATA\openocd_rpi", "C:\Users\adity\AppData\Local\openocd_rpi")
    $rpiOcd = $null
    foreach ($d in $searchDirs) {
        if (Test-Path $d) {
            $found = (Get-ChildItem -Path $d -Recurse -Filter "openocd.exe" -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
            if ($found) { $rpiOcd = $found; break }
        }
    }
    if ($rpiOcd) {
        $ocdDir = Split-Path $rpiOcd
        $env:Path = "$ocdDir;" + $env:Path
        Write-Host "[OK] Added Raspberry Pi OpenOCD to PATH: $ocdDir" -ForegroundColor Green
    } else {
        Write-Error "[FATAL] openocd with RP2350 support not found in PATH or C:\Users\adity\AppData\Local\openocd_rpi"
    }
}

# 2. Check Probe Connection
Write-Host "Checking SWD connection via Raspberry Pi Debug Probe..." -NoNewline
$probeTest = openocd -f interface/cmsis-dap.cfg -f target/rp2350.cfg -c "adapter speed 5000; init; reset halt; exit" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host " [FAIL]" -ForegroundColor Red
    Write-Host $probeTest
    Write-Error "[FATAL] Cannot connect to RP2350 via Debug Probe. Check SWD wiring and USB connection."
}
Write-Host " [CONNECTED]" -ForegroundColor Green

# 3. Select Cells based on Arch
$armCells = @(
    "rp2350_arm-c-gcc-O3",
    "rp2350_arm-c-gcc-Oz",
    "rp2350_arm-c-clang-O3",
    "rp2350_arm-c-clang-Oz",
    "rp2350_arm-rust-rustc-O3",
    "rp2350_arm-rust-rustc-Oz",
    "rp2350_arm-rust_opt-rustc-O3",
    "rp2350_arm-rust_opt-rustc-Oz",
    "rp2350_arm-zig-zig-ReleaseFast",
    "rp2350_arm-zig-zig-ReleaseSafe",
    "rp2350_arm-zig-zig-ReleaseSmall"
)

$rvCells = @(
    "rp2350_rv_zbb-c-gcc-O3",
    "rp2350_rv_zbb-c-gcc-Oz",
    "rp2350_rv_zbb-c-clang-O3",
    "rp2350_rv_zbb-c-clang-Oz",
    "rp2350_rv_zbb-rust-rustc-O3",
    "rp2350_rv_zbb-rust-rustc-Oz",
    "rp2350_rv_zbb-rust_opt-rustc-O3",
    "rp2350_rv_zbb-rust_opt-rustc-Oz",
    "rp2350_rv_zbb-zig-zig-ReleaseFast",
    "rp2350_rv_zbb-zig-zig-ReleaseSafe",
    "rp2350_rv_zbb-zig-zig-ReleaseSmall"
)

$targetCells = @()
if ($Arch -eq "arm") {
    $targetCells = $armCells
} elseif ($Arch -eq "rv") {
    $targetCells = $rvCells
} else {
    $targetCells = $armCells + $rvCells
}

# 4. Ensure host reference fuzz digest exists (required by validation gates)
if (-not (Test-Path "$RepoRoot/build/host/fuzz_digest.json")) {
    Write-Host "[PREP] Generating host libraries and reference fuzz digest..." -ForegroundColor Yellow
    & uv run scripts/build_all.py --target host
    & uv run host/differential.py
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[FATAL] Differential fuzz test failed or could not produce fuzz_digest.json."
    }
}

# 5. Check for missing cell builds or rebuild request and build on-demand
$missing = @()
foreach ($cell in $targetCells) {
    if (-not (Test-Path "$RepoRoot/build/cells/$cell/firmware.elf")) {
        $missing += $cell
    }
}
if ($Rebuild -or $missing.Count -gt 0) {
    $msg = if ($Rebuild) { "Rebuilding all $($targetCells.Count) target cells..." } else { "Missing $($missing.Count) firmware images. Building target cells..." }
    Write-Host "[BUILD] $msg" -ForegroundColor Yellow
    $archList = if ($Arch -eq "arm") { @("rp2350_arm") } elseif ($Arch -eq "rv") { @("rp2350_rv_zbb") } else { @("rp2350_arm", "rp2350_rv_zbb") }
    $buildCmd = @("run", "scripts/build_all.py", "--target", "embedded", "--arch") + $archList + @("--matrix-out", "build/matrix_hw.json")
    & uv $buildCmd
    if ($LASTEXITCODE -ne 0) {
        Write-Error "[FATAL] Failed to build hardware firmware cells."
    }
}

Write-Host "Benchmarking $($targetCells.Count) cells on physical hardware..." -ForegroundColor Yellow
$cmdArgs = @(
    "run", "--with", "pyserial", "scripts/run_all.py", "hw-run",
    "--port", $Port,
    "--confirm-hardware",
    "--repeats", $Repeats,
    "--loader", "openocd",
    "--no-prompt",
    "--cells"
) + $targetCells

& uv $cmdArgs

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[SUCCESS] Hardware benchmark completed and validated!" -ForegroundColor Green

    # Locate the latest run folder
    $latestRun = (Get-ChildItem -Path "$RepoRoot/results/runs" -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1).FullName
    if ($latestRun -and (Test-Path "$latestRun/metrics_summary.csv")) {
        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "              HARDWARE RUN RESULTS SUMMARY                " -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Cyan
        & uv run scripts/summary_report.py $latestRun
    }
} else {
    Write-Host ""
    Write-Host "[WARNING] Benchmark completed with warnings or gate failures. Check latest results/runs folder." -ForegroundColor Yellow
}
