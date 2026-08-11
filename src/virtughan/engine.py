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
from scipy.stats import mode as scipy_mode

from .band_math import evaluate_formula
from .collections import get_collection
from .formula import validate_formula
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
        bands: list[str],
        operation: str | None,
        timeseries: bool,
        output_dir: str,
        log_file: IO[str] = sys.stdout,
        cmap: str = "RdYlGn",
        workers: int = 1,
        smart_filter: bool = True,
        collection: str = "sentinel-2-l2a",
        extra_query: dict[str, Any] | None = None,
    ):
        self.bbox = bbox
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = cloud_cover
        self.formula = formula
        self.bands = list(bands)
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
        self.extra_query = extra_query

        invalid = self.collection_config.validate_bands(self.bands)
        if invalid:
            raise ValueError(f"bands not in collection {collection}: {invalid}")
        validate_formula(self.formula, self.bands)

    def fetch_process_custom_band(
        self, band_urls: dict[str, str]
    ) -> tuple[np.ndarray | None, Any, Any, str | None]:
        arrays: dict[str, np.ndarray] = {}
        transforms: dict[str, Any] = {}
        crses: dict[str, Any] = {}
        shapes: dict[str, tuple[int, int]] = {}
        first_url: str | None = None

        for name, url in band_urls.items():
            if first_url is None:
                first_url = url
            with rio.open(url) as cog:
                min_x, min_y, max_x, max_y = transform_bbox(self.bbox, cog.crs)
                window = calculate_window(cog, min_x, min_y, max_x, max_y)
                if is_window_out_of_bounds(window):
                    return None, None, None, None
                data = cog.read(window=window).astype(float)
                arrays[name] = data
                transforms[name] = cog.window_transform(window)
                crses[name] = cog.crs
                shapes[name] = (data.shape[1], data.shape[2])

        reference = self._pick_reference_band(transforms)
        arrays, ref_transform = self._align_to_reference(
            arrays, transforms, crses, shapes, reference
        )

        result = evaluate_formula(self.formula, arrays)
        return result, crses[reference], ref_transform, first_url

    @staticmethod
    def _pick_reference_band(transforms: dict[str, Any]) -> str:
        return min(transforms, key=lambda name: transforms[name][0])

    @staticmethod
    def _align_to_reference(
        arrays: dict[str, np.ndarray],
        transforms: dict[str, Any],
        crses: dict[str, Any],
        shapes: dict[str, tuple[int, int]],
        reference: str,
    ) -> tuple[dict[str, np.ndarray], Any]:
        ref_array = arrays[reference]
        ref_transform = transforms[reference]
        ref_crs = crses[reference]
        ref_height, ref_width = shapes[reference]

        aligned: dict[str, np.ndarray] = {}
        for name, data in arrays.items():
            if name == reference or shapes[name] == (ref_height, ref_width):
                aligned[name] = data
                continue
            resampled = np.zeros_like(ref_array)
            resampled, _ = reproject(
                source=data,
                destination=resampled,
                src_transform=transforms[name],
                src_crs=crses[name],
                dst_transform=ref_transform,
                dst_crs=ref_crs,
                resampling=Resampling.bilinear,
                dst_shape=(ref_height, ref_width),
            )
            aligned[name] = resampled
        return aligned, ref_transform

    def _get_band_urls(self, features: list[dict[str, Any]]) -> list[dict[str, str]]:
        per_feature: list[dict[str, str]] = []
        for feature in features:
            if any(b not in feature["assets"] for b in self.bands):
                continue
            per_feature.append({b: feature["assets"][b]["href"] for b in self.bands})
        return per_feature

    def _extract_date_from_feature(self, feature: dict[str, Any]) -> str:
        _, date = self.collection_config.tile_id_parser(feature)
        return date

    def _process_images(self, features: list[dict[str, Any]]) -> None:
        band_urls_per_feature = self._get_band_urls(features)
        usable_features = [f for f in features if all(b in f["assets"] for b in self.bands)]

        if self.workers > 1:
            self.console.print("Using parallel processing...")
            self._process_parallel(band_urls_per_feature, usable_features)
        else:
            self._process_sequential(band_urls_per_feature, usable_features)

    def _process_parallel(
        self,
        band_urls_per_feature: list[dict[str, str]],
        features: list[dict[str, Any]],
    ) -> None:
        reference_band = self.bands[0]
        url_to_feature = {
            feature["assets"][reference_band]["href"]: feature for feature in features
        }
        with ThreadPoolExecutor(max_workers=self.workers) as executor:
            futures = [
                executor.submit(self.fetch_process_custom_band, urls)
                for urls in band_urls_per_feature
            ]
            with Progress(console=self.console) as progress:
                total = len(futures)
                task = progress.add_task("Computing Band Calculation", total=total)
                for index, future in enumerate(as_completed(futures), start=1):
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
                    percent = int(index / total * 100) if total else 100
                    self.console.print(f"PROGRESS: {percent}% | {index}/{total}")

    def _process_sequential(
        self,
        band_urls_per_feature: list[dict[str, str]],
        features: list[dict[str, Any]],
    ) -> None:
        with Progress(console=self.console) as progress:
            total = len(band_urls_per_feature)
            task = progress.add_task("Computing Band Calculation", total=total)
            for index, (urls, feature) in enumerate(zip(band_urls_per_feature, features), start=1):
                result, self.crs, self.transform, _ = self.fetch_process_custom_band(urls)
                if result is not None:
                    self.result_list.append(result)
                    date = self._extract_date_from_feature(feature)
                    self.dates.append(date)
                    if self.timeseries:
                        self._save_intermediate_image(result, feature["id"])
                progress.advance(task)
                percent = int(index / total * 100) if total else 100
                self.console.print(f"PROGRESS: {percent}% | {index}/{total}")

    def _save_intermediate_image(self, result: np.ndarray, image_name: str) -> None:
        output_file = os.path.join(self.output_dir, f"{image_name}_result.tif")
        save_geotiff(result, output_file, self.crs, self.transform)
        self.intermediate_images.append(output_file)
        self.intermediate_images_with_text.append(self.add_text_to_image(output_file, image_name))

    def _aggregate_results(self) -> np.ndarray:
        assert self.operation is not None
        sorted_dates_and_results = sorted(zip(self.dates, self.result_list), key=lambda x: x[0])
        sorted_dates, sorted_results = zip(*sorted_dates_and_results)

        max_shape = tuple(max(s) for s in zip(*[arr.shape for arr in sorted_results]))
        padded_result_list = [self._pad_array(arr, max_shape) for arr in sorted_results]
        result_stack = np.ma.stack(padded_result_list)

        def _mode_along_axis(data: np.ndarray, axis: int = 0) -> np.ndarray:
            filled = np.ma.filled(data, np.nan)
            return scipy_mode(filled, axis=axis, nan_policy="omit", keepdims=False).mode

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

        aggregated_result = operations[self.operation](result_stack, axis=0)

        dates_numeric = np.arange(len(sorted_dates))
        values_per_date = np.array(
            operations[self.operation](result_stack, axis=(1, 2, 3)), dtype=float
        )

        valid_mask = np.isfinite(values_per_date)
        if valid_mask.sum() >= 2:
            slope, intercept = np.polyfit(
                dates_numeric[valid_mask], values_per_date[valid_mask], 1
            )
            trend_line = slope * dates_numeric + intercept
        else:
            trend_line = np.full_like(values_per_date, np.nan)

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
        image, vmin, vmax = self._create_image(result_aggregate)
        self._plot_result(image, output_file, vmin, vmax)
        save_geotiff(result_aggregate, output_file, self.crs, self.transform)

    @staticmethod
    def _robust_range(band: np.ndarray) -> tuple[float, float]:
        if isinstance(band, np.ma.MaskedArray):
            valid = np.ma.compressed(band)
        else:
            valid = band[np.isfinite(band)]
        if valid.size == 0:
            return 0.0, 1.0
        vmin, vmax = np.percentile(valid, [2, 98])
        if vmax <= vmin:
            vmax = vmin + 1.0
        return float(vmin), float(vmax)

    def _create_image(self, data: np.ndarray) -> tuple[np.ndarray, float, float]:
        if data.shape[0] == 1:
            band = data[0]
            vmin, vmax = self._robust_range(band)
            filled = np.ma.filled(band, vmin) if isinstance(band, np.ma.MaskedArray) else band
            normalized = np.clip((filled - vmin) / (vmax - vmin), 0, 1)
            colormap = plt.get_cmap(self.cmap)
            colored = colormap(normalized)
            return (colored[:, :, :3] * 255).astype(np.uint8), vmin, vmax

        image_array = np.transpose(data, (1, 2, 0))
        vmin, vmax = self._robust_range(image_array)
        filled = (
            np.ma.filled(image_array, vmin)
            if isinstance(image_array, np.ma.MaskedArray)
            else image_array
        )
        normalized = np.clip((filled - vmin) / (vmax - vmin), 0, 1) * 255
        return normalized.astype(np.uint8), vmin, vmax

    def _plot_result(self, image: np.ndarray, output_file: str, vmin: float, vmax: float) -> None:
        plt.figure(figsize=(10, 10))
        plt.imshow(image)
        plt.title(f"Aggregated {self.operation} Calculation")
        plt.xlabel(
            f"From {self.start_date} to {self.end_date}\nCloud Cover < {self.cloud_cover}%\nBBox: {self.bbox}\nTotal Scene Processed: {len(self.result_list)}"
        )
        plt.colorbar(
            plt.cm.ScalarMappable(
                cmap=plt.get_cmap(self.cmap),
                norm=plt.Normalize(vmin=vmin, vmax=vmax),
            ),
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
            ).astype(float)
            vmin, vmax = self._robust_range(image_array)
            image_array = np.clip((image_array - vmin) / (vmax - vmin), 0, 1) * 255
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

    def _search_and_filter(self) -> list[dict[str, Any]]:
        features = search_stac(
            self.collection_config,
            self.bbox,
            self.start_date,
            self.end_date,
            self.cloud_cover,
            extra_query=self.extra_query,
        )
        self.console.print(f"Total scenes found: {len(features)}")
        filtered_features = filter_intersected_features(features, self.bbox)
        self.console.print(f"Scenes covering input area: {len(filtered_features)}")
        overlapping_features_removed = remove_overlapping_tiles(
            filtered_features, self.collection_config.tile_id_parser
        )
        self.console.print(f"Scenes after removing overlaps: {len(overlapping_features_removed)}")
        if self.use_smart_filter:
            overlapping_features_removed = smart_filter_images(
                overlapping_features_removed,
                self.start_date,
                self.end_date,
                self.collection_config.cloud_cover_property,
            )
            self.console.print(f"Scenes after smart filter: {len(overlapping_features_removed)}")
        return overlapping_features_removed

    def compute(self) -> None:
        self.console.print("[bold blue]Engine starting...[/bold blue]")
        os.makedirs(self.output_dir, exist_ok=True)

        self.console.print("Searching STAC catalog...")
        features = self._search_and_filter()
        self._process_images(features)

        if self.result_list and self.operation:
            self.console.print("Aggregating results...")
            result_aggregate = self._aggregate_results()
            output_file = os.path.join(self.output_dir, "custom_band_output_aggregate.tif")
            self.console.print("Saving aggregated result with colormap...")
            self.save_aggregated_result_with_colormap(result_aggregate, output_file)

        if self.timeseries:
            self.console.print("Creating GIF and zipping TIFF files...")
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
                self.console.print("[yellow]No images found for the given parameters[/yellow]")
