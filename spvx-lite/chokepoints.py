"""
Geospatial bounding boxes for chokepoints used in AIS ingestion.

Coordinates defined as [lon_min, lat_min, lon_max, lat_max].
"""

CHOKEPOINTS: dict[str, list[float]] = {
    "singapore_malacca": [95.0, 0.0, 106.0, 6.5],
    "singapore_port": [103.55, 1.05, 104.15, 1.50],
    "suez": [31.0, 26.0, 34.5, 31.5],
    "bosporus": [26.0, 39.0, 30.5, 42.5],
    "hormuz": [54.0, 24.0, 58.5, 28.2],
    "panama_n": [-80.2, 9.3, -79.3, 9.7],
    "panama_s": [-80.0, 8.5, -79.3, 8.9],
    "rotterdam_port": [3.9, 51.9, 4.4, 52.2],
    "antwerp_port": [4.1, 51.1, 4.5, 51.5],
    "west_africa_bonny": [6.5, 3.8, 7.6, 5.0],
    "west_africa_escravos": [4.7, 4.6, 5.8, 6.1],
    "west_africa_gulf": [0.5, 1.8, 8.5, 5.8],
}


def bounding_boxes() -> list[list[list[float]]]:
    """Return bounding boxes formatted for AISStream [[[lat1, lon1], [lat2, lon2]], ...]."""
    boxes: list[list[list[float]]] = []
    for lon_min, lat_min, lon_max, lat_max in CHOKEPOINTS.values():
        boxes.append([[lat_min, lon_min], [lat_max, lon_max]])
    return boxes
