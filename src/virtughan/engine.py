from __future__ import annotations

import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import IO, Any

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import rasterio as rio
from PIL import Image
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rich.console import Console
from rich.progress import Progress

from .band_math import evaluate_formula
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

matplotlib.use("Agg")


class VirtughanProcessor:
    def __init__(
        self,
        bbox: list[float],
        start_date: str,
        end_date: str,
        cloud_cover: int,
        formula: str,
        band1: str,
        band2: str | None,
        operation: str,
        timeseries: bool,
        output_dir: str,
        log_file: IO[str] = sys.stdout,
        cmap: str = "RdYlGn",
        workers: int = 1,
        smart_filter: bool = True,
        collection: str = "sentinel-2-l2a",
    ):
        self.bbox = bbox
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = cloud_cover
        self.formula = formula or "band1"
        self.band1 = band1
        self.band2 = band2
        self.operation = operation
        self.timeseries = timeseries
        self.output_dir = output_dir
        self.console = Console(file=log_file)
        self.cmap = cmap
        self.workers = workers
        self.result_list: list[np.ndarray] = []
        self.dates: list[str] = []
        self.crs: Any = None
        self.transform: Any = None
        self.intermediate_images: list[str] = []
        self.intermediate_images_with_text: list[str] = []
        self.use_smart_filter = smart_filter
        self.collection_config = get_collection(collection)

    def fetch_process_custom_band(
        self, band1_url: str, band2_url: str | None
    ) -> tuple[np.ndarray | None, Any, Any, str | None]:
        try:
            with rio.open(band1_url) as band1_cog:
                min_x, min_y, max_x, max_y = transform_bbox(self.bbox, band1_cog.crs)
                band1_window = calculate_window(band1_cog, min_x, min_y, max_x, max_y)

                if is_window_out_of_bounds(band1_window):
                    return None, None, None, None

                band1_data = band1_cog.read(window=band1_window).astype(float)
                band1_transform = band1_cog.window_transform(band1_window)
                band1_height, band1_width = band1_data.shape[1], band1_data.shape[2]

                if band2_url:
                    with rio.open(band2_url) as band2_cog:
                        min_x, min_y, max_x, max_y = transform_bbox(self.bbox, band2_cog.crs)
                        band2_window = calculate_window(band2_cog, min_x, min_y, max_x, max_y)

                        if is_window_out_of_bounds(band2_window):
                            return None, None, None, None

                        band2_data = band2_cog.read(window=band2_window).astype(float)
                        band2_transform = band2_cog.window_transform(band2_window)
                        band2_height, band2_width = (
                            band2_data.shape[1],
                            band2_data.shape[2],
                        )

                        band1_data, band2_data, current_transform = self._resample_bands(
                            band1_data,
                            band1_transform,
                            band1_cog.crs,
                            band1_height,
                            band1_width,
                            band2_data,
                            band2_transform,
                            band2_cog.crs,
                            band2_height,
                            band2_width,
                        )

                        result = evaluate_formula(
                            self.formula, {"band1": band1_data, "band2": band2_data}
                        )
                else:
                    if band1_data.shape[0] == 1:
                        result = evaluate_formula(self.formula, {"band1": band1_data})
                    else:
                        result = band1_data
                    current_transform = band1_transform

            return result, band1_cog.crs, current_transform, band1_url

        except Exception:
            raise

    def _resample_bands(
        self,
        band1_data: np.ndarray,
        band1_transform: Any,
        band1_crs: Any,
        band1_height: int,
        band1_width: int,
        band2_data: np.ndarray,
        band2_transform: Any,
        band2_crs: Any,
        band2_height: int,
        band2_width: int,
    ) -> tuple[np.ndarray, np.ndarray, Any]:
        if band1_height == band2_height and band1_width == band2_width:
            return band1_data, band2_data, band1_transform

        band1_res = band1_transform[0]
        band2_res = band2_transform[0]

        if band1_res > band2_res:
            resampled_band2 = np.zeros_like(band1_data)
            resampled_band2, _ = reproject(
                source=band2_data,
                destination=resampled_band2,
                src_transform=band2_transform,
                src_crs=band2_crs,
                dst_transform=band1_transform,
                dst_crs=band1_crs,
                resampling=Resampling.bilinear,
                dst_shape=(band1_height, band1_width),
            )
            return band1_data, resampled_band2, band1_transform
        else:
            resampled_band1 = np.zeros_like(band2_data)
            resampled_band1, _ = reproject(
                source=band1_data,
                destination=resampled_band1,
                src_transform=band1_transform,
                src_crs=band1_crs,
                dst_transform=band2_transform,
                dst_crs=band2_crs,
                resampling=Resampling.bilinear,
                dst_shape=(band2_height, band2_width),
            )
            return resampled_band1, band2_data, band2_transform

    def _get_band_urls(self, features: list[dict[str, Any]]) -> tuple[list[str], list[str | None]]:
        band1_urls = [feature["assets"][self.band1]["href"] for feature in features]
        band2_urls: list[str | None] = (
            [feature["assets"][self.band2]["href"] for feature in features]
            if self.band2
            else [None] * len(features)
        )
        return band1_urls, band2_urls

    def _extract_date_from_feature(self, feature: dict[str, Any]) -> str:
        _, date = self.collection_config.tile_id_parser(feature["id"])
        return date

    def _process_images(self, features: list[dict[str, Any]]) -> None:
        band1_urls, band2_urls = self._get_band_urls(features)

        if self.workers > 1:
            print("Using Parallel Processing...")
            self._process_parallel(band1_urls, band2_urls, features)
        else:
            self._process_sequential(band1_urls, band2_urls, features)

    def _process_parallel(
        self,
        band1_urls: list[str],
        band2_urls: list[str | None],
        features: list[dict[str, Any]],
    ) -> None:
        url_to_feature = {feature["assets"][self.band1]["href"]: feature for feature in features}
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [
                executor.submit(self.fetch_process_custom_band, b1, b2)
                for b1, b2 in zip(band1_urls, band2_urls)
            ]
            with Progress(console=self.console) as progress:
                task = progress.add_task("Computing Band Calculation", total=len(futures))
                for future in as_completed(futures):
                    result, crs, current_transform, name_url = future.result()
                    if result is not None:
                        self.result_list.append(result)
                        self.crs = crs
                        self.transform = current_transform
                        feature = url_to_feature[name_url]
                        date = self._extract_date_from_feature(feature)
                        self.dates.append(date)
                        if self.timeseries:
                            self._save_intermediate_image(result, feature["id"])
                    progress.advance(task)

    def _process_sequential(
        self,
        band1_urls: list[str],
        band2_urls: list[str | None],
        features: list[dict[str, Any]],
    ) -> None:
        with Progress(console=self.console) as progress:
            task = progress.add_task("Computing Band Calculation", total=len(band1_urls))
            for band1_url, band2_url, feature in zip(band1_urls, band2_urls, features):
                result, self.crs, self.transform, _ = self.fetch_process_custom_band(
                    band1_url, band2_url
                )
                if result is not None:
                    self.result_list.append(result)
                    date = self._extract_date_from_feature(feature)
                    self.dates.append(date)
                    if self.timeseries:
                        self._save_intermediate_image(result, feature["id"])
                progress.advance(task)

    def _save_intermediate_image(self, result: np.ndarray, image_name: str) -> None:
        output_file = os.path.join(self.output_dir, f"{image_name}_result.tif")
        save_geotiff(result, output_file, self.crs, self.transform)
        self.intermediate_images.append(output_file)
        self.intermediate_images_with_text.append(self.add_text_to_image(output_file, image_name))

    def _aggregate_results(self) -> np.ndarray:
        sorted_dates_and_results = sorted(zip(self.dates, self.result_list), key=lambda x: x[0])
        sorted_dates, sorted_results = zip(*sorted_dates_and_results)

        max_shape = tuple(max(s) for s in zip(*[arr.shape for arr in sorted_results]))
        padded_result_list = [self._pad_array(arr, max_shape) for arr in sorted_results]
        result_stack = np.ma.stack(padded_result_list)

        operations = {
            "mean": np.ma.mean,
            "median": np.ma.median,
            "max": np.ma.max,
            "min": np.ma.min,
            "std": np.ma.std,
            "sum": np.ma.sum,
            "var": np.ma.var,
        }

        aggregated_result = operations[self.operation](result_stack, axis=0)

        dates_numeric = np.arange(len(sorted_dates))
        values_per_date = operations[self.operation](result_stack, axis=(1, 2, 3))

        slope, intercept = np.polyfit(dates_numeric, values_per_date, 1)
        trend_line = slope * dates_numeric + intercept

        plt.figure(figsize=(10, 5))
        plt.plot(
            sorted_dates,
            values_per_date,
            marker="o",
            linestyle="-",
            label=f"{self.operation.capitalize()} Value",
        )
        plt.plot(sorted_dates, trend_line, color="red", linestyle="--", label="Trend Line")
        plt.xlabel("Date")
        plt.ylabel(f"{self.operation.capitalize()} Value")
        plt.title(f"{self.operation.capitalize()} Value Over Time")
        plt.grid(True)
        plt.xticks(rotation=45)
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(self.output_dir, "values_over_time.png"))
        plt.close()

        return aggregated_result

    def save_aggregated_result_with_colormap(
        self, result_aggregate: np.ndarray, output_file: str
    ) -> None:
        result_aggregate = np.ma.masked_invalid(result_aggregate)
        image = self._create_image(result_aggregate)
        self._plot_result(image, output_file)
        save_geotiff(result_aggregate, output_file, self.crs, self.transform)

    def _create_image(self, data: np.ndarray) -> np.ndarray:
        if data.shape[0] == 1:
            result_normalized = (data[0] - data[0].min()) / (data[0].max() - data[0].min())
            colormap = plt.get_cmap(self.cmap)
            result_colored = colormap(result_normalized)
            return (result_colored[:, :, :3] * 255).astype(np.uint8)
        else:
            image_array = np.transpose(data, (1, 2, 0))
            image_array = (
                (image_array - image_array.min()) / (image_array.max() - image_array.min()) * 255
            )
            return image_array.astype(np.uint8)

    def _plot_result(self, image: np.ndarray, output_file: str) -> None:
        plt.figure(figsize=(10, 10))
        plt.imshow(image)
        plt.title(f"Aggregated {self.operation} Calculation")
        plt.xlabel(
            f"From {self.start_date} to {self.end_date}\nCloud Cover < {self.cloud_cover}%\nBBox: {self.bbox}\nTotal Scene Processed: {len(self.result_list)}"
        )
        plt.colorbar(
            plt.cm.ScalarMappable(cmap=plt.get_cmap(self.cmap)),
            ax=plt.gca(),
            shrink=0.5,
        )
        plt.savefig(
            output_file.replace(".tif", "_colormap.png"),
            bbox_inches="tight",
            pad_inches=0.1,
        )
        plt.close()

    def _pad_array(
        self,
        array: np.ndarray,
        target_shape: tuple[int, ...],
        fill_value: float = np.nan,
    ) -> np.ndarray:
        pad_width = [
            (0, max(0, target - current)) for current, target in zip(array.shape, target_shape)
        ]
        return np.pad(array, pad_width, mode="constant", constant_values=fill_value)

    def add_text_to_image(self, image_path: str, text: str) -> str:
        with rio.open(image_path) as src:
            image_array = (
                src.read(1) if src.count == 1 else np.dstack([src.read(i) for i in range(1, 4)])
            )
            image_array = (
                (image_array - image_array.min()) / (image_array.max() - image_array.min()) * 255
            )
            pil_image = Image.fromarray(image_array.astype(np.uint8))

        plt.figure(figsize=(10, 10))
        plt.imshow(pil_image, cmap=self.cmap if src.count == 1 else None)
        plt.axis("off")
        plt.title(text)
        temp_image_path = os.path.splitext(image_path)[0] + "_text.png"
        plt.savefig(temp_image_path, bbox_inches="tight", pad_inches=0.1)
        plt.close()
        return temp_image_path

    @staticmethod
    def create_gif(image_list: list[str], output_path: str, duration_per_image: int = 1) -> None:
        sorted_image_list = sorted(image_list)
        images = [Image.open(image_path) for image_path in sorted_image_list]
        max_width = max(img.width for img in images)
        max_height = max(img.height for img in images)
        resized_images = [
            img.resize((max_width, max_height), Image.Resampling.LANCZOS) for img in images
        ]
        frame_duration = duration_per_image * 1000
        resized_images[0].save(
            output_path,
            save_all=True,
            append_images=resized_images[1:],
            duration=frame_duration,
            loop=0,
        )
        print(f"Saved timeseries GIF to {output_path}")

    def _search_and_filter(self) -> list[dict[str, Any]]:
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
        return overlapping_features_removed

    def compute(self) -> None:
        print("Engine starting...")
        os.makedirs(self.output_dir, exist_ok=True)
        if not self.band1:
            raise ValueError("Band1 is required")

        print("Searching STAC .....")
        features = self._search_and_filter()
        self._process_images(features)

        if self.result_list and self.operation:
            print("Aggregating results...")
            result_aggregate = self._aggregate_results()
            output_file = os.path.join(self.output_dir, "custom_band_output_aggregate.tif")
            print("Saving aggregated result with colormap...")
            self.save_aggregated_result_with_colormap(result_aggregate, output_file)

        if self.timeseries:
            print("Creating GIF and zipping TIFF files...")
            if self.intermediate_images:
                self.create_gif(
                    self.intermediate_images_with_text,
                    os.path.join(self.output_dir, "output.gif"),
                )
                zip_files(
                    self.intermediate_images,
                    os.path.join(self.output_dir, "tiff_files.zip"),
                )
            else:
                print("No images found for the given parameters")
