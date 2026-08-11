from __future__ import annotations

import time

from fastapi.testclient import TestClient

import API
from API import app

client = TestClient(app)

NEPAL_BBOX = "83.84765625,28.22697003891833,83.935546875,28.304380682962773"
SENTINEL2_COLLECTION = "sentinel-2-l2a"
LANDSAT_COLLECTION = "landsat-c2-l2"
SENTINEL1_COLLECTION = "sentinel-1-rtc"


class TestIndexPages:
    def test_index_page(self):
        response = client.get("/")
        assert response.status_code == 200
        assert "virtughan" in response.text.lower()

    def test_about_page(self):
        response = client.get("/about")
        assert response.status_code == 200


class TestCollectionsEndpoint:
    def test_list_collections(self):
        response = client.get("/collections")
        assert response.status_code == 200
        data = response.json()
        assert SENTINEL2_COLLECTION in data
        assert LANDSAT_COLLECTION in data
        assert SENTINEL1_COLLECTION in data
        assert "bands" in data[SENTINEL2_COLLECTION]
        assert "bands" in data[LANDSAT_COLLECTION]

    def test_sentinel2_has_expected_bands(self):
        response = client.get("/collections")
        bands = response.json()[SENTINEL2_COLLECTION]["bands"]
        for band in ["red", "green", "blue", "nir"]:
            assert band in bands

    def test_landsat_has_expected_bands(self):
        response = client.get("/collections")
        bands = response.json()[LANDSAT_COLLECTION]["bands"]
        for band in ["red", "green", "blue", "nir08"]:
            assert band in bands

    def test_sentinel1_has_expected_bands(self):
        response = client.get("/collections")
        bands = response.json()[SENTINEL1_COLLECTION]["bands"]
        assert set(bands) == {"vv", "vh", "hh", "hv"}


class TestBandsEndpoint:
    def test_sentinel2_bands(self):
        response = client.get("/bands", params={"collection": SENTINEL2_COLLECTION})
        assert response.status_code == 200
        data = response.json()
        assert "red" in data
        assert data["red"]["resolution"] == 10

    def test_landsat_bands(self):
        response = client.get("/bands", params={"collection": LANDSAT_COLLECTION})
        assert response.status_code == 200
        data = response.json()
        assert "red" in data
        assert data["red"]["resolution"] == 30

    def test_invalid_collection(self):
        response = client.get("/bands", params={"collection": "nonexistent"})
        assert response.status_code == 404

    def test_bands_response_shape_matches_frontend(self):
        response = client.get("/bands", params={"collection": SENTINEL2_COLLECTION})
        data = response.json()
        for band_name, band_info in data.items():
            assert isinstance(band_name, str)
            assert isinstance(band_info["resolution"], int)

    def test_landsat_bands_response_shape_matches_frontend(self):
        response = client.get("/bands", params={"collection": LANDSAT_COLLECTION})
        data = response.json()
        for band_name, band_info in data.items():
            assert isinstance(band_name, str)
            assert isinstance(band_info["resolution"], int)


class TestSearchEndpoint:
    def test_sentinel2_search(self):
        response = client.get(
            "/search",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        feature = data["features"][0]
        assert "assets" in feature
        assert "red" in feature["assets"]

    def test_landsat_search(self):
        response = client.get(
            "/search",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) > 0
        feature = data["features"][0]
        assert "assets" in feature
        assert "red" in feature["assets"]
        assert "nir08" in feature["assets"]

    def test_search_feature_structure_matches_frontend(self):
        response = client.get(
            "/search",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        data = response.json()
        feature = data["features"][0]
        assert isinstance(feature["id"], str)
        assert "datetime" in feature["properties"]
        assert "eo:cloud_cover" in feature["properties"]
        assert "geometry" in feature
        assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
        for asset_info in feature["assets"].values():
            assert "href" in asset_info

    def test_landsat_search_feature_structure_matches_frontend(self):
        response = client.get(
            "/search",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "collection": LANDSAT_COLLECTION,
            },
        )
        data = response.json()
        feature = data["features"][0]
        assert isinstance(feature["id"], str)
        assert "datetime" in feature["properties"]
        assert "eo:cloud_cover" in feature["properties"]
        assert "geometry" in feature
        assert feature["geometry"]["type"] in ("Polygon", "MultiPolygon")
        for asset_info in feature["assets"].values():
            assert "href" in asset_info


class TestTileEndpoint:
    def test_sentinel1_tile_does_not_require_cloud_cover_property(self, monkeypatch):
        async def fake_generate_tile(*args, **kwargs):
            return b"png", {"properties": {"datetime": "2025-01-15T12:30:42Z"}}

        monkeypatch.setattr(API.TileProcessor, "cached_generate_tile", fake_generate_tile)
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2025-01-01",
                "end_date": "2025-01-20",
                "bands": "vv,vh",
                "formula": "10 * log10(vv / vh)",
                "collection": SENTINEL1_COLLECTION,
                "mode": "IW",
            },
        )

        assert response.status_code == 200
        assert response.headers["X-Image-Date"] == "2025-01-15T12:30:42Z"
        assert "X-Cloud-Cover" not in response.headers

    def test_sentinel2_tile_single_band(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red",
                "formula": "red",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0
        assert "X-Computation-Time" in response.headers
        assert "X-Image-Date" in response.headers

    def test_sentinel2_tile_ndvi(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0

    def test_landsat_tile_single_band(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red",
                "formula": "red",
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0

    def test_landsat_tile_ndvi(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red,nir08",
                "formula": "(nir08 - red) / (nir08 + red)",
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0

    def test_tile_invalid_band(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "bands": "fake_band",
                "formula": "fake_band",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400

    def test_tile_zoom_too_low(self):
        response = client.get(
            "/tile/5/3055/1728",
            params={
                "bands": "red",
                "formula": "red",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400

    def test_tile_default_band_is_red(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_tile_formula_extra_band_rejected(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "bands": "red,nir,blue",
                "formula": "(nir - red) / (nir + red)",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "not used by formula" in response.json()["detail"]

    def test_tile_formula_missing_band_rejected(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-01-01",
                "end_date": "2025-01-01",
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + swir16)",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "unknown band" in response.json()["detail"]

    def test_tile_timeseries_with_operation(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-09-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "timeseries": True,
                "operation": "median",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0

    def test_landsat_tile_timeseries_with_operation(self):
        response = client.get(
            "/tile/12/3055/1728",
            params={
                "start_date": "2024-09-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands": "red,nir08",
                "formula": "(nir08 - red) / (nir08 + red)",
                "timeseries": True,
                "operation": "median",
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"
        assert len(response.content) > 0


def _poll_export_completion(uid: str, timeout: int = 180) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        log_response = client.get("/logs", params={"uid": uid})
        if log_response.status_code == 200:
            logs = log_response.text
            if "completed" in logs.lower():
                return True
            if "error" in logs.lower():
                return False
        time.sleep(5)
    return False


class TestExportEndpoint:
    def test_sentinel2_export_starts(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "uid" in data
        assert "message" in data

    def test_sentinel2_export_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files_response = client.get("/list-files", params={"uid": uid})
        assert files_response.status_code == 200
        files = files_response.json()
        assert "tiff_files.zip" in files or any(
            f.endswith((".tif", ".tiff", ".png")) for f in files
        ), f"No output files found, got: {list(files.keys())}"

    def test_landsat_export_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "formula": "(nir08 - red) / (nir08 + red)",
                "bands": "red,nir08",
                "timeseries": True,
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files_response = client.get("/list-files", params={"uid": uid})
        assert files_response.status_code == 200
        files = files_response.json()
        assert "tiff_files.zip" in files or any(
            f.endswith((".tif", ".tiff", ".png")) for f in files
        ), f"No output files found, got: {list(files.keys())}"

    def test_export_timeseries_output_files(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "output.gif" in files
        assert "tiff_files.zip" in files
        png_files = [f for f in files if f.endswith("_result_text.png")]
        assert len(png_files) > 0, f"No per-scene PNG files found, got: {list(files.keys())}"
        assert "runtime.log" in files

    def test_export_with_operation_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "operation": "median",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "custom_band_output_aggregate.tif" in files
        assert "custom_band_output_aggregate_colormap.png" in files
        assert "values_over_time.png" in files

    def test_export_mode_operation_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "operation": "mode",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "custom_band_output_aggregate.tif" in files

    def test_landsat_export_timeseries_output_files(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "formula": "(nir08 - red) / (nir08 + red)",
                "bands": "red,nir08",
                "timeseries": True,
                "collection": LANDSAT_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "output.gif" in files
        assert "tiff_files.zip" in files
        png_files = [f for f in files if f.endswith("_result_text.png")]
        assert len(png_files) > 0, f"No per-scene PNG files found, got: {list(files.keys())}"

    def test_landsat_export_with_operation_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "formula": "(nir08 - red) / (nir08 + red)",
                "bands": "red,nir08",
                "timeseries": True,
                "operation": "median",
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "custom_band_output_aggregate.tif" in files
        assert "custom_band_output_aggregate_colormap.png" in files
        assert "values_over_time.png" in files

    def test_landsat_export_mode_operation_completes(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "formula": "(nir08 - red) / (nir08 + red)",
                "bands": "red,nir08",
                "timeseries": True,
                "operation": "mode",
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files = client.get("/list-files", params={"uid": uid}).json()
        assert "custom_band_output_aggregate.tif" in files

    def test_landsat_export_with_smart_filters(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "formula": "(nir08 - red) / (nir08 + red)",
                "bands": "red,nir08",
                "timeseries": True,
                "smart_filters": True,
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

    def test_export_timeseries_false_requires_operation(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "timeseries": False,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400

    def test_export_with_smart_filters(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "formula": "(nir - red) / (nir + red)",
                "bands": "red,nir",
                "timeseries": True,
                "smart_filters": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 201
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

    def test_export_invalid_band(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "fake_band",
                "formula": "fake_band",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400

    def test_export_invalid_collection(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red",
                "formula": "red",
                "collection": "nonexistent",
            },
        )
        assert response.status_code == 400

    def test_export_formula_extra_band_rejected(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red,nir,blue",
                "formula": "(nir - red) / (nir + red)",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "not used by formula" in response.json()["detail"]

    def test_export_formula_missing_band_rejected(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red,nir",
                "formula": "(nir - red) / swir16",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "unknown band" in response.json()["detail"]

    def test_export_formula_syntax_error_rejected(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red,nir",
                "formula": "(nir - red /",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "invalid formula" in response.json()["detail"]

    def test_export_formula_attribute_access_blocked(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red",
                "formula": "red.__class__",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400
        assert "forbidden control characters" in response.json()["detail"]

    def test_export_four_band_formula(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands": "red,nir,swir16,swir22",
                "formula": "(nir - red) / (nir + red) + 0.1 * (swir22 - swir16)",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 201

    def test_export_mode_on_non_s1_rejected(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "collection": SENTINEL2_COLLECTION,
                "mode": "IW",
            },
        )
        assert response.status_code == 400
        assert "sentinel-1-rtc" in response.json()["detail"]

    def test_export_mode_invalid_value_rejected(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "bands": "vv,vh",
                "formula": "10 * log10(vv / vh)",
                "collection": "sentinel-1-rtc",
                "mode": "XYZ",
            },
        )
        assert response.status_code == 400
        assert "Invalid mode" in response.json()["detail"]

    def test_export_sentinel1_iw_accepted(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2025-01-01",
                "end_date": "2025-01-20",
                "bands": "vv,vh",
                "formula": "10 * log10(vv / vh)",
                "timeseries": True,
                "collection": "sentinel-1-rtc",
                "mode": "IW",
            },
        )
        assert response.status_code == 201
        assert "uid" in response.json()

    def test_export_sentinel1_no_cloud_cover_required(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2025-01-01",
                "end_date": "2025-01-20",
                "bands": "vv",
                "formula": "vv",
                "timeseries": True,
                "collection": "sentinel-1-rtc",
            },
        )
        assert response.status_code == 201


class TestImageDownloadEndpoint:
    def test_sentinel2_download_starts(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands_list": "red,green,blue",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        assert "uid" in response.json()

    def test_sentinel2_download_completes(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands_list": "red,green,blue",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Download {uid} did not complete in time"

        files_response = client.get("/list-files", params={"uid": uid})
        assert files_response.status_code == 200
        files = files_response.json()
        assert len(files) > 0, "Expected files, got empty dict"

    def test_landsat_download_completes(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands_list": "red,green,blue",
                "collection": LANDSAT_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Download {uid} did not complete in time"

        files_response = client.get("/list-files", params={"uid": uid})
        assert files_response.status_code == 200
        files = files_response.json()
        assert len(files) > 0, "Expected files, got empty dict"

    def test_download_with_smart_filters(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands_list": "red,green,blue",
                "smart_filters": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 200
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Download {uid} did not complete in time"

    def test_landsat_download_with_smart_filters(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-11-01",
                "end_date": "2025-01-01",
                "cloud_cover": 30,
                "bands_list": "red,green,blue",
                "smart_filters": True,
                "collection": LANDSAT_COLLECTION,
            },
        )
        assert response.status_code == 200
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Download {uid} did not complete in time"

    def test_download_invalid_bands(self):
        response = client.get(
            "/image-download",
            params={
                "bbox": NEPAL_BBOX,
                "bands_list": "fake_band1,fake_band2",
                "collection": SENTINEL2_COLLECTION,
            },
        )
        assert response.status_code == 400


class TestLogsEndpoint:
    def test_logs_not_found(self):
        response = client.get("/logs", params={"uid": "nonexistent_uid"})
        assert response.status_code == 404
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

    def test_logs_active_processing_returns_text(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        time.sleep(2)
        log_response = client.get("/logs", params={"uid": uid})
        assert log_response.status_code == 200
        assert log_response.headers["content-type"] == "text/plain; charset=utf-8"
        assert len(log_response.text) > 0
        _poll_export_completion(uid)


class TestListFilesEndpoint:
    def test_list_files_not_found(self):
        response = client.get("/list-files", params={"uid": "nonexistent_uid"})
        assert response.status_code == 404

    def test_list_files_response_shape(self):
        response = client.get(
            "/export",
            params={
                "bbox": NEPAL_BBOX,
                "start_date": "2024-12-15",
                "end_date": "2024-12-31",
                "cloud_cover": 30,
                "bands": "red,nir",
                "formula": "(nir - red) / (nir + red)",
                "timeseries": True,
                "collection": SENTINEL2_COLLECTION,
            },
        )
        uid = response.json()["uid"]
        assert _poll_export_completion(uid), f"Export {uid} did not complete in time"

        files_response = client.get("/list-files", params={"uid": uid})
        files = files_response.json()
        assert isinstance(files, dict)
        for filename, filesize in files.items():
            assert isinstance(filename, str)
            assert isinstance(filesize, int)
            assert filesize > 0
