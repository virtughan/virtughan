import asyncio
from io import BytesIO

import matplotlib
import mercantile
import numpy as np
from aiocache import cached
from fastapi import HTTPException
from matplotlib import pyplot as plt
from PIL import Image
from rio_tiler.io import Reader
from shapely.geometry import box, mapping

from .utils import (
    aggregate_time_series,
    filter_intersected_features,
    filter_latest_image_per_grid,
    remove_overlapping_sentinel2_tiles,
    search_stac_api_async,
    smart_filter_images,
)

matplotlib.use("Agg")


class TileProcessor:
    """
    Processor for generating and caching tiles from satellite images.
    """

    def __init__(self, cache_time=60):
        """
        Initialize the TileProcessor.

        Parameters:
        cache_time (int): Cache time in seconds.
        """
        self.cache_time = cache_time

    @staticmethod
    def apply_colormap(result, colormap_str):
        """
        Apply a colormap to the result.

        Parameters:
        result (numpy.ndarray): Array of results to apply the colormap to.
        colormap_str (str): Name of the colormap to apply.

        Returns:
        PIL.Image.Image: Image with the applied colormap.
        """
        result_normalized = (result - result.min()) / (result.max() - result.min())
        colormap = plt.get_cmap(colormap_str)
        result_colored = colormap(result_normalized)
        result_image = (result_colored[:, :, :3] * 255).astype(np.uint8)
        return Image.fromarray(result_image)

    @staticmethod
    async def fetch_tile(url, x, y, z):
        """
        Fetch a tile from the given URL.

        Parameters:
        url (str): URL of the tile.
        x (int): X coordinate of the tile.
        y (int): Y coordinate of the tile.
        z (int): Zoom level of the tile.

        Returns:
        numpy.ndarray: Array of the tile data.
        """

        def read_tile():
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
        band2: str,
        formula: str,
        colormap_str: str = "RdYlGn",
        latest: bool = True,
        operation: str = "median",
    ) -> tuple[bytes, dict]:
        """
        Generate and cache a tile.

        Parameters:
        x (int): X coordinate of the tile.
        y (int): Y coordinate of the tile.
        z (int): Zoom level of the tile.
        start_date (str): Start date for the data extraction (YYYY-MM-DD).
        end_date (str): End date for the data extraction (YYYY-MM-DD).
        cloud_cover (int): Maximum allowed cloud cover percentage.
        band1 (str): First band for the formula.
        band2 (str): Second band for the formula.
        formula (str): Formula to apply to the bands.
        colormap_str (str): Name of the colormap to apply.
        latest (bool): Whether to use the latest image.
        operation (str): Operation to apply to the time series.

        Returns:
        bytes: Image bytes of the generated tile.
        """
        tile = mercantile.Tile(x, y, z)
        bbox = mercantile.bounds(tile)
        bbox_geojson = mapping(box(bbox.west, bbox.south, bbox.east, bbox.north))
        results = await search_stac_api_async(bbox_geojson, start_date, end_date, cloud_cover)

        if not results:
            raise HTTPException(status_code=404, detail="No images found for the given parameters")

        results = filter_intersected_features(
            results, [bbox.west, bbox.south, bbox.east, bbox.north]
        )
        if latest:
            if len(results) > 0:
                results = filter_latest_image_per_grid(results)
                feature = results[0]
                band1_url = feature["assets"][band1]["href"]
                band2_url = feature["assets"][band2]["href"] if band2 else None

                try:
                    tasks = [self.fetch_tile(band1_url, x, y, z)]
                    if band2_url:
                        tasks.append(self.fetch_tile(band2_url, x, y, z))

                    tiles = await asyncio.gather(*tasks)
                    band1 = tiles[0]
                    band2 = tiles[1] if band2_url else None
                except Exception as e:
                    raise HTTPException(status_code=500, detail=str(e)) from e

                if band2 is not None:
                    band1 = band1[0].astype(float)
                    band2 = band2[0].astype(float)
                    result = eval(formula)
                    image = self.apply_colormap(result, colormap_str)
                else:
                    inner_bands = band1.shape[0]
                    if inner_bands == 1:
                        band1 = band1[0].astype(float)
                        result = eval(formula)
                        image = self.apply_colormap(result, colormap_str)
                    else:
                        band1 = band1.transpose(1, 2, 0)
                        image = Image.fromarray(band1)
            else:
                raise HTTPException(
                    status_code=404, detail="No images found for the given parameters"
                )
        else:
            results = remove_overlapping_sentinel2_tiles(results)
            results = smart_filter_images(results, start_date, end_date)
            band1_tiles = []
            band2_tiles = []

            tasks = []
            for feature in results:
                band1_url = feature["assets"][band1]["href"]
                band2_url = feature["assets"][band2]["href"] if band2 else None
                tasks.append(self.fetch_tile(band1_url, x, y, z))
                if band2_url:
                    tasks.append(self.fetch_tile(band2_url, x, y, z))

            try:
                tiles = await asyncio.gather(*tasks)
                for i in range(0, len(tiles), 2 if band2 else 1):
                    band1_tiles.append(tiles[i])
                    if band2:
                        band2_tiles.append(tiles[i + 1])
            except Exception as e:
                raise HTTPException(status_code=500, detail=str(e)) from e

            band1 = aggregate_time_series(
                [tile[0].astype(float) for tile in band1_tiles], operation
            )
            if band2_tiles:
                band2 = aggregate_time_series(
                    [tile[0].astype(float) for tile in band2_tiles], operation
                )
                result = eval(formula)
            else:
                result = eval(formula)

            image = self.apply_colormap(result, colormap_str)

        buffered = BytesIO()
        image.save(buffered, format="PNG")
        image_bytes = buffered.getvalue()

        return image_bytes, feature
