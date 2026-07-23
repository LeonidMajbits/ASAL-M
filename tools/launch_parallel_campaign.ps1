param(
    [Parameter(Mandatory = $true)]
    [string]$CampaignName,

    [Parameter(Mandatory = $true)]
    [string[]]$Experiments
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

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

$campaignRoot = Join-Path $repoRoot ("runs\campaigns\" + $CampaignName)
$logsRoot = Join-Path $campaignRoot "logs"
New-Item -ItemType Directory -Force -Path $campaignRoot | Out-Null
New-Item -ItemType Directory -Force -Path $logsRoot | Out-Null

function Get-ExperimentMeta {
    param(
        [string]$SpecPath
    )

    $resolved = Resolve-Path $SpecPath
    if (Get-Command ConvertFrom-Yaml -ErrorAction SilentlyContinue) {
        $raw = Get-Content -Path $resolved -Raw
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

$startedAt = Get-Date
$manifest = [ordered]@{
    campaign_name = $CampaignName
    repo_root = $repoRoot
    launched_at = $startedAt.ToString("o")
    experiments = @()
}

foreach ($experiment in $Experiments) {
    $meta = Get-ExperimentMeta -SpecPath $experiment
    $slug = [IO.Path]::GetFileNameWithoutExtension($meta.SpecPath)
    $stdoutPath = Join-Path $logsRoot ($slug + ".stdout.log")
    $stderrPath = Join-Path $logsRoot ($slug + ".stderr.log")
    $runDir = Join-Path $repoRoot (Join-Path $meta.ArtifactRoot $meta.Name)
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
        -PassThru

    $manifest.experiments += [ordered]@{
        spec_path = $meta.SpecPath
        experiment_name = $meta.Name
        run_dir = $runDir
        stdout_log = $stdoutPath
        stderr_log = $stderrPath
        command = @($pythonExe) + $arguments
        pid = $process.Id
        launched_at = (Get-Date).ToString("o")
    }
}

Start-Sleep -Seconds 8

foreach ($entry in $manifest.experiments) {
    $process = Get-Process -Id $entry.pid -ErrorAction SilentlyContinue
    $entry["startup_running"] = [bool]$process
    $entry["run_dir_exists"] = Test-Path $entry.run_dir
    if (Test-Path $entry.run_dir) {
        $recentFiles = Get-ChildItem -Path $entry.run_dir -Recurse -File -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            Select-Object -First 5 -ExpandProperty FullName
        $entry["recent_files"] = @($recentFiles)
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
    "- Repo root: ``$repoRoot``",
    "- Manifest: ``$manifestPath``",
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
