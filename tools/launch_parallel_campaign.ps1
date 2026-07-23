param(
    [Parameter(Mandatory = $true)]
    [string]$CampaignName,

    [Parameter(Mandatory = $true)]
    [string[]]$Experiments,

    [switch]$IncludeLocalPaths,

    [ValidateRange(0, 300)]
    [int]$StartupProbeSeconds = 8
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($CampaignName -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$') {
    throw "CampaignName must be 1-64 characters using letters, numbers, dot, underscore, or hyphen."
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $repoRoot "venv\Scripts\python.exe"
}
if (-not (Test-Path $pythonExe)) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($null -ne $cmd) {
        $pythonExe = $cmd.Source
    }
}
if (-not (Test-Path $pythonExe)) {
    throw "Python executable not found. Create .venv or ensure python is on PATH."
}

function ConvertTo-PublicPath {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PathValue
    )

    $fullPath = [IO.Path]::GetFullPath($PathValue)
    if ($IncludeLocalPaths) {
        return $fullPath
    }

    $basePath = [IO.Path]::GetFullPath($repoRoot).TrimEnd("\", "/")
    $prefix = $basePath + [IO.Path]::DirectorySeparatorChar
    if ($fullPath.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        return $fullPath.Substring($prefix.Length).Replace("\", "/")
    }
    if ($fullPath.Equals($basePath, [StringComparison]::OrdinalIgnoreCase)) {
        return "."
    }

    $leaf = [IO.Path]::GetFileName($fullPath.TrimEnd("\", "/"))
    if ([string]::IsNullOrWhiteSpace($leaf)) {
        return "external_path"
    }
    return $leaf
}

$campaignRoot = Join-Path $repoRoot ("runs\campaigns\" + $CampaignName)
$logsRoot = Join-Path $campaignRoot "logs"
New-Item -ItemType Directory -Force -Path $campaignRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

function Get-ExperimentMeta {
    param(
        [string]$SpecPath
    )

    $resolved = Resolve-Path -LiteralPath $SpecPath
    if (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue) {
        $raw = Get-Content -LiteralPath $resolved -Raw
        $data = $raw | ConvertFrom-Yaml
        return [pscustomobject]@{
            SpecPath = $resolved.Path
            Name = [string]$data.name
            ArtifactRoot = [string]$data.artifact_root
        }
    }

    $json = & $pythonExe -c "import json, sys, yaml; data = yaml.safe_load(open(sys.argv[1], encoding='utf-8')); print(json.dumps({'name': data.get('name'), 'artifact_root': data.get('artifact_root', 'runs')}))" $resolved.Path
    $data = $json | ConvertFrom-Json
    return [pscustomobject]@{
        SpecPath = $resolved.Path
        Name = [string]$data.name
        ArtifactRoot = [string]$data.artifact_root
    }
}

$startedAt = [DateTimeOffset]::UtcNow
$manifest = [ordered]@{
    campaign_name = $CampaignName
    repo_root = ConvertTo-PublicPath -PathValue $repoRoot
    launched_at = $startedAt.ToString("yyyy-MM-ddTHH:mm:ssZ")
    local_paths_included = [bool]$IncludeLocalPaths
    experiments = @()
}
$runtimeEntries = @()

foreach ($experiment in $Experiments) {
    $meta = Get-ExperimentMeta -SpecPath $experiment
    $slug = [IO.Path]::GetFileNameWithoutExtension($meta.SpecPath)
    $stdoutPath = Join-Path $logsRoot ($slug + ".stdout.log")
    $stderrPath = Join-Path $logsRoot ($slug + ".stderr.log")
    $artifactRoot = $meta.ArtifactRoot
    if (-not [IO.Path]::IsPathRooted($artifactRoot)) {
        $artifactRoot = Join-Path $repoRoot $artifactRoot
    }
    $runDir = Join-Path $artifactRoot $meta.Name
    $arguments = @(
        "-m",
        "asal_m",
        "--experiment",
        ('"{0}"' -f $meta.SpecPath)
    )

    $process = Start-Process `
        -FilePath $pythonExe `
        -ArgumentList $arguments `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $stdoutPath `
        -RedirectStandardError $stderrPath `
        -WindowStyle Hidden `
        -PassThru

    $publicArguments = @(
        "-m",
        "asal_m",
        "--experiment",
        (ConvertTo-PublicPath -PathValue $meta.SpecPath)
    )
    $publicEntry = [ordered]@{
        spec_path = ConvertTo-PublicPath -PathValue $meta.SpecPath
        experiment_name = $meta.Name
        run_dir = ConvertTo-PublicPath -PathValue $runDir
        stdout_log = ConvertTo-PublicPath -PathValue $stdoutPath
        stderr_log = ConvertTo-PublicPath -PathValue $stderrPath
        command = @((ConvertTo-PublicPath -PathValue $pythonExe)) + $publicArguments
        pid = $process.Id
        launched_at = [DateTimeOffset]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
    }
    $manifest.experiments += $publicEntry
    $runtimeEntries += [pscustomobject]@{
        ProcessId = $process.Id
        RunDir = $runDir
        ManifestEntry = $publicEntry
    }
}

if ($StartupProbeSeconds -gt 0) {
    Start-Sleep -Seconds $StartupProbeSeconds
}

foreach ($runtime in $runtimeEntries) {
    $entry = $runtime.ManifestEntry
    $process = Get-Process -Id $runtime.ProcessId -ErrorAction SilentlyContinue
    $entry["startup_running"] = [bool]$process
    $entry["run_dir_exists"] = Test-Path -LiteralPath $runtime.RunDir
    if (Test-Path -LiteralPath $runtime.RunDir) {
        $recentFiles = Get-ChildItem -LiteralPath $runtime.RunDir -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 5
        $entry["recent_files"] = @(
            $recentFiles | ForEach-Object {
                ConvertTo-PublicPath -PathValue $_.FullName
            }
        )
    } else {
        $entry["recent_files"] = @()
    }
}

$manifestPath = Join-Path $campaignRoot "campaign_manifest.json"
$manifest | ConvertTo-Json -Depth 8 | Set-Content -Path $manifestPath -Encoding utf8

$readmePath = Join-Path $campaignRoot "README.md"
$lines = @(
    "# $CampaignName",
    "",
    "- Launched at: ``$($manifest.launched_at)``",
    "- Repo root: ``$($manifest.repo_root)``",
    "- Manifest: ``$(ConvertTo-PublicPath -PathValue $manifestPath)``",
    "- Local paths included: ``$($manifest.local_paths_included)``",
    "",
    "## Resume Rule",
    "",
    "A run is complete only when ``experiment_summary.json`` exists under its run directory.",
    "If a summary is missing after an interruption, inspect the emitted candidate folders and the launch logs recorded here before deciding whether to resume, mine, or invalidate the lane.",
    "",
    "## Experiments"
)

foreach ($entry in $manifest.experiments) {
    $lines += ""
    $lines += "### $($entry.experiment_name)"
    $lines += ""
    $lines += "- Spec: ``$($entry.spec_path)``"
    $lines += "- Run dir: ``$($entry.run_dir)``"
    $lines += "- PID: ``$($entry.pid)``"
    $lines += "- Stdout: ``$($entry.stdout_log)``"
    $lines += "- Stderr: ``$($entry.stderr_log)``"
    $lines += "- Startup running: ``$($entry.startup_running)``"
    $lines += "- Run dir exists: ``$($entry.run_dir_exists)``"
}

Set-Content -Path $readmePath -Value $lines -Encoding utf8

Write-Output "Campaign root: $campaignRoot"
Write-Output "Manifest: $manifestPath"
$manifest.experiments | ForEach-Object {
    Write-Output ("{0}`tPID={1}`tRunning={2}`tRunDir={3}" -f $_.experiment_name, $_.pid, $_.startup_running, $_.run_dir)
}
