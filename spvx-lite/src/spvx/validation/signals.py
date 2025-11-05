"""
JSON Schema validation for published signal payloads.
"""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).with_name("signals_schema.json")
SIGNALS_SCHEMA = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

validator = Draft202012Validator(SIGNALS_SCHEMA)


def validate_signals(payload: dict) -> None:
    """
    Raise an exception if payload does not conform to the signals schema.
    """
    validator.validate(payload)
