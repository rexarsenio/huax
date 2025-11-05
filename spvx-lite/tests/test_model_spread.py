from pathlib import Path

import joblib
import pytest


def test_model_artifact_exists_and_scores():
    path = Path("data/outputs/model_spread.pkl")
    if not path.exists():
        pytest.skip("Model artifact missing; run `spvx.cli train` to generate model_spread.pkl.")
    bundle = joblib.load(path)
    model = bundle.get("model")
    assert model is not None
    assert hasattr(model, "predict_proba")
    assert "calibrator" in bundle and bundle["calibrator"] is not None
    cv_metrics = bundle.get("cv_metrics")
    assert isinstance(cv_metrics, dict)
    assert "auc" in cv_metrics
    assert "model_version" in bundle
