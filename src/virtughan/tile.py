from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import matplotlib
import mercantile
import numpy as np
from aiocache import cached
from fastapi import HTTPException
from matplotlib import pyplot as plt
from PIL import Image
from rio_tiler.io import Reader
from shapely.geometry import box, mapping

from .band_math import evaluate_formula
from .collections import get_collection
from .stac import search_stac_async
from .utils import (
    aggregate_time_series,
    filter_intersected_features,
    filter_latest_image_per_grid,
    remove_overlapping_tiles,
    smart_filter_images,
)

matplotlib.use("Agg")


class TileProcessor:
    def __init__(self, cache_time: int = 60):
        self.cache_time = cache_time

    @staticmethod
    def apply_colormap(result: np.ndarray, colormap_str: str) -> Image.Image:
        result_normalized = (result - result.min()) / (result.max() - result.min())
        colormap = plt.get_cmap(colormap_str)
        result_colored = colormap(result_normalized)
        result_image = (result_colored[:, :, :3] * 255).astype(np.uint8)
        return Image.fromarray(result_image)

    @staticmethod
    async def fetch_tile(url: str, x: int, y: int, z: int) -> np.ndarray:
        def read_tile() -> np.ndarray:
            with Reader(input=url) as cog:
                tile, _ = cog.tile(x, y, z)
                return tile

        return await asyncio.to_thread(read_tile)

    @cached(ttl=60 * 1)
    async def cached_generate_tile(
        self,
        x: int,
        y: int,
        z: int,
        start_date: str,
        end_date: str,
        cloud_cover: int,
        band1: str,
        band2: str | None,
        formula: str,
        colormap_str: str = "RdYlGn",
        latest: bool = True,
        operation: str = "median",
        collection: str = "sentinel-2-l2a",
    ) -> tuple[bytes, dict[str, Any]]:
        collection_config = get_collection(collection)
        tile = mercantile.Tile(x, y, z)
        bbox = mercantile.bounds(tile)
        bbox_geojson = mapping(box(bbox.west, bbox.south, bbox.east, bbox.north))
        results = await search_stac_async(
            collection_config, bbox_geojson, start_date, end_date, cloud_cover
        )

        if not results:
            raise HTTPException(status_code=404, detail="No images found for the given parameters")

        results = filter_intersected_features(
            results, [bbox.west, bbox.south, bbox.east, bbox.north]
        )

        if latest:
            image, feature = await self._generate_latest_tile(
                results, x, y, z, band1, band2, formula, colormap_str, collection_config
            )
        else:
            image, feature = await self._generate_timeseries_tile(
                results,
                x,
                y,
                z,
                start_date,
                end_date,
                band1,
                band2,
                formula,
                colormap_str,
                operation,
                collection_config,
            )

        buffered = BytesIO()
        image.save(buffered, format="PNG")
        return buffered.getvalue(), feature

    async def _generate_latest_tile(
        self,
        results: list[dict[str, Any]],
        x: int,
        y: int,
        z: int,
        band1: str,
        band2: str | None,
        formula: str,
        colormap_str: str,
        collection_config: Any,
    ) -> tuple[Image.Image, dict[str, Any]]:
        if not results:
            raise HTTPException(status_code=404, detail="No images found for the given parameters")

        results = filter_latest_image_per_grid(results, collection_config.tile_id_parser)
        if not results:
            raise HTTPException(status_code=404, detail="No images found after filtering")
        feature = results[0]
        if band1 not in feature["assets"]:
            raise HTTPException(
                status_code=400, detail=f"Band '{band1}' not found in image assets"
            )
        band1_url = feature["assets"][band1]["href"]
        band2_url = (
            feature["assets"][band2]["href"] if band2 and band2 in feature["assets"] else None
        )

        try:
            tasks = [self.fetch_tile(band1_url, x, y, z)]
            if band2_url:
                tasks.append(self.fetch_tile(band2_url, x, y, z))
            tiles = await asyncio.gather(*tasks)
            band1_data = tiles[0]
            band2_data = tiles[1] if band2_url else None
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        if band2_data is not None:
            band1_arr = band1_data[0].astype(float)
            band2_arr = band2_data[0].astype(float)
            result = evaluate_formula(formula, {"band1": band1_arr, "band2": band2_arr})
            image = self.apply_colormap(result, colormap_str)
        else:
            inner_bands = band1_data.shape[0]
            if inner_bands == 1:
                band1_arr = band1_data[0].astype(float)
                result = evaluate_formula(formula, {"band1": band1_arr})
                image = self.apply_colormap(result, colormap_str)
            else:
                image = Image.fromarray(band1_data.transpose(1, 2, 0))

        return image, feature

    async def _generate_timeseries_tile(
        self,
        results: list[dict[str, Any]],
        x: int,
        y: int,
        z: int,
        start_date: str,
        end_date: str,
        band1: str,
        band2: str | None,
        formula: str,
        colormap_str: str,
        operation: str,
        collection_config: Any,
    ) -> tuple[Image.Image, dict[str, Any]]:
        results = remove_overlapping_tiles(results, collection_config.tile_id_parser)
        results = smart_filter_images(results, start_date, end_date)

        tasks = []
        valid_features = []
        for feature in results:
            if band1 not in feature["assets"]:
                continue
            if band2 and band2 not in feature["assets"]:
                continue
            band1_url = feature["assets"][band1]["href"]
            band2_url = feature["assets"][band2]["href"] if band2 else None
            tasks.append(self.fetch_tile(band1_url, x, y, z))
            if band2_url:
                tasks.append(self.fetch_tile(band2_url, x, y, z))
            valid_features.append(feature)

        if not valid_features:
            raise HTTPException(status_code=404, detail="No images with requested bands found")

        try:
            tiles = await asyncio.gather(*tasks)
            step = 2 if band2 else 1
            band1_tiles = [tiles[i] for i in range(0, len(tiles), step)]
            band2_tiles = [tiles[i + 1] for i in range(0, len(tiles), step)] if band2 else []
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e)) from e

        band1_agg = aggregate_time_series(
            [tile[0].astype(float) for tile in band1_tiles], operation
        )
        if band2_tiles:
            band2_agg = aggregate_time_series(
                [tile[0].astype(float) for tile in band2_tiles], operation
            )
            result = evaluate_formula(formula, {"band1": band1_agg, "band2": band2_agg})
        else:
            result = evaluate_formula(formula, {"band1": band1_agg})

        image = self.apply_colormap(result, colormap_str)
        return image, valid_features[0]
