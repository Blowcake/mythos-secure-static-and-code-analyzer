<#
.SYNOPSIS
Run the analyzer project build, unit tests, CLI smoke test, and Doxygen generation.

.DESCRIPTION
Part of AutoIt_Static_Analyzer. This script participates in repeatable local development, verification, or release support workflows.

.NOTES
File: build.ps1
#>
param(
    [switch]$RunBurninSmoke
)

$ErrorActionPreference = "Stop"
$projDir = $PSScriptRoot
$jsonPath = Join-Path $projDir "project.json"

if (-not (Test-Path $jsonPath)) {
    Write-Host "ERROR: project.json not found in $projDir." -ForegroundColor Red
    exit 1
}

$config = Get-Content $jsonPath -Raw | ConvertFrom-Json
$entrypoint = Join-Path $projDir $config.entrypoint
if (-not (Test-Path $entrypoint)) {
    Write-Host "ERROR: Entrypoint file does not exist -> $entrypoint" -ForegroundColor Red
    exit 1
}

$env:PYTHONDONTWRITEBYTECODE = "1"
$env:PYTHONPATH = Join-Path $projDir "src"

Write-Host "Syntax check: $($config.entrypoint)" -ForegroundColor Cyan
python -c "import ast, pathlib; ast.parse(pathlib.Path(r'$entrypoint').read_text(encoding='utf-8'))"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running unit tests..." -ForegroundColor Cyan
python .\tests\test_lexer_helpers.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\tests\test_warning_fixtures.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\tests\test_json_and_lookup.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\tests\test_wrapper_e2e.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python .\tests\test_installer_e2e.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Checking package CLI..." -ForegroundColor Cyan
python -m autoit_static_analyzer --help | Out-Null
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Running Doxygen..." -ForegroundColor Cyan
$doxyFile = Join-Path $projDir "Doxyfile"
if (-not (Test-Path $doxyFile)) {
    Write-Host "ERROR: Doxyfile not found in $projDir." -ForegroundColor Red
    exit 1
}

$doxygenCmd = Get-Command doxygen -ErrorAction SilentlyContinue
if (-not $doxygenCmd) {
    $stdDoxygen = "C:\Program Files\doxygen\bin\doxygen.exe"
    if (Test-Path $stdDoxygen) { $doxygenCmd = $stdDoxygen }
}
if (-not $doxygenCmd) {
    Write-Host "ERROR: Doxygen was not found in PATH or standard installation path 'C:\Program Files\doxygen\bin\doxygen.exe'." -ForegroundColor Red
    exit 1
}

$doxygenOut = Join-Path $projDir "docs\doxygen"
if (-not (Test-Path $doxygenOut)) { New-Item -ItemType Directory -Path $doxygenOut -Force | Out-Null }
& $doxygenCmd $doxyFile
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($RunBurninSmoke) {
    Write-Host "Running burn-in system includes analysis..." -ForegroundColor Cyan
    & (Join-Path $projDir "examples\run_burnin_analysis.ps1")
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

Write-Host "SUCCESS: Build checks completed." -ForegroundColor Green
