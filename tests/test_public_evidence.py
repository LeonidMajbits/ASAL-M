from __future__ import annotations

import ast
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from asal_m.evidence import (
    PUBLIC_FLOAT_DECIMAL_PLACES,
    canonical_public_json,
    canonicalize_public_payload,
)
from examples.certification_benchmark.regenerate import FONT_FILES, _font, _sha256

ROOT = Path(__file__).resolve().parents[1]
CERTIFICATION_BENCHMARK = (
    ROOT / "examples" / "certification_benchmark" / "benchmark.json"
)
VERIFIER = ROOT / "tools" / "verify_public_evidence.py"


def test_canonical_public_json_normalizes_only_published_floats() -> None:
    payload = {
        "whole": 4,
        "nested": [0.12345678901244, -0.0000000000004],
        "truth": True,
    }
    normalized = canonicalize_public_payload(payload)
    assert normalized == {
        "whole": 4,
        "nested": [0.123456789012, 0.0],
        "truth": True,
    }
    assert canonical_public_json(payload).endswith("\n")
    assert json.loads(canonical_public_json(payload)) == normalized


@pytest.mark.parametrize("value", [math.inf, -math.inf, math.nan])
def test_canonical_public_json_rejects_non_finite_values(value: float) -> None:
    with pytest.raises(ValueError, match="NaN or infinity"):
        canonical_public_json({"value": value})


def test_release_fonts_are_repository_bound_and_checksum_verified() -> None:
    assert PUBLIC_FLOAT_DECIMAL_PLACES == 12
    for bold, (path, expected_sha256) in FONT_FILES.items():
        assert path.is_relative_to(ROOT)
        assert _sha256(path) == expected_sha256
        assert _font(18, bold=bold).size == 18


def test_public_evidence_verifier_contains_no_assert_statement() -> None:
    tree = ast.parse(VERIFIER.read_text(encoding="utf-8"))
    assert not [node for node in ast.walk(tree) if isinstance(node, ast.Assert)]


def test_optimized_python_rejects_tampered_evidence(tmp_path: Path) -> None:
    payload = json.loads(CERTIFICATION_BENCHMARK.read_text(encoding="utf-8"))
    payload["comparison"]["absolute_audit_gain"] += 9.0
    tampered = tmp_path / "benchmark.json"
    tampered.write_text(canonical_public_json(payload), encoding="utf-8", newline="\n")

    code = (
        "import json\n"
        "from pathlib import Path\n"
        "from tools.verify_public_evidence import verify\n"
        f"payload = json.loads(Path({str(tampered)!r}).read_text(encoding='utf-8'))\n"
        "verify(payload)\n"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "absolute audit gain is inconsistent" in result.stderr


def test_optimized_python_path_gate_rejects_tampered_evidence(tmp_path: Path) -> None:
    payload = json.loads(CERTIFICATION_BENCHMARK.read_text(encoding="utf-8"))
    payload["comparison"]["absolute_audit_gain"] += 9.0
    tampered = tmp_path / "benchmark.json"
    tampered.write_text(canonical_public_json(payload), encoding="utf-8", newline="\n")

    code = (
        "from pathlib import Path\n"
        "from tools.verify_public_evidence import verify_paths\n"
        f"verify_paths(benchmark=Path({str(tampered)!r}))\n"
    )
    result = subprocess.run(
        [sys.executable, "-O", "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode != 0
    assert "Release artifact checksum mismatch" in result.stderr
