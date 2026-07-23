from __future__ import annotations

import sys

import pytest

from asal_m.__main__ import _load_experiment, main


def test_packaged_experiment_loads_by_name() -> None:
    experiment = _load_experiment("alpha_mainline")
    assert experiment["substrate"] == "alpha_alife"
    assert experiment["search_mode"] == "frontier"


def test_unknown_packaged_experiment_fails_clearly() -> None:
    with pytest.raises(FileNotFoundError, match="packaged starter"):
        _load_experiment("not_a_real_experiment")


@pytest.mark.parametrize(
    ("option", "value"),
    [
        ("--budget", "0"),
        ("--budget", "-1"),
        ("--steps", "0"),
        ("--steps", "-1"),
    ],
)
def test_cli_rejects_non_positive_work_limits(
    monkeypatch, option: str, value: str
) -> None:
    monkeypatch.setattr(
        sys,
        "argv",
        ["asal-m", "--experiment", "alpha_mainline", option, value],
    )
    with pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 2
