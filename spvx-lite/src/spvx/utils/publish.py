"""
Utility helpers for atomic publishing of artifacts.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Iterable, Mapping, Sequence


def atomic_write_json(payload: Mapping[str, object], path: str | os.PathLike[str]) -> None:
    """
    Serialize a JSON payload to disk atomically to avoid partial writes.
    """
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp_path, target)


def atomic_write_csv(
    rows: Iterable[Mapping[str, object]],
    headers: Sequence[str],
    path: str | os.PathLike[str],
) -> None:
    """
    Write CSV rows with a header atomically.
    """
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    with tmp_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(headers))
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    os.replace(tmp_path, target)


def atomic_write_bytes(data: bytes | bytearray, path: str | os.PathLike[str]) -> None:
    """
    Atomically write raw bytes to disk.
    """
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_bytes(bytes(data))
    os.replace(tmp_path, target)


def atomic_write_text(text: str, path: str | os.PathLike[str], encoding: str = "utf-8") -> None:
    """
    Atomically write text content to disk.
    """
    target = Path(path)
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    tmp_path.write_text(text, encoding=encoding)
    os.replace(tmp_path, target)
