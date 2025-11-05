import json
from pathlib import Path

import pytest

from spvx.validation.signals import validate_signals


@pytest.mark.skipif(
    not Path("data/outputs/signals.json").exists(),
    reason="signals.json missing; run `spvx.cli score` to generate snapshot.",
)
def test_signals_snapshot_contains_spread_block():
    path = Path("data/outputs/signals.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_signals(payload)

    assert "spread" in payload
    spread = payload["spread"]
    assert isinstance(spread, dict)
    assert "degraded" in spread
    assert "mode" in spread
    assert "prob_up" in spread
    drivers = spread.get("drivers")
    assert isinstance(drivers, dict)
    assert "sea_state" in drivers
    sea_state = drivers["sea_state"]
    assert isinstance(sea_state, dict)
    assert "hs_z" in sea_state
    assert "as_of" in sea_state
