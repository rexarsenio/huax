"""Canonical corridor definitions for gate-based transit calculations."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Tuple


@dataclass(frozen=True)
class CorridorDefinition:
    corridor_id: str
    entry_gates: Tuple[str, ...]
    exit_gates: Tuple[str, ...]
    min_hours: float
    max_hours: float

    def all_gates(self) -> Tuple[str, ...]:
        return self.entry_gates + self.exit_gates


_CORRIDOR_DEFINITIONS: Tuple[CorridorDefinition, ...] = (
    CorridorDefinition(
        corridor_id="SUEZ_SOUTHBOUND",
        entry_gates=("GATE_SUEZ_N_25NM", "GATE_SUEZ_N_10NM"),
        exit_gates=("GATE_SUEZ_S_25NM", "GATE_SUEZ_S_10NM"),
        min_hours=2.0,
        max_hours=48.0,
    ),
    CorridorDefinition(
        corridor_id="SUEZ_NORTHBOUND",
        entry_gates=("GATE_SUEZ_S_25NM", "GATE_SUEZ_S_10NM"),
        exit_gates=("GATE_SUEZ_N_25NM", "GATE_SUEZ_N_10NM"),
        min_hours=2.0,
        max_hours=48.0,
    ),
    CorridorDefinition(
        corridor_id="HORMUZ_EASTBOUND",
        entry_gates=("GATE_HORMUZ_GULF_100NM", "GATE_HORMUZ_GULF_50NM"),
        exit_gates=("GATE_HORMUZ_OMAN_100NM", "GATE_HORMUZ_OMAN_50NM"),
        min_hours=1.0,
        max_hours=36.0,
    ),
    CorridorDefinition(
        corridor_id="HORMUZ_WESTBOUND",
        entry_gates=("GATE_HORMUZ_OMAN_100NM", "GATE_HORMUZ_OMAN_50NM"),
        exit_gates=("GATE_HORMUZ_GULF_100NM", "GATE_HORMUZ_GULF_50NM"),
        min_hours=1.0,
        max_hours=36.0,
    ),
    CorridorDefinition(
        corridor_id="BAB_EL_MANDEB_NORTHBOUND",
        entry_gates=("GATE_BABELMANDEB_ADEN_50NM", "GATE_BABELMANDEB_ADEN_25NM"),
        exit_gates=("GATE_BABELMANDEB_RED_SEA_50NM", "GATE_BABELMANDEB_RED_SEA_25NM"),
        min_hours=0.5,
        max_hours=24.0,
    ),
    CorridorDefinition(
        corridor_id="BAB_EL_MANDEB_SOUTHBOUND",
        entry_gates=("GATE_BABELMANDEB_RED_SEA_50NM", "GATE_BABELMANDEB_RED_SEA_25NM"),
        exit_gates=("GATE_BABELMANDEB_ADEN_50NM", "GATE_BABELMANDEB_ADEN_25NM"),
        min_hours=0.5,
        max_hours=24.0,
    ),
    CorridorDefinition(
        corridor_id="GIBRALTAR_EASTBOUND",
        entry_gates=("GATE_GIBRALTAR_ATLANTIC_50NM", "GATE_GIBRALTAR_ATLANTIC_100NM"),
        exit_gates=("GATE_GIBRALTAR_MED_50NM", "GATE_GIBRALTAR_MED_100NM"),
        min_hours=0.5,
        max_hours=18.0,
    ),
    CorridorDefinition(
        corridor_id="GIBRALTAR_WESTBOUND",
        entry_gates=("GATE_GIBRALTAR_MED_50NM", "GATE_GIBRALTAR_MED_100NM"),
        exit_gates=("GATE_GIBRALTAR_ATLANTIC_50NM", "GATE_GIBRALTAR_ATLANTIC_100NM"),
        min_hours=0.5,
        max_hours=18.0,
    ),
    CorridorDefinition(
        corridor_id="BOSPORUS_SOUTHBOUND",
        entry_gates=("GATE_BOSPORUS_N_25NM", "GATE_BOSPORUS_N_10NM"),
        exit_gates=("GATE_BOSPORUS_S_25NM", "GATE_BOSPORUS_S_10NM"),
        min_hours=0.5,
        max_hours=24.0,
    ),
    CorridorDefinition(
        corridor_id="BOSPORUS_NORTHBOUND",
        entry_gates=("GATE_BOSPORUS_S_25NM", "GATE_BOSPORUS_S_10NM"),
        exit_gates=("GATE_BOSPORUS_N_25NM", "GATE_BOSPORUS_N_10NM"),
        min_hours=0.5,
        max_hours=24.0,
    ),
    CorridorDefinition(
        corridor_id="YUCATAN_SOUTHBOUND",
        entry_gates=("GATE_YUCATAN_N_25NM", "GATE_YUCATAN_N_10NM"),
        exit_gates=("GATE_YUCATAN_S_25NM", "GATE_YUCATAN_S_10NM"),
        min_hours=4.0,
        max_hours=60.0,
    ),
    CorridorDefinition(
        corridor_id="YUCATAN_NORTHBOUND",
        entry_gates=("GATE_YUCATAN_S_25NM", "GATE_YUCATAN_S_10NM"),
        exit_gates=("GATE_YUCATAN_N_25NM", "GATE_YUCATAN_N_10NM"),
        min_hours=4.0,
        max_hours=60.0,
    ),
)


@lru_cache(maxsize=1)
def corridor_index() -> dict[str, CorridorDefinition]:
    return {definition.corridor_id: definition for definition in _CORRIDOR_DEFINITIONS}


def corridors() -> Tuple[CorridorDefinition, ...]:
    return _CORRIDOR_DEFINITIONS


def corridor_ids() -> Tuple[str, ...]:
    return tuple(definition.corridor_id for definition in _CORRIDOR_DEFINITIONS)


def iter_corridors() -> Iterable[CorridorDefinition]:
    return _CORRIDOR_DEFINITIONS

