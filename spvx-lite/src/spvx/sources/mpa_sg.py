"""
Placeholder for Maritime Port Authority of Singapore open-data ingestion.

The endpoints typically require a free API key. This module documents the
expected table layout so swapping in real fetch logic is straightforward.
"""

from __future__ import annotations


def run(*, days: int = 400) -> None:
    raise NotImplementedError(
        "Live MPA ingestion not implemented in the open build. "
        "Use the mock source or extend with authenticated requests."
    )
