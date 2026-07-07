<#
.SYNOPSIS
Run the analyzer against the AutoIt standard include burn-in fixture.

.DESCRIPTION
Part of AutoIt_Static_Analyzer. This script participates in repeatable local development, verification, or release support workflows.

.NOTES
File: run_burnin_analysis.ps1
#>
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONPATH = (Join-Path $ProjectRoot "src")

$MainFile = Join-Path $ProjectRoot "tests\all_system_includes.au3"
$OutDir = Join-Path $ProjectRoot "scratch_burnin_analysis"

python -m autoit_static_analyzer $MainFile --out-dir $OutDir --enable-experimental-checks
