"""
Runtime utilities for logging metadata and timing.
"""

from __future__ import annotations

import subprocess
import json
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter
from typing import Any, Dict

import numpy as np
import pandas as pd
from rich import print as rprint

from spvx.utils.publish import atomic_write_json

def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def make_run_meta(
    *,
    data_hash: int | None = None,
    extra: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Compose a metadata payload with git commit, timestamp, and library versions.
    """
    meta: Dict[str, Any] = {
        "ts": pd.Timestamp.utcnow().isoformat(),
        "git": _git_commit(),
        "versions": {
            "pandas": pd.__version__,
            "numpy": np.__version__,
        },
    }
    if data_hash is not None:
        meta["data_hash"] = int(data_hash)
    if extra:
        meta.update(extra)
    return meta


def update_run_meta(run_name: str, meta: Dict[str, Any], path: str | Path = "data/outputs/run_meta.json") -> Path:
    """
    Update or create the run_meta.json file with the latest run information.
    """
    run_path = Path(path)
    run_path.parent.mkdir(parents=True, exist_ok=True)
    payload: Dict[str, Any] = {}
    if run_path.exists():
        try:
            payload = json.loads(run_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    payload[run_name] = meta
    atomic_write_json(payload, run_path)
    return run_path


@contextmanager
def log_step(label: str):
    """
    Rich-friendly timing context manager.
    """
    rprint(f"[cyan]{label}...[/cyan]")
    start = perf_counter()
    try:
        yield
    finally:
        elapsed = perf_counter() - start
        rprint(f"[green]{label} completed in {elapsed:.2f}s[/green]")
