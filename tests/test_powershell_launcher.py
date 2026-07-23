from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest
import yaml


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell launcher")
def test_powershell_campaign_manifest_is_path_safe(
    tmp_path: Path,
) -> None:
    repository = Path(__file__).resolve().parents[1]
    shell = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    if shell is None:
        pytest.skip("PowerShell is unavailable")

    campaign_name = f"test-{uuid.uuid4().hex[:12]}"
    campaign_root = repository / "runs" / "campaigns" / campaign_name
    artifact_root = tmp_path / "private-artifacts"
    spec_path = tmp_path / "private-spec.yaml"
    spec = yaml.safe_load(
        (repository / "asal_m" / "experiments" / "alpha_mainline.yaml").read_text(
            encoding="utf-8"
        )
    )
    spec["name"] = "launcher_smoke"
    spec["budget"] = 1
    spec["steps"] = 4
    spec["artifact_root"] = str(artifact_root)
    spec["validation"] = {
        "interval": 0,
        "score_threshold": 999.0,
        "perturbations": [],
    }
    spec_path.write_text(yaml.safe_dump(spec, sort_keys=False), encoding="utf-8")

    command = [
        shell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(repository / "tools" / "launch_parallel_campaign.ps1"),
        "-CampaignName",
        campaign_name,
        "-Experiments",
        str(spec_path),
        "-StartupProbeSeconds",
        "1",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert completed.returncode == 0, completed.stderr

        summary_path = artifact_root / "launcher_smoke" / "experiment_summary.json"
        deadline = time.monotonic() + 20
        while not summary_path.exists() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert summary_path.is_file()

        manifest_text = (campaign_root / "campaign_manifest.json").read_text(
            encoding="utf-8-sig"
        )
        readme_text = (campaign_root / "README.md").read_text(encoding="utf-8-sig")
        manifest = json.loads(manifest_text)
        combined = manifest_text + readme_text

        assert manifest["repo_root"] == "."
        assert manifest["local_paths_included"] is False
        assert manifest["experiments"][0]["spec_path"] == "private-spec.yaml"
        assert str(repository) not in combined
        assert str(tmp_path) not in combined
        assert ":\\" not in combined
    finally:
        shutil.rmtree(campaign_root, ignore_errors=True)
        campaigns_root = campaign_root.parent
        if campaigns_root.is_dir() and not any(campaigns_root.iterdir()):
            campaigns_root.rmdir()
        runs_root = campaigns_root.parent
        if runs_root.is_dir() and not any(runs_root.iterdir()):
            runs_root.rmdir()
