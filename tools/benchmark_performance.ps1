<#
.SYNOPSIS
Run reproducible isolated-process performance benchmarks for au3Mythos.

.DESCRIPTION
Records every run plus cumulative, median, min, max, and mean timings. The same
script and workload definitions must be used for the Before and After phases.
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("Before", "After")]
    [string]$Phase,

    [ValidateRange(1, 50)]
    [int]$Iterations = 5,

    [string]$ResultsDir = "docs_internal\false_positives_asprinjunky\performance_results"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$absoluteResultsDir = Join-Path $projectRoot $ResultsDir
New-Item -ItemType Directory -Path $absoluteResultsDir -Force | Out-Null

$env:PYTHONPATH = Join-Path $projectRoot "src"
$pythonVersion = (& python --version 2>&1 | Out-String).Trim()
$analyzerModule = "autoit_static_analyzer"
$ajFile = Join-Path $projectRoot "docs_internal\false_positives_asprinjunky\AspirinJunkie_FalsePositive_Cases_A-J.au3"
$burninFile = Join-Path $projectRoot "tests\all_system_includes.au3"

$workloads = @(
    [pscustomobject]@{
        Name = "AJ_Full_JSON"
        File = $ajFile
        Arguments = @("-d", "-w", "1", "-w", "2", "-w", "3", "-w", "4", "-w", "5", "-w", "6", "-w", "7", "--enable-experimental-checks", "--json-out")
    },
    [pscustomobject]@{
        Name = "Burnin_Standard_JSON"
        File = $burninFile
        Arguments = @("--json-out")
    },
    [pscustomobject]@{
        Name = "Burnin_Experimental_JSON"
        File = $burninFile
        Arguments = @("--enable-experimental-checks", "--json-out")
    },
    [pscustomobject]@{
        Name = "Burnin_Experimental_Report"
        File = $burninFile
        Arguments = @("--enable-experimental-checks")
    }
)

$rows = [System.Collections.Generic.List[object]]::new()
$phaseTempRoot = Join-Path $projectRoot ".tmp\performance_benchmark_$($Phase.ToLowerInvariant())"
New-Item -ItemType Directory -Path $phaseTempRoot -Force | Out-Null

foreach ($workload in $workloads) {
    for ($iteration = 1; $iteration -le $Iterations; $iteration++) {
        $outDir = Join-Path $phaseTempRoot "$($workload.Name)_$iteration"
        New-Item -ItemType Directory -Path $outDir -Force | Out-Null
        $arguments = @("-m", $analyzerModule, $workload.File, "--out-dir", $outDir) + $workload.Arguments

        $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
        & python @arguments *> $null
        $exitCode = $LASTEXITCODE
        $stopwatch.Stop()

        $rows.Add([pscustomobject]@{
            Phase = $Phase
            Workload = $workload.Name
            Iteration = $iteration
            Milliseconds = [Math]::Round($stopwatch.Elapsed.TotalMilliseconds, 3)
            ExitCode = $exitCode
        })
    }
}

$summary = foreach ($group in ($rows | Group-Object Workload)) {
    $values = @($group.Group.Milliseconds | Sort-Object)
    $count = $values.Count
    $median = if ($count % 2 -eq 1) {
        $values[[int][Math]::Floor($count / 2)]
    } else {
        ($values[$count / 2 - 1] + $values[$count / 2]) / 2
    }
    [pscustomobject]@{
        Phase = $Phase
        Workload = $group.Name
        Runs = $count
        TotalMilliseconds = [Math]::Round(($values | Measure-Object -Sum).Sum, 3)
        MedianMilliseconds = [Math]::Round($median, 3)
        MeanMilliseconds = [Math]::Round(($values | Measure-Object -Average).Average, 3)
        MinMilliseconds = [Math]::Round($values[0], 3)
        MaxMilliseconds = [Math]::Round($values[-1], 3)
        ExitCodes = (($group.Group.ExitCode | Sort-Object -Unique) -join ",")
    }
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$baseName = "$($Phase.ToLowerInvariant())_${timestamp}"
$csvPath = Join-Path $absoluteResultsDir "${baseName}_runs.csv"
$jsonPath = Join-Path $absoluteResultsDir "${baseName}_summary.json"
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

$result = [pscustomobject]@{
    Phase = $Phase
    Timestamp = (Get-Date).ToString("o")
    PythonVersion = $pythonVersion
    IterationsPerWorkload = $Iterations
    TotalRuns = $rows.Count
    GrandTotalMilliseconds = [Math]::Round(($rows.Milliseconds | Measure-Object -Sum).Sum, 3)
    Summary = @($summary)
}
$result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $jsonPath -Encoding UTF8

$summary | Format-Table -AutoSize
Write-Host "Grand total: $($result.GrandTotalMilliseconds) ms across $($result.TotalRuns) runs"
Write-Host "Run data: $csvPath"
Write-Host "Summary:  $jsonPath"
