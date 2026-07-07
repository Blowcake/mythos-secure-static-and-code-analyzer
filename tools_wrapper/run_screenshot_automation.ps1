Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = (Get-Item (Join-Path $ScriptDir "..")).FullName
Push-Location $ProjectRoot

Write-Host "=== au3Mythos Settings GUI Screenshot Automation ===" -ForegroundColor Cyan

# 1. Kill any active settings GUI processes
Write-Host "Terminating active Settings GUI processes..." -ForegroundColor Yellow
$processes = Get-Process -Name au3Mythos_Settings_x64 -ErrorAction SilentlyContinue
if ($processes) {
    $processes | Stop-Process -Force
    Start-Sleep -Seconds 1
}

# 2. Check if the compiled binary exists
$settingsPath = Join-Path $ProjectRoot "bin\au3Mythos_Settings_x64.exe"
if (-not (Test-Path $settingsPath)) {
    Write-Host "Settings binary missing at $settingsPath. Running build..." -ForegroundColor Yellow
    & .\build.ps1
    if (-not (Test-Path $settingsPath)) {
        Write-Error "Failed to locate compiled settings binary at $settingsPath"
        Pop-Location
        Exit 1
    }
}

# 3. Execute screenshot script
Write-Host "Executing screenshot generation script..." -ForegroundColor Yellow
$autoItExe = "C:\Program Files (x86)\AutoIt3\AutoIt3_x64.exe"
if (-not (Test-Path $autoItExe)) {
    Write-Error "AutoIt3 interpreter not found at $autoItExe"
    Pop-Location
    Exit 1
}

$screenshotScript = Join-Path $ScriptDir "generate_screenshots.au3"
$process = Start-Process -FilePath $autoItExe -ArgumentList "`"$screenshotScript`"" -PassThru -NoNewWindow -Wait

if ($process.ExitCode -ne 0) {
    Write-Error "Screenshot automation failed with exit code $($process.ExitCode)."
    Pop-Location
    Exit 1
}

# 4. Verify output files
$outputDir = Join-Path $ProjectRoot "docs\screenshots"
$expectedScreens = @(
    "win32_settings_splash.png",
    "win32_settings_tab_routing.png",
    "win32_settings_tab_profiles.png",
    "win32_settings_tab_engine.png",
    "win32_settings_about_dialog.png"
)

Write-Host "Verifying generated screenshots in $outputDir..." -ForegroundColor Yellow
$allPassed = $true
$now = Get-Date

foreach ($screen in $expectedScreens) {
    $filePath = Join-Path $outputDir $screen
    if (-not (Test-Path $filePath)) {
        Write-Host "FAIL: Missing screenshot: $screen" -ForegroundColor Red
        $allPassed = $false
    } else {
        $lastWrite = (Get-Item $filePath).LastWriteTime
        $ageSeconds = ($now - $lastWrite).TotalSeconds
        if ($ageSeconds -gt 180) {
            Write-Host "FAIL: Screenshot $screen has old timestamp ($lastWrite)" -ForegroundColor Red
            $allPassed = $false
        } else {
            Write-Host "PASS: Verified $screen (Updated: $lastWrite)" -ForegroundColor Green
        }
    }
}

Pop-Location

if ($allPassed) {
    Write-Host "SUCCESS: All settings GUI screenshots have been updated!" -ForegroundColor Green
    Exit 0
} else {
    Write-Error "Some screenshots failed to verify."
    Exit 1
}
