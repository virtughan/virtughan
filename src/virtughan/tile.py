from __future__ import annotations

import asyncio
from collections.abc import Awaitable
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
        _CMAP_ALIASES = {
            "PrGn": "PRGn",
            "Viridis": "viridis",
            "Inferno": "inferno",
            "Magma": "magma",
            "Plasma": "plasma",
            "Cividis": "cividis",
            "PrGn_r": "PRGn_r",
            "Viridis_r": "viridis_r",
            "Inferno_r": "inferno_r",
            "Magma_r": "magma_r",
            "Plasma_r": "plasma_r",
            "Cividis_r": "cividis_r",
        }
        cmap_name = _CMAP_ALIASES.get(colormap_str, colormap_str)
        try:
            colormap = plt.get_cmap(cmap_name)
        except ValueError:
            colormap = plt.get_cmap("RdYlGn")
        result_normalized = (result - result.min()) / (result.max() - result.min())
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
        bands: tuple[str, ...],
        formula: str,
        colormap_str: str = "RdYlGn",
        latest: bool = True,
        operation: str = "median",
        collection: str = "sentinel-2-l2a",
        mode: str | None = None,
    ) -> tuple[bytes, dict[str, Any]]:
        bands_list = list(bands)
        collection_config = get_collection(collection)
        tile = mercantile.Tile(x, y, z)
        bbox = mercantile.bounds(tile)
        bbox_geojson = mapping(box(bbox.west, bbox.south, bbox.east, bbox.north))
        extra_query = {"sar:instrument_mode": {"eq": mode}} if mode else None
        results = await search_stac_async(
            collection_config,
            bbox_geojson,
            start_date,
            end_date,
            cloud_cover,
            extra_query=extra_query,
        )

        if not results:
            raise HTTPException(status_code=404, detail="No images found for the given parameters")

        results = filter_intersected_features(
            results, [bbox.west, bbox.south, bbox.east, bbox.north]
        )

        if latest:
            image, feature = await self._generate_latest_tile(
                results, x, y, z, bands_list, formula, colormap_str, collection_config
            )
        else:
            image, feature = await self._generate_timeseries_tile(
                results,
                x,
                y,
                z,
                start_date,
                end_date,
                bands_list,
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
        bands: list[str],
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
        for band in bands:
            if band not in feature["assets"]:
                raise HTTPException(
                    status_code=400, detail=f"Band '{band}' not found in image assets"
                )

        urls = [feature["assets"][band]["href"] for band in bands]
        try:
            tiles = await asyncio.gather(*[self.fetch_tile(url, x, y, z) for url in urls])
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        if len(bands) == 1 and tiles[0].shape[0] > 1:
            image = Image.fromarray(tiles[0].transpose(1, 2, 0))
            return image, feature

        arrays = {band: tile[0].astype(float) for band, tile in zip(bands, tiles)}
        result = evaluate_formula(formula, arrays)
        image = self.apply_colormap(result, colormap_str)
        return image, feature

    async def _generate_timeseries_tile(
        self,
        results: list[dict[str, Any]],
        x: int,
        y: int,
        z: int,
        start_date: str,
        end_date: str,
        bands: list[str],
        formula: str,
        colormap_str: str,
        operation: str,
        collection_config: Any,
    ) -> tuple[Image.Image, dict[str, Any]]:
        results = remove_overlapping_tiles(results, collection_config.tile_id_parser)
        results = smart_filter_images(
            results, start_date, end_date, collection_config.cloud_cover_property
        )

        tasks: list[Awaitable[np.ndarray]] = []
        valid_features: list[dict[str, Any]] = []
        for feature in results:
            if any(band not in feature["assets"] for band in bands):
                continue
            for band in bands:
                tasks.append(self.fetch_tile(feature["assets"][band]["href"], x, y, z))
            valid_features.append(feature)

        if not valid_features:
            raise HTTPException(status_code=404, detail="No images with requested bands found")

        try:
            tiles = await asyncio.gather(*tasks)
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

        step = len(bands)
        per_band_stacks: dict[str, list[np.ndarray]] = {band: [] for band in bands}
        for feature_index in range(len(valid_features)):
            base = feature_index * step
            for band_index, band in enumerate(bands):
                per_band_stacks[band].append(tiles[base + band_index][0].astype(float))

        aggregated = {
            band: aggregate_time_series(stack, operation)
            for band, stack in per_band_stacks.items()
        }

        result = evaluate_formula(formula, aggregated)
        image = self.apply_colormap(result, colormap_str)
        return image, valid_features[0]
