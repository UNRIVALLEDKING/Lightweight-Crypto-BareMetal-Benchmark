<#
.SYNOPSIS
    Automated QEMU Runner for LWC Multi-Language Benchmark
    Runs the full simulation pipeline across Cortex-M33 and RISC-V targets.

.EXAMPLE
    .\run_qemu_benchmark.ps1
    .\run_qemu_benchmark.ps1 -Arch armv8m
    .\run_qemu_benchmark.ps1 -Arch rv32imac_zbb
#>
[CmdletBinding()]
param(
    [ValidateSet("all", "armv8m", "rv32imac", "rv32imac_zbb")]
    [string]$Arch = "all",
    [int]$Repeats = 1
)

$ErrorActionPreference = "Stop"
$RepoRoot = if ($PSScriptRoot) { $PSScriptRoot } else { (Get-Location).Path }
Set-Location $RepoRoot

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "     LWC Multi-Language QEMU Benchmark Pipeline           " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Target Arch : $Arch"
Write-Host "Repeats     : $Repeats per cell"
Write-Host ""

$cmd = @("run", "scripts/run_pipeline.py", "--repeats", $Repeats)
if ($Arch -ne "all") {
    $cmd += @("--arch", $Arch)
}

& uv $cmd

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "[SUCCESS] QEMU pipeline completed and validated!" -ForegroundColor Green

    $latestRun = (Get-ChildItem -Path "$RepoRoot/results/runs" -Directory | Sort-Object CreationTime -Descending | Select-Object -First 1).FullName
    if ($latestRun -and (Test-Path "$latestRun/metrics_summary.csv")) {
        Write-Host ""
        Write-Host "==========================================================" -ForegroundColor Cyan
        Write-Host "                QEMU RUN RESULTS SUMMARY                  " -ForegroundColor Cyan
        Write-Host "==========================================================" -ForegroundColor Cyan
        & uv run scripts/summary_report.py $latestRun
    }
} else {
    Write-Host ""
    Write-Host "[WARNING] QEMU benchmark pipeline failed. Check latest results/runs folder." -ForegroundColor Yellow
}
