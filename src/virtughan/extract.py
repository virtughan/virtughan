from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import IO, Any

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rich.console import Console
from rich.progress import Progress

from .collections import get_collection
from .geo import (
    calculate_window,
    is_window_out_of_bounds,
    save_geotiff,
    transform_bbox,
)
from .stac import search_stac
from .utils import (
    filter_intersected_features,
    remove_overlapping_tiles,
    smart_filter_images,
    zip_files,
)


class ExtractProcessor:
    def __init__(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str,
        cloud_cover: int,
        bands_list: list[str],
        output_dir: str,
        log_file: IO[str] = sys.stdout,
        workers: int = 1,
        zip_output: bool = False,
        smart_filter: bool = True,
        collection: str = "sentinel-2-l2a",
    ):
        self.bbox = bbox
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = cloud_cover
        self.bands_list = bands_list
        self.output_dir = output_dir
        self.console = Console(file=log_file)
        self.workers = workers
        self.zip_output = zip_output
        self.crs: Any = None
        self.transform: Any = None
        self.use_smart_filter = smart_filter
        self.collection_config = get_collection(collection)

        self._validate_bands_list()

    def _validate_bands_list(self) -> None:
        invalid_bands = self.collection_config.validate_bands(self.bands_list)
        if invalid_bands:
            available = ", ".join(self.collection_config.band_names)
            raise ValueError(
                f"Invalid band names: {', '.join(invalid_bands)}. "
                f"Band names should be one of: {available}"
            )

    def _get_band_urls(self, features: list[dict[str, Any]]) -> list[list[str]]:
        urls = []
        for feature in features:
            try:
                band_hrefs = [feature["assets"][band]["href"] for band in self.bands_list]
                urls.append(band_hrefs)
            except KeyError:
                continue
        return urls

    def _fetch_and_save_bands(self, band_urls: list[str], feature_id: str) -> str | None:
        try:
            bands: list[np.ndarray] = []
            bands_meta: list[str] = []
            resolutions: list[tuple[float, float]] = []

            for band_url in band_urls:
                with rasterio.open(band_url) as band_cog:
                    resolutions.append(band_cog.res)

            lowest_resolution = max(resolutions, key=lambda res: res[0] * res[1])

            for band_url in band_urls:
                with rasterio.open(band_url) as band_cog:
                    min_x, min_y, max_x, max_y = transform_bbox(self.bbox, band_cog.crs)
                    band_window = calculate_window(band_cog, min_x, min_y, max_x, max_y)

                    if is_window_out_of_bounds(band_window):
                        return None
                    self.crs = band_cog.crs
                    window_transform = band_cog.window_transform(band_window)

                    band_data = band_cog.read(1, window=band_window).astype(float)

                    if band_cog.res != lowest_resolution:
                        scale_factor_x = band_cog.res[0] / lowest_resolution[0]
                        scale_factor_y = band_cog.res[1] / lowest_resolution[1]
                        dst_height = int(band_data.shape[0] * scale_factor_y)
                        dst_width = int(band_data.shape[1] * scale_factor_x)
                        dst_transform = window_transform * rasterio.Affine.scale(
                            1.0 / scale_factor_x, 1.0 / scale_factor_y
                        )
                        band_data = reproject(
                            source=band_data,
                            destination=np.empty(
                                (dst_height, dst_width),
                                dtype=band_data.dtype,
                            ),
                            src_transform=window_transform,
                            src_crs=band_cog.crs,
                            dst_transform=dst_transform,
                            dst_crs=band_cog.crs,
                            resampling=Resampling.average,
                        )[0]
                        window_transform = dst_transform

                    self.transform = window_transform

                    bands.append(band_data)
                    bands_meta.append(band_url.split("/")[-1].split(".")[0])

            print("Stacking Bands...")
            stacked_bands = np.stack(bands)
            output_file = os.path.join(self.output_dir, f"{feature_id}_bands_export.tif")
            save_geotiff(
                stacked_bands, output_file, self.crs, self.transform, band_descriptions=bands_meta
            )
            return output_file
        except Exception:
            raise

    def extract(self) -> None:
        print("Extracting bands...")
        os.makedirs(self.output_dir, exist_ok=True)

        features = search_stac(
            self.collection_config,
            self.bbox,
            self.start_date,
            self.end_date,
            self.cloud_cover,
        )
        print(f"Total scenes found: {len(features)}")
        filtered_features = filter_intersected_features(features, self.bbox)
        print(f"Scenes covering input area: {len(filtered_features)}")
        overlapping_features_removed = remove_overlapping_tiles(
            filtered_features, self.collection_config.tile_id_parser
        )
        print(f"Scenes after removing overlaps: {len(overlapping_features_removed)}")
        if self.use_smart_filter:
            overlapping_features_removed = smart_filter_images(
                overlapping_features_removed, self.start_date, self.end_date
            )
            print(f"Scenes after applying smart filter: {len(overlapping_features_removed)}")

        band_urls_list = self._get_band_urls(overlapping_features_removed)
        result_lists: list[str | None] = []

        if self.workers > 1:
            print("Using Parallel Processing...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = [
                    executor.submit(self._fetch_and_save_bands, band_urls, feature["id"])
                    for band_urls, feature in zip(band_urls_list, overlapping_features_removed)
                ]
                with Progress(console=self.console) as progress:
                    task = progress.add_task("Extracting Bands", total=len(futures))
                    for future in as_completed(futures):
                        result = future.result()
                        result_lists.append(result)
                        progress.advance(task)
        else:
            with Progress(console=self.console) as progress:
                task = progress.add_task("Extracting Bands", total=len(band_urls_list))
                for band_urls, feature in zip(band_urls_list, overlapping_features_removed):
                    result = self._fetch_and_save_bands(band_urls, feature["id"])
                    result_lists.append(result)
                    progress.advance(task)

        if self.zip_output:
            valid_files = [f for f in result_lists if f is not None]
            zip_files(
                valid_files,
                os.path.join(self.output_dir, "tiff_files.zip"),
            )
