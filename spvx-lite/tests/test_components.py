import pandas as pd
from pathlib import Path


def test_components_shape():
    path = Path("data/processed/components.parquet")
    assert path.exists(), "components parquet missing; run ingest+compute-index"
    df = pd.read_parquet(path)
    expected_cols = {"date", "CQ_TR", "CQ_SG", "PORT_EU"}
    assert expected_cols.issubset(df.columns)
    assert len(df) >= 365
    assert df.isna().sum().sum() == 0
