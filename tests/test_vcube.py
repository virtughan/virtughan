from __future__ import annotations

import os
import shutil

import mercantile
import numpy as np
import pytest
import rasterio

from virtughan.band_math import evaluate_formula
from virtughan.collections import get_collection
from virtughan.engine import VirtughanProcessor
from virtughan.extract import ExtractProcessor
from virtughan.stac import search_stac
from virtughan.tile import TileProcessor

NEPAL_BBOX = [83.84765625, 28.22697003891833, 83.935546875, 28.304380682962773]

SENTINEL2_START = "2024-12-01"
SENTINEL2_END = "2025-01-01"

LANDSAT_START = "2024-11-01"
LANDSAT_END = "2025-01-01"


# ---- Unit Tests: collections registry ----


class TestCollections:
    def test_get_sentinel2_collection(self):
        config = get_collection("sentinel-2-l2a")
        assert config.collection_id == "sentinel-2-l2a"
        assert "red" in config.bands
        assert "nir" in config.bands
        assert config.bands["red"].resolution == 10

    def test_get_landsat_collection(self):
        config = get_collection("landsat-c2-l2")
        assert config.collection_id == "landsat-c2-l2"
        assert "red" in config.bands
        assert "nir08" in config.bands
        assert config.bands["red"].resolution == 30

    def test_unknown_collection_raises(self):
        with pytest.raises(ValueError, match="Unknown collection"):
            get_collection("nonexistent-collection")

    def test_validate_bands_returns_invalid(self):
        config = get_collection("sentinel-2-l2a")
        invalid = config.validate_bands(["red", "fake_band"])
        assert invalid == ["fake_band"]

    def test_validate_bands_all_valid(self):
        config = get_collection("sentinel-2-l2a")
        invalid = config.validate_bands(["red", "green", "blue"])
        assert invalid == []


# ---- Unit Tests: band_math ----


class TestBandMath:
    def test_ndvi_formula(self):
        nir = np.array([0.8, 0.6, 0.9])
        red = np.array([0.2, 0.3, 0.1])
        result = evaluate_formula(
            "(band2 - band1) / (band2 + band1)", {"band1": red, "band2": nir}
        )
        expected = (nir - red) / (nir + red)
        np.testing.assert_allclose(result, expected)

    def test_single_band_formula(self):
        band = np.array([100.0, 200.0, 300.0])
        result = evaluate_formula("band1 / 10000", {"band1": band})
        np.testing.assert_allclose(result, band / 10000)

    def test_division_by_zero_no_crash(self):
        a = np.array([1.0, 0.0])
        b = np.array([0.0, 0.0])
        result = evaluate_formula("band1 / band2", {"band1": a, "band2": b})
        assert result.shape == (2,)


# ---- Integration Tests: STAC search ----


class TestSTACSearch:
    def test_sentinel2_search_returns_results(self):
        config = get_collection("sentinel-2-l2a")
        results = search_stac(config, NEPAL_BBOX, SENTINEL2_START, SENTINEL2_END, 30, max_items=5)
        assert len(results) > 0
        feature = results[0]
        assert "assets" in feature
        assert "red" in feature["assets"]
        assert "nir" in feature["assets"]
        assert "href" in feature["assets"]["red"]

    def test_landsat_search_returns_results(self):
        config = get_collection("landsat-c2-l2")
        results = search_stac(config, NEPAL_BBOX, LANDSAT_START, LANDSAT_END, 30, max_items=5)
        assert len(results) > 0
        feature = results[0]
        assert "assets" in feature
        assert "red" in feature["assets"]
        assert "nir08" in feature["assets"]

    def test_search_with_high_cloud_filter_returns_fewer(self):
        config = get_collection("sentinel-2-l2a")
        strict = search_stac(config, NEPAL_BBOX, SENTINEL2_START, SENTINEL2_END, 5, max_items=50)
        loose = search_stac(config, NEPAL_BBOX, SENTINEL2_START, SENTINEL2_END, 80, max_items=50)
        assert len(strict) <= len(loose)


# ---- Integration Tests: Engine (VirtughanProcessor) ----


OUTPUT_ENGINE_S2 = "test_output_engine_s2"
OUTPUT_ENGINE_LS = "test_output_engine_ls"


@pytest.fixture(scope="module")
def sentinel2_engine_result():
    if os.path.exists(OUTPUT_ENGINE_S2):
        shutil.rmtree(OUTPUT_ENGINE_S2)

    processor = VirtughanProcessor(
        bbox=NEPAL_BBOX,
        start_date=SENTINEL2_START,
        end_date=SENTINEL2_END,
        cloud_cover=30,
        formula="(band2 - band1) / (band2 + band1)",
        band1="red",
        band2="nir",
        operation="median",
        timeseries=False,
        output_dir=OUTPUT_ENGINE_S2,
        workers=2,
        collection="sentinel-2-l2a",
    )
    processor.compute()
    yield processor
    shutil.rmtree(OUTPUT_ENGINE_S2, ignore_errors=True)


@pytest.fixture(scope="module")
def landsat_engine_result():
    if os.path.exists(OUTPUT_ENGINE_LS):
        shutil.rmtree(OUTPUT_ENGINE_LS)

    processor = VirtughanProcessor(
        bbox=NEPAL_BBOX,
        start_date=LANDSAT_START,
        end_date=LANDSAT_END,
        cloud_cover=30,
        formula="(band2 - band1) / (band2 + band1)",
        band1="red",
        band2="nir08",
        operation="median",
        timeseries=False,
        output_dir=OUTPUT_ENGINE_LS,
        workers=2,
        collection="landsat-c2-l2",
    )
    processor.compute()
    yield processor
    shutil.rmtree(OUTPUT_ENGINE_LS, ignore_errors=True)


class TestEngineSentinel2:
    def test_output_directory_created(self, sentinel2_engine_result):
        assert os.path.exists(sentinel2_engine_result.output_dir)

    def test_output_files_created(self, sentinel2_engine_result):
        files = os.listdir(sentinel2_engine_result.output_dir)
        assert len(files) > 0

    def test_output_geotiff_valid(self, sentinel2_engine_result):
        tiff_files = [
            f
            for f in os.listdir(sentinel2_engine_result.output_dir)
            if f.endswith(".tif") or f.endswith(".tiff")
        ]
        assert len(tiff_files) > 0
        tiff_path = os.path.join(sentinel2_engine_result.output_dir, tiff_files[0])
        with rasterio.open(tiff_path) as ds:
            assert ds.crs is not None
            data = ds.read(1)
            valid_data = data[~np.isnan(data) & (data != ds.nodata if ds.nodata else True)]
            if len(valid_data) > 0:
                assert valid_data.min() >= -1.0
                assert valid_data.max() <= 1.0


class TestEngineLandsat:
    def test_output_directory_created(self, landsat_engine_result):
        assert os.path.exists(landsat_engine_result.output_dir)

    def test_output_files_created(self, landsat_engine_result):
        files = os.listdir(landsat_engine_result.output_dir)
        assert len(files) > 0

    def test_output_geotiff_valid(self, landsat_engine_result):
        tiff_files = [
            f
            for f in os.listdir(landsat_engine_result.output_dir)
            if f.endswith(".tif") or f.endswith(".tiff")
        ]
        assert len(tiff_files) > 0
        tiff_path = os.path.join(landsat_engine_result.output_dir, tiff_files[0])
        with rasterio.open(tiff_path) as ds:
            assert ds.crs is not None
            data = ds.read(1)
            valid_data = data[~np.isnan(data) & (data != ds.nodata if ds.nodata else True)]
            if len(valid_data) > 0:
                assert valid_data.min() >= -1.0
                assert valid_data.max() <= 1.0


# ---- Integration Tests: Extract (ExtractProcessor) ----


OUTPUT_EXTRACT_S2 = "test_output_extract_s2"
OUTPUT_EXTRACT_LS = "test_output_extract_ls"


@pytest.fixture(scope="module")
def sentinel2_extract_result():
    if os.path.exists(OUTPUT_EXTRACT_S2):
        shutil.rmtree(OUTPUT_EXTRACT_S2)

    extractor = ExtractProcessor(
        bbox=NEPAL_BBOX,
        start_date="2024-12-15",
        end_date="2024-12-31",
        cloud_cover=30,
        bands_list=["red", "green", "blue"],
        output_dir=OUTPUT_EXTRACT_S2,
        workers=2,
        collection="sentinel-2-l2a",
    )
    extractor.extract()
    yield extractor
    shutil.rmtree(OUTPUT_EXTRACT_S2, ignore_errors=True)


@pytest.fixture(scope="module")
def landsat_extract_result():
    if os.path.exists(OUTPUT_EXTRACT_LS):
        shutil.rmtree(OUTPUT_EXTRACT_LS)

    extractor = ExtractProcessor(
        bbox=NEPAL_BBOX,
        start_date=LANDSAT_START,
        end_date=LANDSAT_END,
        cloud_cover=30,
        bands_list=["red", "green", "blue"],
        output_dir=OUTPUT_EXTRACT_LS,
        workers=2,
        collection="landsat-c2-l2",
    )
    extractor.extract()
    yield extractor
    shutil.rmtree(OUTPUT_EXTRACT_LS, ignore_errors=True)


class TestExtractSentinel2:
    def test_output_directory_created(self, sentinel2_extract_result):
        assert os.path.exists(sentinel2_extract_result.output_dir)

    def test_output_files_created(self, sentinel2_extract_result):
        files = os.listdir(sentinel2_extract_result.output_dir)
        assert len(files) > 0

    def test_extracted_bands_valid(self, sentinel2_extract_result):
        tiff_files = [
            f
            for f in os.listdir(sentinel2_extract_result.output_dir)
            if f.endswith(".tif") or f.endswith(".tiff")
        ]
        if tiff_files:
            tiff_path = os.path.join(sentinel2_extract_result.output_dir, tiff_files[0])
            with rasterio.open(tiff_path) as ds:
                assert ds.crs is not None
                assert ds.count >= 1
                assert ds.width > 0
                assert ds.height > 0


class TestExtractLandsat:
    def test_output_directory_created(self, landsat_extract_result):
        assert os.path.exists(landsat_extract_result.output_dir)

    def test_output_files_created(self, landsat_extract_result):
        files = os.listdir(landsat_extract_result.output_dir)
        assert len(files) > 0

    def test_extracted_bands_valid(self, landsat_extract_result):
        tiff_files = [
            f
            for f in os.listdir(landsat_extract_result.output_dir)
            if f.endswith(".tif") or f.endswith(".tiff")
        ]
        if tiff_files:
            tiff_path = os.path.join(landsat_extract_result.output_dir, tiff_files[0])
            with rasterio.open(tiff_path) as ds:
                assert ds.crs is not None
                assert ds.count >= 1
                assert ds.width > 0
                assert ds.height > 0


# ---- Integration Tests: Tile (TileProcessor) ----


@pytest.fixture(scope="module")
def tile_coords():
    lat, lon, zoom = 28.28139, 83.91866, 12
    x, y, z = mercantile.tile(lon, lat, zoom)
    return x, y, z


@pytest.mark.asyncio
class TestTileSentinel2:
    async def test_generate_tile_returns_image(self, tile_coords):
        x, y, z = tile_coords
        tile_processor = TileProcessor()
        image_bytes, feature = await tile_processor.cached_generate_tile(
            x=x,
            y=y,
            z=z,
            start_date="2024-01-01",
            end_date="2025-01-01",
            cloud_cover=30,
            band1="red",
            band2="nir",
            formula="(band2 - band1) / (band2 + band1)",
            colormap_str="RdYlGn",
            collection="sentinel-2-l2a",
        )
        assert len(image_bytes) > 0
        assert "datetime" in feature["properties"]

    async def test_generate_tile_landsat(self, tile_coords):
        x, y, z = tile_coords
        tile_processor = TileProcessor()
        image_bytes, feature = await tile_processor.cached_generate_tile(
            x=x,
            y=y,
            z=z,
            start_date="2024-01-01",
            end_date="2025-01-01",
            cloud_cover=30,
            band1="red",
            band2="nir08",
            formula="(band2 - band1) / (band2 + band1)",
            colormap_str="RdYlGn",
            collection="landsat-c2-l2",
        )
        assert len(image_bytes) > 0
        assert "datetime" in feature["properties"]
