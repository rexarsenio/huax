from __future__ import annotations

from spvx.ingest.canonicalize import canonicalize


def _base_payload(**overrides):
    payload = {
        "MMSI": 123456789,
        "MetaData": {"receivedTimestamp": 1_700_000_000_000},
        "Message": {
            "PositionReport": {
                "Latitude": 1.2345,
                "Longitude": 103.9876,
                "Sog": 12.3,
                "Cog": 45.0,
            }
        },
    }
    payload.update(overrides)
    return payload


def test_tanker_classification():
    payload = _base_payload(
        Message={"PositionReport": {"Latitude": 1.0, "Longitude": 103.0, "Sog": 5.0, "Cog": 10.0, "ShipType": 82}}
    )
    canon = canonicalize(payload)
    assert canon is not None
    assert canon["is_tanker"] is True

    payload_non = _base_payload(
        Message={"PositionReport": {"Latitude": 1.0, "Longitude": 103.0, "Sog": 10.0, "Cog": 90.0}},
        MetaData={"receivedTimestamp": 1_700_000_100_000, "shipType": "General Cargo"},
    )
    canon_non = canonicalize(payload_non)
    assert canon_non is not None
    assert canon_non["is_tanker"] is False


def test_invalid_positions_filtered():
    bad_lat = _base_payload(Message={"PositionReport": {"Latitude": 95.0, "Longitude": 103.0, "Sog": 5.0}})
    assert canonicalize(bad_lat) is None

    bad_speed = _base_payload(Message={"PositionReport": {"Latitude": 1.0, "Longitude": 103.0, "Sog": 55.0}})
    assert canonicalize(bad_speed) is None
