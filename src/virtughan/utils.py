import os
import zipfile
from datetime import datetime, timedelta

import httpx
import numpy as np
import requests
from shapely.geometry import box, shape

STAC_API_URL = "https://earth-search.aws.element84.com/v1/search"


def search_stac_api(bbox, start_date, end_date, cloud_cover):
    """
    Search the STAC API for satellite images.

    Parameters:
    bbox (list): Bounding box coordinates [min_lon, min_lat, max_lon, max_lat].
    start_date (str): Start date for the search (YYYY-MM-DD).
    end_date (str): End date for the search (YYYY-MM-DD).
    cloud_cover (int): Maximum allowed cloud cover percentage.

    Returns:
    list: List of features found in the search.
    """
    search_params = {
        "collections": ["sentinel-2-l2a"],
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": cloud_cover}},
        "bbox": bbox,
        "limit": 100,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    all_features = []
    next_link = None

    while True:
        response = requests.post(
            STAC_API_URL,
            json=search_params if not next_link else next_link["body"],
        )
        response.raise_for_status()
        response_json = response.json()

        all_features.extend(response_json["features"])

        next_link = next((link for link in response_json["links"] if link["rel"] == "next"), None)
        if not next_link:
            break
    return all_features


async def search_stac_api_async(bbox_geojson, start_date, end_date, cloud_cover):
    """
    Asynchronously search the STAC API for satellite images.

    Parameters:
    bbox_geojson (dict): Bounding box in GeoJSON format.
    start_date (str): Start date for the search (YYYY-MM-DD).
    end_date (str): End date for the search (YYYY-MM-DD).
    cloud_cover (int): Maximum allowed cloud cover percentage.

    Returns:
    list: List of features found in the search.
    """
    search_params = {
        "collections": ["sentinel-2-l2a"],
        "datetime": f"{start_date}T00:00:00Z/{end_date}T23:59:59Z",
        "query": {"eo:cloud_cover": {"lt": cloud_cover}},
        "intersects": bbox_geojson,
        "limit": 100,
        "sortby": [{"field": "properties.datetime", "direction": "desc"}],
    }

    all_features = []
    next_link = None

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.post(
                STAC_API_URL,
                json=search_params if not next_link else next_link["body"],
            )
            response.raise_for_status()
            response_json = response.json()

            all_features.extend(response_json["features"])

            next_link = next(
                (link for link in response_json["links"] if link["rel"] == "next"), None
            )
            if not next_link:
                break

    return all_features


def zip_files(file_list, zip_path):
    """
    Zip a list of files.

    Parameters:
    file_list (list): List of file paths to zip.
    zip_path (str): Path to the output zip file.
    """
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for file in file_list:
            zipf.write(file, os.path.basename(file))
    print(f"Saved intermediate images ZIP to {zip_path}")
    for file in file_list:
        os.remove(file)


def filter_latest_image_per_grid(features):
    """
    Filter the latest image per grid.

    Parameters:
    features (list): List of features to filter.

    Returns:
    list: List of filtered features.
    """
    grid_latest = {}
    for feature in features:
        grid = feature["id"].split("_")[1]
        date = feature["properties"]["datetime"]
        if grid not in grid_latest or date > grid_latest[grid]["properties"]["datetime"]:
            grid_latest[grid] = feature
    return list(grid_latest.values())


def filter_intersected_features(features, bbox):
    """
    Filter features that intersect with the bounding box.

    Parameters:
    features (list): List of features to filter.
    bbox (list): Bounding box coordinates [min_lon, min_lat, max_lon, max_lat].

    Returns:
    list: List of filtered features.
    """
    bbox_polygon = box(bbox[0], bbox[1], bbox[2], bbox[3])
    return [feature for feature in features if shape(feature["geometry"]).contains(bbox_polygon)]


def remove_overlapping_sentinel2_tiles(features):
    """
    Remove overlapping Sentinel-2 tiles.

    Parameters:
    features (list): List of features to process.

    Returns:
    list: List of non-overlapping features.
    """
    if not features:
        return []

    zone_counts = {}
    for feature in features:
        zone = feature["id"].split("_")[1][:2]
        zone_counts[zone] = zone_counts.get(zone, 0) + 1

    if not zone_counts:
        return []

    max_zone = max(zone_counts, key=lambda k: zone_counts[k])

    filtered_features = {}
    for feature in features:
        parts = feature["id"].split("_")
        date = parts[2]
        zone = parts[1][:2]

        if zone == max_zone and date not in filtered_features:
            filtered_features[date] = feature

    return list(filtered_features.values())


def aggregate_time_series(data, operation):
    """
    Aggregate a time series of data.

    Parameters:
    data (list): List of data arrays to aggregate.
    operation (str): Operation to apply to the data (mean, median, max, min, std, sum, var).

    Returns:
    numpy.ndarray: Aggregated result.
    """
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


def smart_filter_images(features, start_date: str, end_date: str):
    """
    Apply smart filtering to the image collection , reduces the number of images go through in large timestamps.

    Parameters:
    features (list): List of features to filter.
    start_date (str): Start date for the filtering (YYYY-MM-DD).
    end_date (str): End date for the filtering (YYYY-MM-DD).

    Returns:
    list: List of filtered features.
    """
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
