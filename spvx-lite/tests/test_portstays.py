import datetime as dt

from spvx.sources.portstays import summarise_tanker_activity


def _make_stay(port_name: str, vessel_type: str, atd: str | None, ata: str | None) -> dict:
    payload = {
        "vessel": {"vesselType": vessel_type},
        "port": {"name": port_name},
    }
    if atd:
        payload["atd"] = atd
    if ata:
        payload["ata"] = ata
    return payload


def test_summarise_tanker_activity_counts_departures_and_arrivals():
    stays = [
        _make_stay("Antwerp", "Crude Tanker", "2025-01-10T10:05:00Z", None),
        _make_stay("Antwerp", "Crude Tanker", "2025-01-10T22:15:00Z", "2025-01-08T18:00:00Z"),
        _make_stay("Zeebrugge", "LNG Tanker", None, "2025-01-11T06:30:00Z"),
        _make_stay("Antwerp", "Bulk Carrier", "2025-01-10T09:00:00Z", None),  # ignored (not tanker)
    ]

    summaries = summarise_tanker_activity({"stays": stays})

    assert len(summaries) == 3
    antwerp = next(item for item in summaries if item.port_code == "antwerp" and item.date == dt.date(2025, 1, 10))
    assert antwerp.depart == 2
    assert antwerp.arrive == 0

    antwerp_arrival = next(
        item for item in summaries if item.port_code == "antwerp" and item.date == dt.date(2025, 1, 8)
    )
    assert antwerp_arrival.arrive == 1

    zeebrugge = next(item for item in summaries if item.port_code == "zeebrugge")
    assert zeebrugge.arrive == 1
    assert zeebrugge.depart == 0


def test_summarise_handles_ship_etd_and_stay_start_fields():
    stays = [
        {
            "ship": {"ship_type": "TANKR"},
            "berth_at_arrival": "BEANR01729L0762",
            "stay_start": "2025-01-05T05:30:00Z",
        },
        {
            "ship": {"ship_type": "TANKR"},
            "berth_at_departure": "BEANR01719L0210",
            "etd": "2025-01-05T11:00:00Z",
        },
    ]

    summaries = summarise_tanker_activity(stays)

    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.port_code == "antwerp"
    assert summary.arrive == 1
    assert summary.depart == 1
