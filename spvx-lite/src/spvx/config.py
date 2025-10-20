"""
Configuration utilities driven by environment variables and config.yml.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Runtime settings loaded from .env files."""

    run_mode: str = "mock"
    duckdb_path: str = "db/spvx.duckdb"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="",
        case_sensitive=False,
        extra="allow",
    )


@lru_cache(maxsize=1)
def load_config(path: str | Path = "config.yml") -> Dict[str, Any]:
    """Load YAML configuration once per process."""
    with open(path, "r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)
