from __future__ import annotations

from typing import Any

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.windows import Window, from_bounds


def transform_bbox(bbox: list[float], target_crs: Any) -> tuple[float, float, float, float]:
    transformer = Transformer.from_crs("epsg:4326", target_crs, always_xy=True)
    min_x, min_y = transformer.transform(bbox[0], bbox[1])
    max_x, max_y = transformer.transform(bbox[2], bbox[3])
    return min_x, min_y, max_x, max_y


def calculate_window(
    cog: rasterio.DatasetReader,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
) -> Window:
    return from_bounds(min_x, min_y, max_x, max_y, cog.transform)


def is_window_out_of_bounds(window: Window) -> bool:
    return window.col_off < 0 or window.row_off < 0 or window.width <= 0 or window.height <= 0


def save_geotiff(
    data: np.ndarray,
    output_path: str,
    crs: Any,
    transform: Any,
    nodata: float = -9999,
    band_descriptions: list[str] | None = None,
) -> None:
    data = np.where(np.isnan(data), nodata, data)
    with rasterio.open(
        output_path,
        "w",
        driver="GTiff",
        height=data.shape[1],
        width=data.shape[2],
        count=data.shape[0],
        dtype=data.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
    ) as dst:
        for band_index in range(1, data.shape[0] + 1):
            dst.write(data[band_index - 1], band_index)
            if band_descriptions:
                dst.set_band_description(band_index, band_descriptions[band_index - 1])
