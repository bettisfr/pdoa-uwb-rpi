#!/usr/bin/env python3
"""Export lightly decimated local UAV trajectories from aligned flight logs."""

from __future__ import annotations

import argparse
import csv
import math
from datetime import datetime
from pathlib import Path


def export(source: Path, destination: Path, interval_s: float) -> None:
    """Average local trajectory samples over consecutive time buckets."""
    start: datetime | None = None
    current_bucket: int | None = None
    bucket_points: list[tuple[float, float, float]] = []

    def write_bucket() -> None:
        if not bucket_points:
            return
        count = len(bucket_points)
        mean_x = sum(point[0] for point in bucket_points) / count
        mean_y = sum(point[1] for point in bucket_points) / count
        mean_height = sum(point[2] for point in bucket_points) / count
        writer.writerow((f"{mean_x:.3f}", f"{mean_y:.3f}", f"{mean_height:.3f}"))

    with source.open(newline="") as input_file, destination.open("w", newline="") as output_file:
        writer = csv.writer(output_file)
        writer.writerow(("x_m", "y_m", "height_m"))
        for row in csv.DictReader(input_file):
            try:
                timestamp = datetime.fromisoformat(row["time"])
                point = (
                    timestamp,
                    float(row["gt_x_m"]),
                    float(row["gt_y_m"]),
                    float(row["height_fusion_m"]),
                )
            except (KeyError, TypeError, ValueError):
                continue
            if start is None:
                start = timestamp
            bucket = math.floor((timestamp - start).total_seconds() / interval_s)
            if current_bucket is None:
                current_bucket = bucket
            if bucket != current_bucket:
                write_bucket()
                bucket_points.clear()
                current_bucket = bucket
            bucket_points.append((point[1], point[2], point[3]))
        write_bucket()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path, help="directory with drone_*.csv logs")
    parser.add_argument("output_directory", type=Path, help="directory for exported trajectory CSVs")
    parser.add_argument(
        "--interval-s",
        type=float,
        default=1.0,
        help="averaging interval in seconds (default: 1.0)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    sources = sorted(args.input_directory.glob("drone_*.csv"))
    if not sources:
        raise SystemExit(f"no drone_*.csv logs found in {args.input_directory}")
    if args.interval_s <= 0:
        raise SystemExit("--interval-s must be positive")

    args.output_directory.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(sources, start=1):
        destination = args.output_directory / f"uav-flight-{index}.csv"
        export(source, destination, args.interval_s)
        print(f"Wrote {destination}")


if __name__ == "__main__":
    main()
