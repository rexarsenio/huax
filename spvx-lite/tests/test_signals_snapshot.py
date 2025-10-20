import json
from pathlib import Path

from spvx.validation.signals import validate_signals


def test_signals_snapshot_contains_spread_block():
    path = Path("data/outputs/signals.json")
    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_signals(payload)

    assert "spread" in payload
    spread = payload["spread"]
    assert isinstance(spread, dict)
    assert "degraded" in spread
    assert "mode" in spread
    assert "prob_up" in spread
