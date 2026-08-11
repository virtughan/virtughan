from __future__ import annotations

import logging
import os
import zipfile
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from scipy.stats import mode as scipy_mode
from shapely.geometry import box, shape

logger = logging.getLogger(__name__)


def zip_files(file_list: list[str], zip_path: str) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file in file_list:
            zipf.write(file, os.path.basename(file))
    logger.info("Saved intermediate images ZIP to %s", zip_path)
    for file in file_list:
        os.remove(file)


def filter_latest_image_per_grid(
    features: list[dict[str, Any]],
    tile_id_parser: Callable[[dict[str, Any]], tuple[str, str]],
) -> list[dict[str, Any]]:
    grid_latest: dict[str, dict[str, Any]] = {}
    for feature in features:
        grid, _ = tile_id_parser(feature)
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
    tile_id_parser: Callable[[dict[str, Any]], tuple[str, str]],
) -> list[dict[str, Any]]:
    if not features:
        return []

    zone_counts: dict[str, int] = {}
    for feature in features:
        zone, _ = tile_id_parser(feature)
        zone_counts[zone] = zone_counts.get(zone, 0) + 1

    if not zone_counts:
        return []

    max_zone = max(zone_counts, key=lambda k: zone_counts[k])

    filtered: dict[str, dict[str, Any]] = {}
    for feature in features:
        zone, date = tile_id_parser(feature)
        if zone == max_zone and date not in filtered:
            filtered[date] = feature

    return list(filtered.values())


def _mode_along_axis(data: np.ndarray, axis: int = 0) -> np.ndarray:
    filled = np.ma.filled(data, np.nan)
    return scipy_mode(filled, axis=axis, nan_policy="omit", keepdims=False).mode


def aggregate_time_series(data: list[np.ndarray], operation: str) -> np.ndarray:
    result_stack = np.ma.stack(data)

    operations: dict[str, Any] = {
        "mean": np.ma.mean,
        "median": np.ma.median,
        "max": np.ma.max,
        "min": np.ma.min,
        "std": np.ma.std,
        "sum": np.ma.sum,
        "var": np.ma.var,
        "mode": _mode_along_axis,
    }

    return operations[operation](result_stack, axis=0)


def smart_filter_images(
    features: list[dict[str, Any]],
    start_date: str,
    end_date: str,
    ranking_property: str | None = "eo:cloud_cover",
) -> list[dict[str, Any]]:
    if not features:
        return []

    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    total_days = (end - start).days

    if total_days <= 90:
        # Up to 3 months: select 1 image per 14 days (bi-weekly)
        frequency = timedelta(days=14)

    elif total_days <= 365:
        # Up to 1 year: select 1 image per month
        frequency = timedelta(days=30)

    elif total_days <= 3 * 365:
        # Up to 3 years: select 1 image per quarter
        frequency = timedelta(days=90)

    else:
        # More than 3 years: select 1 image per 6 months
        frequency = timedelta(days=180)

    filtered_features = []
    last_selected_date = None
    best_feature = None
    logger.info(
        "Filter from %s to %s",
        features[-1]["properties"]["datetime"].split("T")[0],
        features[0]["properties"]["datetime"].split("T")[0],
    )
    logger.info("Selecting 1 image per %d days", frequency.days)

    for feature in sorted(features, key=lambda x: x["properties"]["datetime"]):
        date = datetime.fromisoformat(feature["properties"]["datetime"].split("T")[0])
        if last_selected_date is None or date >= last_selected_date + frequency:
            if best_feature:
                filtered_features.append(best_feature)
            best_feature = feature
            last_selected_date = date
        elif best_feature is not None and ranking_property:
            candidate_rank = feature["properties"].get(ranking_property)
            best_rank = best_feature["properties"].get(ranking_property)
            if candidate_rank is not None and (best_rank is None or candidate_rank < best_rank):
                best_feature = feature

    # Handle the last period
    if best_feature:
        filtered_features.append(best_feature)

    return filtered_features
