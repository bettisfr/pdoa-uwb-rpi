#!/usr/bin/env python3
"""Generate time-slider maps for the archived DJI UAV recordings."""

from __future__ import annotations

import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import folium
from folium.plugins import TimestampedGeoJson


EARTH_RADIUS_M = 6_378_137.0
SAMPLE_PERIOD_S = 1.0

# Bearing is measured clockwise from +X; +Y is the O -> Q4 baseline.
TAG_LAYOUT = [
    ("dw00", 15, 28, 0),
    ("dw01", 35, 18, 90),
    ("dw02", 55, 10, 180),
    ("dw03", 75, 24, 270),
    ("dw04", 90, 30, 0),
    ("dw05", 105, 24, 90),
    ("dw06", 125, 10, 180),
    ("dw07", 145, 18, 270),
    ("dw08", 165, 28, 0),
]


@dataclass(frozen=True)
class Point:
    timestamp: datetime
    latitude: float
    longitude: float
    height_m: float | None


def parse_timestamp(value: str, flight_date: date) -> datetime | None:
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return timestamp if timestamp.date() == flight_date else None


def read_points(path: Path) -> list[Point]:
    match = re.search(r"_(\d{4}-\d{2}-\d{2})_", path.name)
    if not match:
        raise ValueError(f"Cannot infer flight date from {path.name}")
    flight_date = date.fromisoformat(match.group(1))
    points: list[Point] = []
    with path.open(newline="") as source:
        for row in csv.DictReader(source):
            timestamp = parse_timestamp(row.get("CUSTOM.dateTime", ""), flight_date)
            try:
                latitude = float(row["OSD.latitude"])
                longitude = float(row["OSD.longitude"])
            except (KeyError, TypeError, ValueError):
                continue
            if timestamp is None or not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                continue
            try:
                height_m = float(row["OSD.height"])
            except (KeyError, TypeError, ValueError):
                height_m = None
            points.append(Point(timestamp, latitude, longitude, height_m))
    return points


def sample_points(points: list[Point]) -> list[Point]:
    sampled: list[Point] = []
    for point in points:
        if not sampled or (point.timestamp - sampled[-1].timestamp).total_seconds() >= SAMPLE_PERIOD_S:
            sampled.append(point)
    if points and sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def local_to_wgs84(reference: dict[str, float], x_m: float, y_m: float) -> tuple[float, float]:
    origin_lat = math.radians(reference["origin_lat_deg"])
    q4_east = math.radians(reference["q4_lon_deg"] - reference["origin_lon_deg"]) * EARTH_RADIUS_M * math.cos(origin_lat)
    q4_north = math.radians(reference["q4_lat_deg"] - reference["origin_lat_deg"]) * EARTH_RADIUS_M
    baseline = math.hypot(q4_east, q4_north)
    if baseline < 0.01:
        raise ValueError("O and Q4 are too close")
    y_east = q4_east / baseline
    y_north = q4_north / baseline
    east_m = x_m * y_north + y_m * y_east
    north_m = -x_m * y_east + y_m * y_north
    latitude = reference["origin_lat_deg"] + math.degrees(north_m / EARTH_RADIUS_M)
    longitude = reference["origin_lon_deg"] + math.degrees(east_m / (EARTH_RADIUS_M * math.cos(origin_lat)))
    return latitude, longitude


def tag_locations(reference: dict[str, float]) -> list[dict[str, float | int | str]]:
    locations = []
    for name, bearing_deg, radius_m, rotation_deg in TAG_LAYOUT:
        bearing_rad = math.radians(bearing_deg)
        x_m = radius_m * math.cos(bearing_rad)
        y_m = radius_m * math.sin(bearing_rad)
        latitude, longitude = local_to_wgs84(reference, x_m, y_m)
        locations.append({
            "name": name,
            "bearing_deg": bearing_deg,
            "radius_m": radius_m,
            "rotation_deg": rotation_deg,
            "x_m": x_m,
            "y_m": y_m,
            "latitude": latitude,
            "longitude": longitude,
        })
    return locations


def popup_html(point: Point) -> str:
    height = "-" if point.height_m is None else f"{point.height_m:.1f} m"
    return (
        f"<b>{point.timestamp.astimezone().isoformat(timespec='seconds')}</b><br>"
        f"Lat/Lon: {point.latitude:.8f}, {point.longitude:.8f}<br>"
        f"Flight height: {height}"
    )


def add_legend(map_object: folium.Map) -> None:
    legend = """
    <div style="position: fixed; bottom: 28px; left: 12px; z-index: 1000;
         background: white; border: 1px solid #9aa4ad; border-radius: 4px;
         padding: 8px 10px; font: 13px system-ui, sans-serif; line-height: 1.45;">
      <b>UAV map</b><br>
      <span style="color:#b22222">&#8212;</span> DJI GPS path<br>
      <span style="color:#138a36">&#9679;</span> Planned UWB tag<br>
      <span style="color:#b22222">&#9679;</span> O local origin<br>
      <span style="color:#165dba">&#9679;</span> Q4 (+Y direction)<br>
      Slider: 1 Hz sampled DJI path
    </div>
    """
    map_object.get_root().html.add_child(folium.Element(legend))


def build_map(csv_path: Path, reference: dict[str, float], output_path: Path) -> None:
    points = read_points(csv_path)
    if len(points) < 2:
        raise ValueError(f"No valid GPS track in {csv_path}")
    sampled = sample_points(points)
    tags = tag_locations(reference)
    center = [sum(point.latitude for point in points) / len(points), sum(point.longitude for point in points) / len(points)]
    map_object = folium.Map(location=center, zoom_start=17, max_zoom=21, control_scale=True, tiles="OpenStreetMap")

    full_track = folium.FeatureGroup(name="Full GPS path", show=False)
    full_track.add_child(folium.PolyLine(
        [(point.latitude, point.longitude) for point in points], color="#777777", weight=2, opacity=0.55,
    ))
    full_track.add_to(map_object)

    time_features = []
    for previous, current in zip(sampled, sampled[1:]):
        time_features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[previous.longitude, previous.latitude], [current.longitude, current.latitude]],
            },
            "properties": {
                "times": [previous.timestamp.isoformat(), current.timestamp.isoformat()],
                "style": {"color": "#b22222", "weight": 4, "opacity": 0.9},
                "popup": popup_html(current),
            },
        })
    TimestampedGeoJson(
        {"type": "FeatureCollection", "features": time_features},
        period="PT1S",
        duration="P1D",
        transition_time=100,
        auto_play=False,
        loop=False,
        add_last_point=False,
        max_speed=10,
        loop_button=True,
        date_options="YYYY-MM-DD HH:mm:ss",
        time_slider_drag_update=True,
    ).add_to(map_object)

    reference_group = folium.FeatureGroup(name="Local reference", show=True)
    folium.CircleMarker(
        (reference["origin_lat_deg"], reference["origin_lon_deg"]), radius=8,
        color="#8b1e1e", fill=True, fill_color="#b22222", fill_opacity=1,
        tooltip="O - local origin",
    ).add_to(reference_group)
    folium.CircleMarker(
        (reference["q4_lat_deg"], reference["q4_lon_deg"]), radius=8,
        color="#124f9e", fill=True, fill_color="#165dba", fill_opacity=1,
        tooltip="Q4 - +Y direction",
    ).add_to(reference_group)
    reference_group.add_to(map_object)

    tag_group = folium.FeatureGroup(name="Planned UWB tag layout", show=True)
    for tag in tags:
        popup = (
            f"<b>{tag['name']}</b><br>"
            f"Bearing: {tag['bearing_deg']} deg<br>"
            f"Radius: {tag['radius_m']} m<br>"
            f"Local: x={tag['x_m']:.3f}, y={tag['y_m']:.3f} m<br>"
            f"Rotation: {tag['rotation_deg']} deg<br>"
            f"GPS: {tag['latitude']:.8f}, {tag['longitude']:.8f}"
        )
        folium.CircleMarker(
            (tag["latitude"], tag["longitude"]), radius=10, color="#075c21",
            weight=2, fill=True, fill_color="#20a548", fill_opacity=1,
            tooltip=folium.Tooltip(str(tag["name"]), permanent=True, direction="top", offset=(0, -8)),
            popup=popup,
        ).add_to(tag_group)
    tag_group.add_to(map_object)

    layout_bounds = [
        (reference["origin_lat_deg"], reference["origin_lon_deg"]),
        (reference["q4_lat_deg"], reference["q4_lon_deg"]),
        *((tag["latitude"], tag["longitude"]) for tag in tags),
    ]
    map_object.fit_bounds(layout_bounds, padding=(12, 12), max_zoom=21)
    folium.LayerControl(collapsed=False).add_to(map_object)
    add_legend(map_object)
    map_object.get_root().html.add_child(folium.Element(
        f"<title>{csv_path.stem} - UAV path</title>"
    ))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    map_object.save(output_path)
    print(f"{csv_path.name}: {len(points)} GPS samples, {len(sampled)} slider samples -> {output_path}")


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data" / "uav-20260903"
    reference = json.loads((data_dir / "reference.json").read_text())
    output_dir = data_dir / "maps"
    for csv_path in sorted((data_dir / "dji-flight-records").glob("*.csv")):
        build_map(csv_path, reference, output_dir / f"{csv_path.stem}.html")


if __name__ == "__main__":
    main()
