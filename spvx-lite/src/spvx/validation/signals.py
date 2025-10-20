"""
JSON Schema validation for published signal payloads.
"""

from __future__ import annotations

from jsonschema import Draft202012Validator


SIGNALS_SCHEMA = {
    "type": "object",
    "required": ["asof", "spvx_lite", "spvx_lite_chg"],
    "properties": {
        "asof": {"type": "string", "format": "date-time"},
        "spvx_lite": {"type": "number"},
        "spvx_lite_chg": {"type": "number"},
        "drivers": {
            "type": "object",
            "properties": {
                "CQ_TR": {"type": "number"},
                "CQ_SG": {"type": "number"},
                "PORT_EU": {"type": "number"},
            },
            "required": ["CQ_TR", "CQ_SG", "PORT_EU"],
            "additionalProperties": False,
        },
        "spread_direction": {
            "type": ["object", "null"],
            "properties": {
                "t+1_prob_up": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                "top_decile": {"type": "boolean"},
            },
            "required": ["t+1_prob_up", "top_decile"],
            "additionalProperties": False,
        },
        "spread": {
            "type": "object",
            "properties": {
                "model_ver": {"type": ["string", "null"]},
                "metrics": {"type": ["object", "null"]},
                "drift": {"type": ["object", "null"]},
                "degraded": {"type": "boolean"},
                "mode": {"type": ["string", "null"]},
                "prob_up": {"type": ["number", "null"], "minimum": 0.0, "maximum": 1.0},
                "prob_up_raw": {"type": ["number", "null"]},
                "prob_up_calibrated": {"type": ["number", "null"]},
                "drivers": {"type": ["object", "null"]},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "top_decile_threshold": {"type": ["number", "null"]},
                "recent_window_days": {"type": ["number", "null"]},
                "calibration_curve": {"type": ["array", "null"]},
            },
            "required": ["degraded", "mode"],
            "additionalProperties": True,
        },
        "throughput_72h": {
            "type": "object",
            "properties": {
                "mae_units": {"type": ["number", "null"]},
                "nowcast": {
                    "type": "object",
                    "patternProperties": {
                        "^[0-9]{4}-[0-9]{2}-[0-9]{2}$": {"type": "number"},
                    },
                    "additionalProperties": False,
                    "minProperties": 1,
                },
            },
            "required": ["mae_units", "nowcast"],
            "additionalProperties": False,
        },
        "annotations": {"type": "array", "items": {"type": "string"}},
        "degraded": {"type": "boolean"},
    },
    "additionalProperties": False,
}

validator = Draft202012Validator(SIGNALS_SCHEMA)


def validate_signals(payload: dict) -> None:
    """
    Raise an exception if payload does not conform to the signals schema.
    """
    validator.validate(payload)
