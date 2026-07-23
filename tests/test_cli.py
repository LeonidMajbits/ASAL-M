from __future__ import annotations

import pytest

from asal_m.__main__ import _load_experiment


def test_packaged_experiment_loads_by_name() -> None:
    experiment = _load_experiment("alpha_mainline")
    assert experiment["substrate"] == "alpha_alife"
    assert experiment["search_mode"] == "frontier"


def test_unknown_packaged_experiment_fails_clearly() -> None:
    with pytest.raises(FileNotFoundError, match="packaged starter"):
        _load_experiment("not_a_real_experiment")
