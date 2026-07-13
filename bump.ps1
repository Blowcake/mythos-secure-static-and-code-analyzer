<#
.SYNOPSIS
Update project version metadata consistently.

.DESCRIPTION
Part of AutoIt_Static_Analyzer. This script participates in repeatable local development, verification, or release support workflows.

.NOTES
File: bump.ps1
#>
param (
    [Parameter(Position=0)]
    [ValidateSet("patch", "minor", "major", "set")]
    [string]$Type = "patch",

    [Parameter(Position=1)]
    [string]$ManualVersion = ""
)

$ErrorActionPreference = "Stop"
$projDir = $PSScriptRoot
$jsonPath = Join-Path $projDir "project.json"
$pyprojectPath = Join-Path $projDir "pyproject.toml"
$initPath = Join-Path $projDir "src\autoit_static_analyzer\__init__.py"
$doxyPath = Join-Path $projDir "Doxyfile"
$analyzerPath = Join-Path $projDir "src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py"
$settingsPath = Join-Path $projDir "tools_wrapper\au3Mythos_Settings.au3"
$setupPath = Join-Path $projDir "tools_installer\Setup_au3Mythos_x64.au3"
$uninstallPath = Join-Path $projDir "tools_installer\Uninstall_au3Mythos_x64.au3"


if (-not (Test-Path $jsonPath)) {
    Write-Host "ERROR: project.json not found in $projDir." -ForegroundColor Red
    exit 1
}

$config = Get-Content $jsonPath -Raw | ConvertFrom-Json
$currentVersion = $config.version
if ([string]::IsNullOrWhiteSpace($currentVersion)) { $currentVersion = "0.1.0" }

$rx = '^(\d+)\.(\d+)\.(\d+)$'
if ($currentVersion -notmatch $rx) {
    Write-Host "WARNING: Current version '$currentVersion' is not X.Y.Z. Resetting to 0.1.0." -ForegroundColor Yellow
    $major = 0; $minor = 1; $patch = 0
} else {
    $major = [int]$matches[1]
    $minor = [int]$matches[2]
    $patch = [int]$matches[3]
}

switch ($Type) {
    "patch" { $patch += 1 }
    "minor" { $minor += 1; $patch = 0 }
    "major" { $major += 1; $minor = 0; $patch = 0 }
    "set" {
        if ($ManualVersion -notmatch $rx) {
            Write-Host "ERROR: Manual version must be in X.Y.Z format." -ForegroundColor Red
            exit 1
        }
        $major = [int]$matches[1]
        $minor = [int]$matches[2]
        $patch = [int]$matches[3]
    }
}

$newVersion = "$major.$minor.$patch"
$config.version = $newVersion
Set-Content -Path $jsonPath -Value ($config | ConvertTo-Json -Depth 10)

if (Test-Path $pyprojectPath) {
    $text = Get-Content $pyprojectPath -Raw
    $text = [regex]::Replace($text, '(?m)^version\s*=\s*".*"', "version = `"$newVersion`"")
    Set-Content -Path $pyprojectPath -Value $text
}

if (Test-Path $initPath) {
    $text = Get-Content $initPath -Raw
    $text = [regex]::Replace($text, '__version__\s*=\s*".*"', "__version__ = `"$newVersion`"")
    Set-Content -Path $initPath -Value $text
}

if (Test-Path $doxyPath) {
    $text = Get-Content $doxyPath -Raw
    $text = [regex]::Replace($text, '(?m)^PROJECT_NUMBER\s*=.*$', "PROJECT_NUMBER         = `"$newVersion`"")
    Set-Content -Path $doxyPath -Value $text
}

if (Test-Path $analyzerPath) {
    $text = Get-Content $analyzerPath -Raw
    $text = [regex]::Replace($text, '__version__\s*=\s*".*"', ('__version__ = "' + $newVersion + '"'))
    Set-Content -Path $analyzerPath -Value $text
}

if (Test-Path $settingsPath) {
    $text = Get-Content $settingsPath -Raw
    $text = [regex]::Replace($text, '(?i)"Version \d+\.\d+\.\d+"', ('"Version ' + $newVersion + '"'))
    Set-Content -Path $settingsPath -Value $text
}

if (Test-Path $setupPath) {
    $text = Get-Content $setupPath -Raw
    $text = [regex]::Replace($text, '(?i)"Version \d+\.\d+\.\d+"', ('"Version ' + $newVersion + '"'))
    $text = [regex]::Replace($text, '(?i)"DisplayVersion"\s*,\s*"REG_SZ"\s*,\s*"\d+\.\d+\.\d+"', ('"DisplayVersion", "REG_SZ", "' + $newVersion + '"'))
    Set-Content -Path $setupPath -Value $text
}

if (Test-Path $uninstallPath) {
    $text = Get-Content $uninstallPath -Raw
    $text = [regex]::Replace($text, '(?i)"Version \d+\.\d+\.\d+"', ('"Version ' + $newVersion + '"'))
    Set-Content -Path $uninstallPath -Value $text
}



Write-Host "Version bumped successfully: " -NoNewline
Write-Host "$currentVersion " -ForegroundColor DarkGray -NoNewline
Write-Host "-> " -NoNewline
Write-Host "$newVersion" -ForegroundColor Green

Write-Host "`nRun " -NoNewline
Write-Host ".\build.ps1" -ForegroundColor Cyan -NoNewline
Write-Host " to validate the project."
