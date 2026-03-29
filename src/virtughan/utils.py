from __future__ import annotations

import os
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from shapely.geometry import box, shape


def zip_files(file_list: list[str], zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file in file_list:
            zipf.write(file, os.path.basename(file))
    print(f"Saved intermediate images ZIP to {zip_path}")
    for file in file_list:
        os.remove(file)


def filter_latest_image_per_grid(
    features: list[dict[str, Any]],
    tile_id_parser: Callable[[str], tuple[str, str]],
) -> list[dict[str, Any]]:
    grid_latest: dict[str, dict[str, Any]] = {}
    for feature in features:
        grid, _ = tile_id_parser(feature["id"])
        feature_datetime = feature["properties"]["datetime"]
        if (
            grid not in grid_latest
            or feature_datetime > grid_latest[grid]["properties"]["datetime"]
        ):
            grid_latest[grid] = feature
    return list(grid_latest.values())


def filter_intersected_features(
    features: list[dict[str, Any]], bbox: list[float]
) -> list[dict[str, Any]]:
    bbox_polygon = box(bbox[0], bbox[1], bbox[2], bbox[3])
    return [feature for feature in features if shape(feature["geometry"]).contains(bbox_polygon)]


def remove_overlapping_tiles(
    features: list[dict[str, Any]],
    tile_id_parser: Callable[[str], tuple[str, str]],
) -> list[dict[str, Any]]:
    if not features:
        return []

    zone_counts: dict[str, int] = {}
    for feature in features:
        zone, _ = tile_id_parser(feature["id"])
        zone_counts[zone] = zone_counts.get(zone, 0) + 1

    if not zone_counts:
        return []

    max_zone = max(zone_counts, key=lambda k: zone_counts[k])

    filtered: dict[str, dict[str, Any]] = {}
    for feature in features:
        zone, date = tile_id_parser(feature["id"])
        if zone == max_zone and date not in filtered:
            filtered[date] = feature

    return list(filtered.values())


def aggregate_time_series(data: list[np.ndarray], operation: str) -> np.ndarray:
    result_stack = np.ma.stack(data)

    operations = {
        "mean": np.ma.mean,
        "median": np.ma.median,
        "max": np.ma.max,
        "min": np.ma.min,
        "std": np.ma.std,
        "sum": np.ma.sum,
        "var": np.ma.var,
    }

    return operations[operation](result_stack, axis=0)


def smart_filter_images(
    features: list[dict[str, Any]], start_date: str, end_date: str
) -> list[dict[str, Any]]:
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    total_days = (end - start).days

    if total_days <= 30 * 3:
        # For a time range of up to 3 months, select 1 image per 4 days
        frequency = timedelta(days=4)

    elif total_days <= 365:
        frequency = timedelta(days=15)

    elif total_days <= 2 * 365:
        frequency = timedelta(days=30)

    elif total_days <= 3 * 365:
        frequency = timedelta(days=45)
    else:
        # rest, select 1 image per 2 months
        frequency = timedelta(days=60)

    filtered_features = []
    last_selected_date = None
    best_feature = None
    print(
        f"""Filter from : {features[-1]["properties"]["datetime"].split("T")[0]} to : {features[0]["properties"]["datetime"].split("T")[0]}"""
    )
    print(f"Selecting 1 image per {frequency.days} days")

    for feature in sorted(features, key=lambda x: x["properties"]["datetime"]):
        date = datetime.fromisoformat(feature["properties"]["datetime"].split("T")[0])
        if last_selected_date is None or date >= last_selected_date + frequency:
            if best_feature:
                filtered_features.append(best_feature)
            best_feature = feature
            last_selected_date = date
        elif best_feature is not None:
            if (
                feature["properties"]["eo:cloud_cover"]
                < best_feature["properties"]["eo:cloud_cover"]
            ):
                best_feature = feature

    # Handle the last period
    if best_feature:
        filtered_features.append(best_feature)

    return filtered_features
