#!/usr/bin/env python3
"""Entry point for the PDoA measurement-analysis workflow.

The static coplanar, static non-coplanar, and UAV campaigns will be normalized
into one analysis table.  In that table, the node--tag height difference is a
feature (``height_difference_m``), not a dataset-specific special case.  This
allows the same descriptive statistics and future models to be evaluated across
all campaigns, while retaining the campaign identifier for grouped analyses.
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from statistics import fmean, pstdev


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DATA_DIRECTORY = REPOSITORY_ROOT / "data"
CSV_DIRECTORY = REPOSITORY_ROOT / "analysis" / "csv"
PLOTS_DIRECTORY = REPOSITORY_ROOT / "analysis" / "plots"


def discover_static_campaigns() -> list[Path]:
    """Return static datasets, including coplanar and elevated-node runs."""
    return sorted(DATA_DIRECTORY.glob("ground-height-*/experiment.json"))


def discover_uav_campaigns() -> list[Path]:
    """Return UAV campaign reference files."""
    return sorted(DATA_DIRECTORY.glob("uav-*/reference.json"))


def wrap_degrees(angle_deg: float) -> float:
    """Return the equivalent angle in the interval [-180, 180)."""
    return (angle_deg + 180.0) % 360.0 - 180.0


def build_static_dataset() -> Path:
    """Normalize the three static campaigns into one per-measurement CSV.

    The reported range is a three-dimensional propagation range.  The output
    therefore retains its error against the three-dimensional ground truth and
    also derives the ground distance through
    ``sqrt(reported_range_m**2 - height_difference_m**2)``.
    """
    CSV_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = CSV_DIRECTORY / "static_measurements.csv"
    fieldnames = [
        "experiment_id",
        "run_file",
        "time",
        "tag",
        "height_difference_m",
        "target_ground_distance_m",
        "tag_rotation_deg",
        "gt_bearing_deg",
        "gt_x_m",
        "gt_y_m",
        "gt_range_3d_m",
        "range_m",
        "range_error_3d_m",
        "estimated_ground_distance_m",
        "ground_distance_error_m",
        "pdoa_deg",
        "eta_expected_deg",
        "eta_residual_deg",
        "estimated_bearing_deg",
        "bearing_error_deg",
        "x_m",
        "y_m",
        "position_error_m",
        "clk_ppm",
        "sequence",
    ]

    row_count = 0
    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()

        for experiment_path in discover_static_campaigns():
            for run_path in sorted((experiment_path.parent / "runs").glob("*.csv")):
                with run_path.open(newline="") as input_file:
                    for source in csv.DictReader(input_file):
                        if source["valid_position"] != "1":
                            continue

                        height_m = float(source["node_height_m"])
                        ground_distance_m = float(source["target_distance_m"])
                        bearing_deg = float(source["tag_bearing_deg"])
                        bearing_rad = math.radians(bearing_deg)
                        gt_x_m = ground_distance_m * math.cos(bearing_rad)
                        gt_y_m = ground_distance_m * math.sin(bearing_rad)
                        gt_range_3d_m = math.hypot(ground_distance_m, height_m)

                        range_m = float(source["range_cm"]) / 100.0
                        x_m = float(source["x_cm"]) / 100.0
                        y_m = float(source["y_cm"]) / 100.0
                        estimated_bearing_deg = math.degrees(math.atan2(y_m, x_m))

                        # With the nominal t=lambda/2 array, the far-field
                        # phase is -180 degrees times the baseline component
                        # of the 3D unit direction vector.
                        eta_expected_deg = -180.0 * gt_x_m / gt_range_3d_m
                        pdoa_deg = float(source["pdoa_deg"])

                        if range_m >= height_m:
                            estimated_ground_distance_m = math.sqrt(
                                range_m**2 - height_m**2
                            )
                            ground_distance_error_m = (
                                estimated_ground_distance_m - ground_distance_m
                            )
                        else:
                            estimated_ground_distance_m = None
                            ground_distance_error_m = None

                        writer.writerow(
                            {
                                "experiment_id": source["experiment_id"],
                                "run_file": source["run_file"],
                                "time": source["time"],
                                "tag": source["tag"],
                                "height_difference_m": height_m,
                                "target_ground_distance_m": ground_distance_m,
                                "tag_rotation_deg": source["tag_rotation_deg"],
                                "gt_bearing_deg": bearing_deg,
                                "gt_x_m": gt_x_m,
                                "gt_y_m": gt_y_m,
                                "gt_range_3d_m": gt_range_3d_m,
                                "range_m": range_m,
                                "range_error_3d_m": range_m - gt_range_3d_m,
                                "estimated_ground_distance_m": estimated_ground_distance_m,
                                "ground_distance_error_m": ground_distance_error_m,
                                "pdoa_deg": pdoa_deg,
                                "eta_expected_deg": eta_expected_deg,
                                "eta_residual_deg": wrap_degrees(
                                    pdoa_deg - eta_expected_deg
                                ),
                                "estimated_bearing_deg": estimated_bearing_deg,
                                "bearing_error_deg": wrap_degrees(
                                    estimated_bearing_deg - bearing_deg
                                ),
                                "x_m": x_m,
                                "y_m": y_m,
                                "position_error_m": math.hypot(
                                    x_m - gt_x_m, y_m - gt_y_m
                                ),
                                "clk_ppm": source["clk_ppm"],
                                "sequence": source["seq"],
                            }
                        )
                        row_count += 1

    print(f"Static measurements written: {row_count}")
    return output_path


def circular_mean_degrees(values: list[float]) -> float:
    """Return the circular mean of degree-valued observations."""
    sine_mean = fmean(math.sin(math.radians(value)) for value in values)
    cosine_mean = fmean(math.cos(math.radians(value)) for value in values)
    return math.degrees(math.atan2(sine_mean, cosine_mean))


def circular_standard_deviation_degrees(values: list[float]) -> float:
    """Return the circular standard deviation of degree-valued observations."""
    sine_mean = fmean(math.sin(math.radians(value)) for value in values)
    cosine_mean = fmean(math.cos(math.radians(value)) for value in values)
    resultant_length = math.hypot(sine_mean, cosine_mean)
    return math.degrees(math.sqrt(-2.0 * math.log(max(resultant_length, 1e-15))))


def summarize_static_dataset(dataset_path: Path) -> Path:
    """Write raw-measurement and position-error summaries grouped by height."""
    groups: dict[str, list[dict[str, str]]] = {}
    with dataset_path.open(newline="") as dataset_file:
        for row in csv.DictReader(dataset_file):
            groups.setdefault(row["height_difference_m"], []).append(row)

    output_path = CSV_DIRECTORY / "static_metrics_by_height.csv"
    fieldnames = [
        "height_difference_m",
        "samples",
        "ground_distance_samples",
        "range_3d_bias_m",
        "range_3d_mae_m",
        "range_3d_rmse_m",
        "range_3d_std_m",
        "ground_distance_bias_m",
        "ground_distance_mae_m",
        "ground_distance_rmse_m",
        "ground_distance_std_m",
        "eta_residual_circular_mean_deg",
        "eta_residual_circular_std_deg",
        "eta_residual_mae_deg",
        "bearing_error_circular_mean_deg",
        "bearing_error_circular_std_deg",
        "bearing_error_mae_deg",
        "position_error_mean_m",
        "position_error_rmse_m",
        "position_error_std_m",
    ]

    def mae(values: list[float]) -> float:
        return fmean(abs(value) for value in values)

    def rmse(values: list[float]) -> float:
        return math.sqrt(fmean(value * value for value in values))

    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for height_m, rows in sorted(groups.items(), key=lambda item: float(item[0])):
            range_errors = [float(row["range_error_3d_m"]) for row in rows]
            ground_errors = [
                float(row["ground_distance_error_m"])
                for row in rows
                if row["ground_distance_error_m"]
            ]
            eta_errors = [float(row["eta_residual_deg"]) for row in rows]
            bearing_errors = [float(row["bearing_error_deg"]) for row in rows]
            position_errors = [float(row["position_error_m"]) for row in rows]
            writer.writerow(
                {
                    "height_difference_m": height_m,
                    "samples": len(rows),
                    "ground_distance_samples": len(ground_errors),
                    "range_3d_bias_m": fmean(range_errors),
                    "range_3d_mae_m": mae(range_errors),
                    "range_3d_rmse_m": rmse(range_errors),
                    "range_3d_std_m": pstdev(range_errors),
                    "ground_distance_bias_m": fmean(ground_errors),
                    "ground_distance_mae_m": mae(ground_errors),
                    "ground_distance_rmse_m": rmse(ground_errors),
                    "ground_distance_std_m": pstdev(ground_errors),
                    "eta_residual_circular_mean_deg": circular_mean_degrees(eta_errors),
                    "eta_residual_circular_std_deg": circular_standard_deviation_degrees(eta_errors),
                    "eta_residual_mae_deg": mae(eta_errors),
                    "bearing_error_circular_mean_deg": circular_mean_degrees(bearing_errors),
                    "bearing_error_circular_std_deg": circular_standard_deviation_degrees(bearing_errors),
                    "bearing_error_mae_deg": mae(bearing_errors),
                    "position_error_mean_m": fmean(position_errors),
                    "position_error_rmse_m": rmse(position_errors),
                    "position_error_std_m": pstdev(position_errors),
                }
            )

    return output_path


def summarize_static_configurations(dataset_path: Path) -> Path:
    """Write metrics for every height--distance--bearing static configuration.

    Each row aggregates the repeated samples over the four tag rotations while
    retaining the fixed tag associated with that bearing.
    """
    groups: dict[tuple[str, str, str, str], list[dict[str, str]]] = {}
    with dataset_path.open(newline="") as dataset_file:
        for row in csv.DictReader(dataset_file):
            key = (
                row["height_difference_m"],
                row["target_ground_distance_m"],
                row["gt_bearing_deg"],
                row["tag"],
            )
            groups.setdefault(key, []).append(row)

    output_path = CSV_DIRECTORY / "static_metrics_by_configuration.csv"
    fieldnames = [
        "height_difference_m",
        "target_ground_distance_m",
        "gt_bearing_deg",
        "tag",
        "samples",
        "ground_distance_samples",
        "range_3d_bias_m",
        "range_3d_mae_m",
        "range_3d_rmse_m",
        "range_3d_std_m",
        "ground_distance_bias_m",
        "ground_distance_mae_m",
        "ground_distance_rmse_m",
        "ground_distance_std_m",
        "eta_residual_circular_mean_deg",
        "eta_residual_circular_std_deg",
        "eta_residual_mae_deg",
        "bearing_error_circular_mean_deg",
        "bearing_error_circular_std_deg",
        "bearing_error_mae_deg",
        "position_error_mean_m",
        "position_error_rmse_m",
        "position_error_std_m",
    ]

    def mae(values: list[float]) -> float:
        return fmean(abs(value) for value in values)

    def rmse(values: list[float]) -> float:
        return math.sqrt(fmean(value * value for value in values))

    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for key, rows in sorted(
            groups.items(),
            key=lambda item: tuple(float(value) if index < 3 else value
                                   for index, value in enumerate(item[0])),
        ):
            range_errors = [float(row["range_error_3d_m"]) for row in rows]
            ground_errors = [
                float(row["ground_distance_error_m"])
                for row in rows
                if row["ground_distance_error_m"]
            ]
            eta_errors = [float(row["eta_residual_deg"]) for row in rows]
            bearing_errors = [float(row["bearing_error_deg"]) for row in rows]
            position_errors = [float(row["position_error_m"]) for row in rows]
            height_m, distance_m, bearing_deg, tag = key
            writer.writerow(
                {
                    "height_difference_m": height_m,
                    "target_ground_distance_m": distance_m,
                    "gt_bearing_deg": bearing_deg,
                    "tag": tag,
                    "samples": len(rows),
                    "ground_distance_samples": len(ground_errors),
                    "range_3d_bias_m": fmean(range_errors),
                    "range_3d_mae_m": mae(range_errors),
                    "range_3d_rmse_m": rmse(range_errors),
                    "range_3d_std_m": pstdev(range_errors),
                    "ground_distance_bias_m": fmean(ground_errors),
                    "ground_distance_mae_m": mae(ground_errors),
                    "ground_distance_rmse_m": rmse(ground_errors),
                    "ground_distance_std_m": pstdev(ground_errors),
                    "eta_residual_circular_mean_deg": circular_mean_degrees(eta_errors),
                    "eta_residual_circular_std_deg": circular_standard_deviation_degrees(eta_errors),
                    "eta_residual_mae_deg": mae(eta_errors),
                    "bearing_error_circular_mean_deg": circular_mean_degrees(bearing_errors),
                    "bearing_error_circular_std_deg": circular_standard_deviation_degrees(bearing_errors),
                    "bearing_error_mae_deg": mae(bearing_errors),
                    "position_error_mean_m": fmean(position_errors),
                    "position_error_rmse_m": rmse(position_errors),
                    "position_error_std_m": pstdev(position_errors),
                }
            )

    return output_path


def summarize_static_tags(dataset_path: Path) -> Path:
    """Write raw-error metrics for every fixed tag--bearing--height group."""
    groups: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    with dataset_path.open(newline="") as dataset_file:
        for row in csv.DictReader(dataset_file):
            key = (
                row["tag"],
                row["gt_bearing_deg"],
                row["height_difference_m"],
            )
            groups.setdefault(key, []).append(row)

    output_path = CSV_DIRECTORY / "static_metrics_by_tag_height.csv"
    fieldnames = [
        "tag",
        "gt_bearing_deg",
        "height_difference_m",
        "samples",
        "ground_distance_bias_m",
        "ground_distance_mae_m",
        "ground_distance_std_m",
        "eta_residual_circular_mean_deg",
        "eta_residual_circular_std_deg",
        "eta_residual_mae_deg",
        "bearing_error_circular_mean_deg",
        "bearing_error_circular_std_deg",
        "bearing_error_mae_deg",
        "position_error_mean_m",
        "position_error_std_m",
    ]

    def mae(values: list[float]) -> float:
        return fmean(abs(value) for value in values)

    def mean_within_condition_std(
        rows: list[dict[str, str]], field: str, circular: bool = False
    ) -> float:
        """Average repeatability over fixed distance--rotation conditions."""
        conditions: dict[tuple[str, str], list[float]] = {}
        for row in rows:
            value = row[field]
            if not value:
                continue
            key = (row["target_ground_distance_m"], row["tag_rotation_deg"])
            conditions.setdefault(key, []).append(float(value))
        standard_deviations = [
            circular_standard_deviation_degrees(values)
            if circular
            else pstdev(values)
            for values in conditions.values()
            if len(values) > 1
        ]
        return fmean(standard_deviations)

    with output_path.open("w", newline="") as output_file:
        writer = csv.DictWriter(output_file, fieldnames=fieldnames)
        writer.writeheader()
        for (tag, bearing_deg, height_m), rows in sorted(
            groups.items(), key=lambda item: (float(item[0][1]), float(item[0][2]))
        ):
            ground_errors = [
                float(row["ground_distance_error_m"])
                for row in rows
                if row["ground_distance_error_m"]
            ]
            eta_errors = [float(row["eta_residual_deg"]) for row in rows]
            bearing_errors = [float(row["bearing_error_deg"]) for row in rows]
            position_errors = [float(row["position_error_m"]) for row in rows]
            writer.writerow(
                {
                    "tag": tag,
                    "gt_bearing_deg": bearing_deg,
                    "height_difference_m": height_m,
                    "samples": len(rows),
                    "ground_distance_bias_m": fmean(ground_errors),
                    "ground_distance_mae_m": mae(ground_errors),
                    "ground_distance_std_m": mean_within_condition_std(
                        rows, "ground_distance_error_m"
                    ),
                    "eta_residual_circular_mean_deg": circular_mean_degrees(eta_errors),
                    "eta_residual_circular_std_deg": mean_within_condition_std(
                        rows, "eta_residual_deg", circular=True
                    ),
                    "eta_residual_mae_deg": mae(eta_errors),
                    "bearing_error_circular_mean_deg": circular_mean_degrees(bearing_errors),
                    "bearing_error_circular_std_deg": mean_within_condition_std(
                        rows, "bearing_error_deg", circular=True
                    ),
                    "bearing_error_mae_deg": mae(bearing_errors),
                    "position_error_mean_m": fmean(position_errors),
                    "position_error_std_m": mean_within_condition_std(
                        rows, "position_error_m"
                    ),
                }
            )

    return output_path


def plot_range_and_pdoa_by_tag(metrics_path: Path) -> Path:
    """Plot ground-distance bias and PDoA residual MAE by tag and height."""
    import matplotlib.pyplot as plt

    with metrics_path.open(newline="") as metrics_file:
        rows = list(csv.DictReader(metrics_file))

    heights_m = sorted({float(row["height_difference_m"]) for row in rows})
    tags = sorted({row["tag"] for row in rows})
    rows_by_tag_height = {
        (row["tag"], float(row["height_difference_m"])): row for row in rows
    }
    colors = {0.0: "#1f77b4", 2.0: "#ff7f0e", 4.0: "#2ca02c"}
    markers = {0.0: "o", 2.0: "s", 4.0: "^"}
    bar_width = 0.23
    tag_positions = list(range(len(tags)))

    PLOTS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    output_path = PLOTS_DIRECTORY / "static_range_pdoa_by_tag.pdf"
    figure, distance_axis = plt.subplots(figsize=(6.0, 3.15), constrained_layout=True)
    pdoa_axis = distance_axis.twinx()
    for height_index, height_m in enumerate(heights_m):
        offset = (height_index - (len(heights_m) - 1) / 2) * bar_width
        positions = [position + offset for position in tag_positions]
        height_rows = [rows_by_tag_height[(tag, height_m)] for tag in tags]
        distance_bias_cm = [
            100.0 * float(row["ground_distance_bias_m"]) for row in height_rows
        ]
        distance_std_cm = [
            100.0 * float(row["ground_distance_std_m"]) for row in height_rows
        ]
        pdoa_mae_deg = [float(row["eta_residual_mae_deg"]) for row in height_rows]
        pdoa_std_deg = [
            float(row["eta_residual_circular_std_deg"]) for row in height_rows
        ]
        pdoa_lower_error_deg = [
            min(mae_deg, std_deg)
            for mae_deg, std_deg in zip(pdoa_mae_deg, pdoa_std_deg)
        ]
        bars = distance_axis.bar(
            positions,
            distance_bias_cm,
            yerr=distance_std_cm,
            color=colors[height_m],
            width=bar_width,
            capsize=2.5,
            error_kw={"ecolor": colors[height_m], "elinewidth": 0.8},
            label=fr"$h={height_m:g}$ m",
        )
        marker_positions = [
            bar.get_x() + bar.get_width() / 2.0 for bar in bars.patches
        ]
        pdoa_axis.errorbar(
            marker_positions,
            pdoa_mae_deg,
            yerr=[pdoa_lower_error_deg, pdoa_std_deg],
            color=colors[height_m],
            fmt=f"-{markers[height_m]}",
            markersize=4,
            linewidth=1.4,
            capsize=2.5,
            elinewidth=0.8,
        )

    distance_axis.axhline(0.0, color="black", linewidth=0.8)
    distance_axis.set_xticks(tag_positions, tags)
    distance_axis.set_xlabel("Tag")
    distance_axis.set_ylabel("Ground-distance bias [cm]")
    distance_axis.tick_params(axis="y", labelcolor="black")
    distance_axis.set_ylim(-80, 0)
    pdoa_axis.set_ylim(0, 200)
    pdoa_axis.set_yticks(range(0, 201, 25))
    distance_axis.grid(axis="y", color="0.88", linewidth=0.8)
    distance_axis.set_axisbelow(True)
    figure.legend(
        loc="upper center",
        bbox_to_anchor=(0.5, 1.05),
        ncols=3,
        fontsize=8,
        frameon=False,
    )
    pdoa_axis.set_ylabel("PDoA residual MAE [deg]")

    figure.savefig(output_path, bbox_inches="tight", pad_inches=0.02)
    plt.close(figure)
    return output_path


def export_static_plot_data(metrics_path: Path) -> list[Path]:
    """Export the three series used by the publication-quality TikZ plot."""
    with metrics_path.open(newline="") as metrics_file:
        rows = list(csv.DictReader(metrics_file))

    output_paths: list[Path] = []
    for height_m in sorted({float(row["height_difference_m"]) for row in rows}):
        output_path = CSV_DIRECTORY / f"static_range_pdoa_h{height_m:g}.csv"
        height_rows = sorted(
            (row for row in rows if float(row["height_difference_m"]) == height_m),
            key=lambda row: row["tag"],
        )
        with output_path.open("w", newline="") as output_file:
            fieldnames = [
                "tag",
                "ground_distance_bias_cm",
                "ground_distance_std_cm",
                "eta_residual_mae_deg",
                "eta_residual_lower_error_deg",
                "eta_residual_upper_error_deg",
            ]
            writer = csv.DictWriter(output_file, fieldnames=fieldnames)
            writer.writeheader()
            for row in height_rows:
                eta_mae_deg = float(row["eta_residual_mae_deg"])
                eta_std_deg = float(row["eta_residual_circular_std_deg"])
                writer.writerow(
                    {
                        "tag": row["tag"],
                        "ground_distance_bias_cm": 100.0
                        * float(row["ground_distance_bias_m"]),
                        "ground_distance_std_cm": 100.0
                        * float(row["ground_distance_std_m"]),
                        "eta_residual_mae_deg": eta_mae_deg,
                        "eta_residual_lower_error_deg": min(eta_mae_deg, eta_std_deg),
                        "eta_residual_upper_error_deg": eta_std_deg,
                    }
                )
        output_paths.append(output_path)

    return output_paths


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--build-static-dataset",
        action="store_true",
        help="normalize the h=0, 2, and 4 m campaigns into analysis/csv/",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_arguments()
    static_campaigns = discover_static_campaigns()
    uav_campaigns = discover_uav_campaigns()

    print(f"Static campaigns found: {len(static_campaigns)}")
    print(f"UAV campaigns found: {len(uav_campaigns)}")
    print(f"CSV outputs: {CSV_DIRECTORY}")
    print(f"Temporary plots: {PLOTS_DIRECTORY}")

    if args.build_static_dataset:
        dataset_path = build_static_dataset()
        print(f"Output written to: {dataset_path}")
        print(f"Metrics written to: {summarize_static_dataset(dataset_path)}")
        print(
            "Configuration metrics written to: "
            f"{summarize_static_configurations(dataset_path)}"
        )
        tag_metrics_path = summarize_static_tags(dataset_path)
        print(f"Tag metrics written to: {tag_metrics_path}")
        print(f"Temporary plot written to: {plot_range_and_pdoa_by_tag(tag_metrics_path)}")
        print("TikZ plot data written to: " + ", ".join(
            str(path) for path in export_static_plot_data(tag_metrics_path)
        ))


if __name__ == "__main__":
    main()
