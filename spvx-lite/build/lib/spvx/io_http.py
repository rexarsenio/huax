"""
HTTP helper utilities with simple retry + caching stubs for open-data pulls.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests import Response
from rich import print as rprint


def fetch_json(
    url: str,
    params: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 10,
    retries: int = 3,
    backoff: float = 1.5,
    cache_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Fetch JSON payloads with basic retry handling.

    When `cache_path` is supplied, responses are cached locally to avoid
    re-requesting the same payload during development.
    """
    if cache_path and cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8"))

    attempt = 0
    while True:
        try:
            resp: Response = requests.get(url, params=params, headers=headers, timeout=timeout)
            resp.raise_for_status()
            data = resp.json()
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(json.dumps(data), encoding="utf-8")
            return data
        except requests.RequestException as exc:  # pragma: no cover - network edge cases
            attempt += 1
            if attempt > retries:
                rprint(f"[red][HTTP][/red] failed to fetch {url}: {exc}")
                raise
            sleep_for = backoff**attempt
            rprint(f"[yellow][HTTP][/yellow] retry {attempt} for {url} after {sleep_for:.1f}s due to {exc}")
            time.sleep(sleep_for)
