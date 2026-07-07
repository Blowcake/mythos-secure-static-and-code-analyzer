Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$projectJsonPath = Join-Path $projectRoot "project.json"

if (-not (Test-Path -LiteralPath $projectJsonPath)) {
    throw "project.json not found in $projectRoot"
}

$project = Get-Content -LiteralPath $projectJsonPath | ConvertFrom-Json
$projectName = if ($project.project_name) { [string]$project.project_name } else { "AutoIt_Static_Analyzer" }
$version = if ($project.version) { [string]$project.version } else { throw "project.json is missing version" }

$distRoot = Join-Path $projectRoot "dist"
$releaseRoot = Join-Path $distRoot "release"
$stageRoot = Join-Path $releaseRoot "stage"

$winName = "$projectName-v$version-win-x64"

Write-Host "Preparing release assets for $projectName v$version..." -ForegroundColor Cyan

# 1. Terminate any running instances of wrapper/settings GUI
Write-Host "Checking for active binary instances..." -ForegroundColor Yellow
$activeProcesses = Get-Process -Name "Au3Check_Wrapper_x64", "au3Mythos_Settings_x64", "Au3Check_Wrapper", "au3Mythos_Settings" -ErrorAction SilentlyContinue
if ($activeProcesses) {
    Write-Host "Terminating active compiler/wrapper processes..." -ForegroundColor Yellow
    $activeProcesses | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# Clean old release directories
if (Test-Path -LiteralPath $releaseRoot) {
    Remove-Item -LiteralPath $releaseRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null
New-Item -ItemType Directory -Path $stageRoot -Force | Out-Null

# Helper to assert file presence and size
function Assert-File {
    param([Parameter(Mandatory = $true)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Required release file missing: $Path"
    }
    $size = (Get-Item -LiteralPath $Path).Length
    if ($size -lt 500) {
        throw "File is invalid or corrupted (size too small): $Path ($size bytes)"
    }
}

# Helper to compile AutoIt scripts
function Compile-AutoIt {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Output,
        [Parameter(Mandatory = $true)][string]$ExpectedPragmaOutput,
        [string]$Icon = ""
    )
    Write-Host "Compiling $Source -> $Output..." -ForegroundColor Yellow
    $aut2exe = "C:\Program Files (x86)\AutoIt3\Aut2Exe\Aut2exe_x64.exe"
    if (-not (Test-Path -LiteralPath $aut2exe)) {
        throw "Aut2Exe compiler not found at $aut2exe"
    }
    
    if (Test-Path -LiteralPath $ExpectedPragmaOutput) {
        Remove-Item -LiteralPath $ExpectedPragmaOutput -Force
    }
    if (Test-Path -LiteralPath $Output) {
        Remove-Item -LiteralPath $Output -Force
    }
    
    $workspace = Split-Path -Parent $projectRoot
    $wrapperExe = Join-Path $workspace "tools_au3\Agent_Run_Wrapper.exe"
    
    $args = @("`"$aut2exe`"", "/in", "`"$Source`"", "/nopack", "/comp", "2", "/x64")
    if ($Icon) {
        $args += @("/icon", "`"$Icon`"")
    }
    
    $proc = Start-Process -FilePath $wrapperExe -ArgumentList $args -PassThru -Wait -NoNewWindow
    if ($proc.ExitCode -ne 0) {
        throw "Failed to compile $Source (ExitCode: $($proc.ExitCode))"
    }
    
    if (-not (Test-Path -LiteralPath $ExpectedPragmaOutput -PathType Leaf)) {
        throw "Expected pragma output file missing after compile: $ExpectedPragmaOutput"
    }
    
    $dir = Split-Path -Parent $Output
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Copy-Item -LiteralPath $ExpectedPragmaOutput -Destination $Output -Force
    Assert-File $Output
}

# 2. Build Python engine using PyInstaller
Write-Host "Compiling Python scoping analyzer engine..." -ForegroundColor Yellow
$pyinstaller = "pyinstaller"
$pyinstallerCmd = Get-Command $pyinstaller -ErrorAction SilentlyContinue
if ($pyinstallerCmd) {
    $pyinstaller = $pyinstallerCmd.Source
} else {
    $pyinstaller = Join-Path $env:USERPROFILE "AppData\Roaming\Python\Python314\Scripts\pyinstaller.exe"
}
if (-not (Test-Path -LiteralPath $pyinstaller)) {
    throw "PyInstaller not found at $pyinstaller"
}

$proc = Start-Process -FilePath $pyinstaller -ArgumentList "--onefile", "--distpath", "bin", "--workpath", "dist\build", "--specpath", "dist", "--name", "autoit_windows_x64_scoping_analyzer", "src\autoit_static_analyzer\autoit_windows_x64_scoping_analyzer.py" -WorkingDirectory $projectRoot -PassThru -Wait -NoNewWindow
if ($proc.ExitCode -ne 0) {
    throw "PyInstaller compilation failed (ExitCode: $($proc.ExitCode))"
}
Assert-File (Join-Path $projectRoot "bin\autoit_windows_x64_scoping_analyzer.exe")

# 3. Compile AutoIt wrappers & installer
$iconPath = Join-Path $projectRoot "resources\mythos_logo.ico"
Compile-AutoIt (Join-Path $projectRoot "tools_wrapper\Au3Check_Wrapper.au3") (Join-Path $projectRoot "bin\Au3Check_Wrapper_x64.exe") (Join-Path $projectRoot "tools_wrapper\Au3Check_Wrapper.exe")
Compile-AutoIt (Join-Path $projectRoot "tools_wrapper\au3Mythos_Settings.au3") (Join-Path $projectRoot "bin\au3Mythos_Settings_x64.exe") (Join-Path $projectRoot "tools_wrapper\au3Mythos_Settings.exe") -Icon $iconPath
Compile-AutoIt (Join-Path $projectRoot "tools_installer\Uninstall_au3Mythos_x64.au3") (Join-Path $projectRoot "bin\Uninstall_au3Mythos_x64.exe") (Join-Path $projectRoot "tools_installer\Uninstall_au3Mythos_x64.exe") -Icon $iconPath
Compile-AutoIt (Join-Path $projectRoot "tools_installer\Setup_au3Mythos_x64.au3") (Join-Path $projectRoot "bin\Setup_au3Mythos_x64.exe") (Join-Path $projectRoot "tools_installer\Setup_au3Mythos_x64.exe") -Icon $iconPath

# 4. Stage files for distribution
$winStage = Join-Path $stageRoot $winName
New-Item -ItemType Directory -Path $winStage -Force | Out-Null

function Copy-FileTo {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if (-not (Test-Path -LiteralPath $Source -PathType Leaf)) {
        throw "Source file missing: $Source"
    }
    $dir = Split-Path -Parent $Destination
    if (-not (Test-Path -LiteralPath $dir)) {
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
}

# Copy binaries
Copy-FileTo (Join-Path $projectRoot "bin\autoit_windows_x64_scoping_analyzer.exe") (Join-Path $winStage "bin\autoit_windows_x64_scoping_analyzer.exe")
Copy-FileTo (Join-Path $projectRoot "bin\Au3Check_Wrapper_x64.exe") (Join-Path $winStage "bin\Au3Check_Wrapper_x64.exe")
Copy-FileTo (Join-Path $projectRoot "bin\au3Mythos_Settings_x64.exe") (Join-Path $winStage "au3Mythos_Settings_x64.exe")
Copy-FileTo (Join-Path $projectRoot "bin\Setup_au3Mythos_x64.exe") (Join-Path $winStage "Setup_au3Mythos_x64.exe")
Copy-FileTo (Join-Path $projectRoot "bin\Uninstall_au3Mythos_x64.exe") (Join-Path $winStage "tools_installer\Uninstall_au3Mythos_x64.exe")

# Copy default config template
Copy-FileTo (Join-Path $projectRoot "resources\mythos_config\config.json") (Join-Path $winStage "mythos_config\config.json")

# Copy resources
if (Test-Path (Join-Path $projectRoot "resources")) {
    Copy-Item -Path (Join-Path $projectRoot "resources") -Destination $winStage -Recurse -Force
}

# Copy public documents
$publicDocs = @("README.md", "LICENSE", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "GOVERNANCE.md")
foreach ($doc in $publicDocs) {
    Copy-FileTo (Join-Path $projectRoot $doc) (Join-Path $winStage $doc)
}

# Copy user manual and screenshots
$stageDocsDir = Join-Path $winStage "docs"
if (-not (Test-Path $stageDocsDir)) {
    New-Item -ItemType Directory -Path $stageDocsDir -Force | Out-Null
}
Copy-Item -Path (Join-Path $projectRoot "docs\au3Mythos_User_Manual.md") -Destination (Join-Path $stageDocsDir "au3Mythos_User_Manual.md") -Force
Copy-Item -Path (Join-Path $projectRoot "docs\screenshots") -Destination $stageDocsDir -Recurse -Force

# Forbidden file verification to prevent leak of private assets
function Assert-NoForbiddenReleaseFiles {
    param([Parameter(Mandatory = $true)][string]$Directory)

    $forbidden = @(
        "\\docs_internal\\",
        "\\scratch\\",
        "\\.agents\\",
        "\\.tmp\\",
        "\\docs\\doxygen\\",
        "\\Logs\\",
        "task\.md$",
        "walkthrough\.md$",
        "implementation_plan\.md$",
        "_safetybackup",
        "\.log$"
    )

    $violations = @()
    Get-ChildItem -LiteralPath $Directory -Recurse -Force | ForEach-Object {
        if (-not $_.PSIsContainer) {
            $rel = $_.FullName.Substring($Directory.Length).TrimStart("\", "/")
            foreach ($pattern in $forbidden) {
                if ($rel -match $pattern) {
                    $violations += $rel
                    break
                }
            }
        }
    }

    if ($violations.Count -gt 0) {
        Write-Host "ERROR: Forbidden files found in release staging directory:" -ForegroundColor Red
        $violations | Sort-Object -Unique | ForEach-Object { Write-Host "  $_" -ForegroundColor Red }
        throw "Release packaging failed forbidden-file validation."
    }
}

Assert-NoForbiddenReleaseFiles $winStage

# 5. Compress to ZIP archive
Write-Host "Creating zip package..." -ForegroundColor Yellow
$zipPath = Join-Path $releaseRoot "$winName.zip"
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $winStage -DestinationPath $zipPath -CompressionLevel Optimal

# 6. Generate Checksums
Write-Host "Generating SHA256 checksums..." -ForegroundColor Yellow
$checksumPath = Join-Path $releaseRoot "SHA256SUMS.txt"
if (Test-Path -LiteralPath $checksumPath) {
    Remove-Item -LiteralPath $checksumPath -Force
}

Get-ChildItem -LiteralPath $releaseRoot -File -Filter "*.zip" | Sort-Object Name | ForEach-Object {
    $hash = Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256
    Add-Content -LiteralPath $checksumPath -Value ("{0}  {1}" -f $hash.Hash.ToLowerInvariant(), $_.Name)
}

# Cleanup staging folder
if (Test-Path -LiteralPath $stageRoot) {
    Remove-Item -LiteralPath $stageRoot -Recurse -Force
}

Write-Host "Release assets created successfully:" -ForegroundColor Green
Get-ChildItem -LiteralPath $releaseRoot -File | Sort-Object Name | ForEach-Object {
    Write-Host ("  {0} ({1:N0} bytes)" -f $_.Name, $_.Length) -ForegroundColor Green
}
