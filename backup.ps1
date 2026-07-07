<#
.SYNOPSIS
Create a timestamped backup archive for the analyzer project.

.DESCRIPTION
Part of AutoIt_Static_Analyzer. This script participates in repeatable local development, verification, or release support workflows.

.NOTES
File: backup.ps1
#>
param (
    [switch]$Verbose
)

$ErrorActionPreference = "Stop"

$workspace = Split-Path -Parent $PSScriptRoot
$backupRoot = Join-Path $workspace "_Backups"
if (!(Test-Path $backupRoot)) { New-Item -ItemType Directory -Path $backupRoot | Out-Null }

$projDir = $PSScriptRoot
$jsonPath = Join-Path $projDir "project.json"

if (-not (Test-Path $jsonPath)) {
    Write-Host "ERROR: project.json not found in $projDir." -ForegroundColor Red
    exit 1
}

$config = Get-Content $jsonPath -Raw | ConvertFrom-Json
$projName = $config.project_name
if ([string]::IsNullOrWhiteSpace($projName)) { $projName = (Get-Item $projDir).Name }

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$index = 1
while ($true) {
    $idxStr = $index.ToString("00")
    $zipName = "${projName}_${timestamp}_${idxStr}.zip"
    $zipPath = Join-Path $backupRoot $zipName
    if (-not (Test-Path $zipPath)) { break }
    $index++
}

$ignoreList = @(
    "*\.git\*",
    "*\__pycache__\*",
    "*\.pytest_cache\*",
    "*\temp\*",
    "*\temp_*\*",
    "*\dist\*",
    "*\build\*",
    "*\*.egg-info\*"
)

$filesToZip = New-Object System.Collections.Generic.List[string]
$projFiles = Get-ChildItem -Path $projDir -Recurse -File | Where-Object {
    $path = $_.FullName
    foreach ($ig in $ignoreList) {
        if ($path -like $ig) { return $false }
    }
    return $true
}
foreach ($f in $projFiles) { $filesToZip.Add($f.FullName) }

try {
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zipArchive = [System.IO.Compression.ZipFile]::Open($zipPath, 'Create')

    foreach ($f in $filesToZip) {
        if ($f -match "^$([regex]::Escape($workspace))\\(.*)$") {
            $relPath = $matches[1]
        } else {
            $relPath = "_External\" + (($f -replace ':', '_') -replace '\\', '_')
        }
        [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zipArchive, $f, $relPath) | Out-Null
    }

    $zipArchive.Dispose()
    Write-Host "Backup success: " -NoNewline
    Write-Host $zipPath -ForegroundColor Green
} catch {
    if ($zipArchive) { $zipArchive.Dispose() }
    Write-Host "Error creating Zip: $_" -ForegroundColor Red
    exit 1
}
