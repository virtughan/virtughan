from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import matplotlib
import numpy as np
import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from matplotlib import pyplot as plt
from PIL import Image
from rich.console import Console
from shapely.geometry import box, mapping
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.status import HTTP_504_GATEWAY_TIMEOUT

from src.virtughan.collections import COLLECTIONS, SENTINEL1_MODES, get_collection
from src.virtughan.engine import VirtughanProcessor
from src.virtughan.extract import ExtractProcessor
from src.virtughan.formula import FormulaError, validate_formula
from src.virtughan.stac import search_stac_async
from src.virtughan.tile import TileProcessor

matplotlib.use("Agg")

# region Configuration

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
EXPIRY_DURATION_HOURS = int(os.getenv("EXPIRY_DURATION_HOURS", "1"))
EXPIRY_DURATION = timedelta(hours=EXPIRY_DURATION_HOURS)
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "120"))
STATIC_EXPORT_DIR = os.getenv("STATIC_EXPORT_DIR", "static/export")
STATIC_DIR = os.getenv("STATIC_DIR", "static")
RATE_LIMIT_DEFAULT = os.getenv("RATE_LIMIT_DEFAULT", "60/minute")
RATE_LIMIT_EXPORT = os.getenv("RATE_LIMIT_EXPORT", "10/minute")
RATE_LIMIT_TILE = os.getenv("RATE_LIMIT_TILE", "120/minute")
MAX_BBOX_AREA_SQ_DEG = float(os.getenv("MAX_BBOX_AREA_SQ_DEG", "25.0"))
MAX_DATE_RANGE_DAYS = int(os.getenv("MAX_DATE_RANGE_DAYS", "1825"))

VALID_OPERATIONS = frozenset(["mean", "median", "max", "min", "std", "sum", "var", "mode"])

# endregion

# region Logging


def _setup_logging() -> None:
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer: Any
    if LOG_FORMAT == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, LOG_LEVEL.upper(), logging.INFO))


_setup_logging()
logger = structlog.get_logger("virtughan.api")

# endregion

# region Validation


def _safe_uid_path(uid: str, *subpath: str) -> str:
    path = os.path.realpath(os.path.join(STATIC_EXPORT_DIR, uid, *subpath))
    base = os.path.realpath(STATIC_EXPORT_DIR)
    if not path.startswith(base + os.sep):
        raise HTTPException(status_code=400, detail="Invalid UID")
    return path


def _parse_bbox(bbox_str: str) -> list[float]:
    try:
        coords = list(map(float, bbox_str.split(",")))
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid bbox format. Expected: west,south,east,north"
        ) from exc
    if len(coords) != 4:
        raise HTTPException(status_code=400, detail="Bbox must have exactly 4 coordinates")
    west, south, east, north = coords
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        raise HTTPException(status_code=400, detail="Longitude must be between -180 and 180")
    if not (-90 <= south <= 90 and -90 <= north <= 90):
        raise HTTPException(status_code=400, detail="Latitude must be between -90 and 90")
    if west >= east or south >= north:
        raise HTTPException(
            status_code=400, detail="Invalid bbox: west < east and south < north required"
        )
    area = (east - west) * (north - south)
    if area > MAX_BBOX_AREA_SQ_DEG:
        raise HTTPException(
            status_code=400,
            detail=f"Bbox area ({area:.1f} sq deg) exceeds limit ({MAX_BBOX_AREA_SQ_DEG})",
        )
    return coords


def _validate_dates(start_date: str | None, end_date: str | None) -> tuple[str, str]:
    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(
            status_code=400, detail="Invalid date format. Expected: YYYY-MM-DD"
        ) from exc
    if start >= end:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")
    if (end - start).days > MAX_DATE_RANGE_DAYS:
        raise HTTPException(
            status_code=400,
            detail=f"Date range exceeds maximum ({MAX_DATE_RANGE_DAYS} days)",
        )
    return start_date, end_date


def _parse_bands(bands_str: str) -> list[str]:
    bands = [b.strip() for b in bands_str.split(",") if b.strip()]
    if not bands:
        raise HTTPException(status_code=400, detail="bands must not be empty")
    return bands


def _validate_formula_request(collection: str, formula: str, bands_str: str) -> list[str]:
    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    bands = _parse_bands(bands_str)
    invalid = config.validate_bands(bands)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Bands not in {collection}: {invalid}",
        )

    try:
        validate_formula(formula, bands)
    except FormulaError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return bands


def _validate_mode(collection: str, mode: str | None) -> dict[str, Any] | None:
    if mode is None:
        return None
    if collection != "sentinel-1-rtc":
        raise HTTPException(
            status_code=400,
            detail="mode filter only applies to sentinel-1-rtc",
        )
    if mode not in SENTINEL1_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Choose from: {sorted(SENTINEL1_MODES)}",
        )
    return {"sar:instrument_mode": {"eq": mode}}


# endregion

# region App setup

limiter = Limiter(key_func=get_remote_address, default_limits=[RATE_LIMIT_DEFAULT])


@asynccontextmanager
async def lifespan(application: FastAPI):
    logger.info("starting_application")
    task = asyncio.create_task(_cleanup_expired_folders())
    yield
    task.cancel()
    logger.info("shutting_down_application")


OPENAPI_TAGS = [
    {"name": "frontend", "description": "HTML frontend endpoints"},
    {"name": "compute", "description": "Band computation and export"},
    {"name": "tiles", "description": "On-the-fly tile generation"},
    {"name": "search", "description": "STAC catalog search"},
    {"name": "data", "description": "Collection and band metadata"},
    {"name": "monitoring", "description": "Health and status"},
]

app = FastAPI(
    title="Virtughan API",
    description=(
        "Virtual Computation Cube for Earth Observation Satellite Data. "
        "Compute band math, generate tiles, extract raw imagery from "
        "Sentinel-1, Sentinel-2, and Landsat collections via STAC APIs."
    ),
    version="1.1.1",
    lifespan=lifespan,
    openapi_tags=OPENAPI_TAGS,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.middleware("http")
async def timeout_middleware(request: Request, call_next):
    try:
        return await asyncio.wait_for(call_next(request), timeout=REQUEST_TIMEOUT)
    except asyncio.TimeoutError:
        logger.warning("request_timeout", path=request.url.path)
        return JSONResponse(
            {"detail": "Request processing exceeded the time limit."},
            status_code=HTTP_504_GATEWAY_TIMEOUT,
        )


@app.middleware("http")
async def no_cache_middleware(request: Request, call_next):
    """Ensure export and tile responses are not cached by the browser.

    This prevents stale frontend georaster tiles or modal images from being
    re-used after a new export/job has started.
    """
    response = await call_next(request)
    path = request.url.path or ""
    # Disable caching for export static files and generated tiles
    if path.startswith("/static/export") or path.startswith("/tile/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory="templates")

# endregion

# region Frontend


@app.get("/", response_class=HTMLResponse, tags=["frontend"], include_in_schema=False)
async def read_index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/about", response_class=HTMLResponse, tags=["frontend"], include_in_schema=False)
async def read_about(request: Request):
    return templates.TemplateResponse(request, "about.html")


@app.get("/qgis-plugin", response_class=HTMLResponse, tags=["frontend"], include_in_schema=False)
async def read_qgis_plugin(request: Request):
    return templates.TemplateResponse(request, "qgis-plugin.html")


# endregion

# region Monitoring


@app.get("/health", tags=["monitoring"])
async def health_check():
    return {"status": "healthy"}


@app.get("/list-files", tags=["monitoring"])
@limiter.limit(RATE_LIMIT_DEFAULT)
async def list_files(request: Request, uid: str = Query(..., description="Export job UID")):
    directory = _safe_uid_path(uid)
    if not os.path.exists(directory):
        raise HTTPException(status_code=404, detail="Directory not found")

    files = {}
    for filename in os.listdir(directory):
        filepath = os.path.join(directory, filename)
        if os.path.isfile(filepath):
            files[filename] = os.path.getsize(filepath)

    return JSONResponse(content=files)


@app.get("/logs", tags=["monitoring"])
@limiter.limit(RATE_LIMIT_DEFAULT)
async def get_logs(request: Request, uid: str = Query(..., description="Export job UID")):
    log_file = _safe_uid_path(uid, "runtime.log")
    if not os.path.exists(log_file):
        return Response("Log file not found", media_type="text/plain", status_code=404)
    with open(log_file) as file:
        logs = file.readlines()[-30:]
    return Response("\n".join(logs), media_type="text/plain")


# endregion

# region Data


@app.get("/collections", tags=["data"])
async def list_collections():
    return {
        name: {
            "bands": {
                band_name: {
                    "resolution": band.resolution,
                    "wavelength": band.wavelength,
                    "description": band.description,
                }
                for band_name, band in config.bands.items()
            }
        }
        for name, config in COLLECTIONS.items()
    }


@app.get("/bands", tags=["data"])
async def get_bands(
    collection: str = Query("sentinel-2-l2a", description="Collection name"),
):
    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {
        band_name: {
            "resolution": band.resolution,
            "wavelength": band.wavelength,
            "description": band.description,
        }
        for band_name, band in config.bands.items()
    }


# endregion

# region Search


@app.get("/search", tags=["search"])
@limiter.limit(RATE_LIMIT_DEFAULT)
async def search_images(
    request: Request,
    bbox: str = Query(..., description="Bounding box: west,south,east,north"),
    cloud_cover: int = Query(30, ge=0, le=100, description="Maximum cloud cover percentage"),
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
    mode: str | None = Query(
        None,
        description=(
            "Sentinel-1 acquisition mode (IW, EW, SM, WV). Only valid for sentinel-1-rtc."
        ),
    ),
):
    bbox_coords = _parse_bbox(bbox)
    start_date, end_date = _validate_dates(start_date, end_date)

    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    extra_query = _validate_mode(collection, mode)

    west, south, east, north = bbox_coords
    bbox_geojson = mapping(box(west, south, east, north))

    response = await search_stac_async(
        config,
        bbox_geojson,
        start_date,
        end_date,
        cloud_cover,
        extra_query=extra_query,
    )
    return JSONResponse(content={"type": "FeatureCollection", "features": response})


# endregion

# region Compute


@app.get("/export", tags=["compute"])
@limiter.limit(RATE_LIMIT_EXPORT)
async def compute_aoi_over_time(
    request: Request,
    background_tasks: BackgroundTasks,
    bbox: str = Query(..., description="Bounding box: west,south,east,north"),
    start_date: str = Query(
        (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d"),
        description="Start date (YYYY-MM-DD)",
    ),
    end_date: str = Query(
        datetime.now().strftime("%Y-%m-%d"),
        description="End date (YYYY-MM-DD)",
    ),
    cloud_cover: int = Query(30, ge=0, le=100, description="Cloud cover percentage"),
    formula: str = Query(
        "(nir - red) / (nir + red)",
        description="Band math formula using band names (e.g. NDVI: (nir - red) / (nir + red))",
    ),
    bands: str = Query(
        "red,nir",
        description="Comma-separated band names referenced by the formula",
    ),
    operation: str = Query(None, description="Aggregation operation"),
    timeseries: bool = Query(True, description="Generate timeseries"),
    smart_filter: bool = Query(False, alias="smart_filters", description="Apply smart filter"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
    mode: str | None = Query(
        None,
        description=(
            "Sentinel-1 acquisition mode (IW, EW, SM, WV). Only valid for sentinel-1-rtc."
        ),
    ),
):
    if not timeseries and operation is None:
        raise HTTPException(status_code=400, detail="Operation is required when timeseries=false")
    if operation and operation not in VALID_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operation '{operation}'. Choose from: {sorted(VALID_OPERATIONS)}",
        )

    bbox_coords = _parse_bbox(bbox)
    start_date, end_date = _validate_dates(start_date, end_date)
    bands_list = _validate_formula_request(collection, formula, bands)
    extra_query = _validate_mode(collection, mode)

    uid = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + str(uuid.uuid4())[:6]
    output_dir = os.path.join(STATIC_EXPORT_DIR, uid)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("export_started", uid=uid, collection=collection, operation=operation)

    background_tasks.add_task(
        _run_computation,
        bbox_coords,
        start_date,
        end_date,
        cloud_cover,
        formula,
        bands_list,
        operation,
        timeseries,
        output_dir,
        smart_filter,
        collection,
        uid,
        extra_query,
    )
    return JSONResponse(
        content={"message": f"Processing started in background: {output_dir}", "uid": uid},
        status_code=201,
    )


@app.get("/tile/{z}/{x}/{y}", tags=["tiles"])
@limiter.limit(RATE_LIMIT_TILE)
async def get_tile(
    request: Request,
    z: int,
    x: int,
    y: int,
    start_date: str = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(None, description="End date (YYYY-MM-DD)"),
    cloud_cover: int = Query(30, ge=0, le=100),
    bands: str = Query("red", description="Comma-separated band names referenced by the formula"),
    formula: str = Query("red", description="Band math formula using band names"),
    colormap_str: str = Query("RdYlGn", description="Colormap"),
    operation: str = Query("median", description="Aggregation operation"),
    timeseries: bool = Query(False, description="Analyze timeseries"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
    mode: str | None = Query(
        None,
        description=(
            "Sentinel-1 acquisition mode (IW, EW, SM, WV). Only valid for sentinel-1-rtc."
        ),
    ),
):
    if z < 10 or z > 23:
        raise HTTPException(status_code=400, detail="Zoom level must be between 10 and 23")

    bands_list = _validate_formula_request(collection, formula, bands)
    _validate_mode(collection, mode)

    if not start_date:
        start_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    try:
        start_time = time.time()
        tile_processor = TileProcessor()
        image_bytes, feature = await tile_processor.cached_generate_tile(
            x,
            y,
            z,
            start_date,
            end_date,
            cloud_cover,
            tuple(bands_list),
            formula,
            colormap_str,
            operation=operation,
            latest=(timeseries is False),
            collection=collection,
            mode=mode,
        )
        computation_time = time.time() - start_time

        headers = {
            "X-Computation-Time": str(computation_time),
            "X-Image-Date": feature["properties"]["datetime"],
            "Cache-Control": "no-store, no-cache, must-revalidate",
        }
        cloud_cover_value = feature["properties"].get("eo:cloud_cover")
        if cloud_cover_value is not None:
            headers["X-Cloud-Cover"] = str(cloud_cover_value)
        return Response(content=image_bytes, media_type="image/png", headers=headers)

    except Exception as exc:
        logger.exception("tile_computation_error", z=z, x=x, y=y, collection=collection)
        raise HTTPException(status_code=500, detail=f"Tile computation error: {exc!s}") from exc


@app.get("/export-tile/{uid}/{z}/{x}/{y}", tags=["tiles"])
@limiter.limit(RATE_LIMIT_TILE)
async def get_export_tile(
    request: Request,
    uid: str,
    z: int,
    x: int,
    y: int,
    colormap: str = Query("RdYlGn", description="Matplotlib colormap name"),
    vmin: float | None = Query(None, description="Global min value for normalization"),
    vmax: float | None = Query(None, description="Global max value for normalization"),
):
    """Serve a colored tile from a completed export GeoTIFF."""
    tif_path = _safe_uid_path(uid, "custom_band_output_aggregate.tif")
    if not os.path.exists(tif_path):
        raise HTTPException(status_code=404, detail="Export result not found")

    # If vmin/vmax not provided, read from metadata
    if vmin is None or vmax is None:
        metadata = await asyncio.to_thread(_read_export_metadata, tif_path)
        vmin = metadata["min"] if vmin is None else vmin
        vmax = metadata["max"] if vmax is None else vmax

    try:
        image_bytes = await asyncio.to_thread(
            _render_export_tile, tif_path, z, x, y, colormap, vmin, vmax
        )
        return Response(content=image_bytes, media_type="image/png")
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/export-tile/{uid}/metadata", tags=["tiles"])
async def get_export_tile_metadata(request: Request, uid: str):
    """Return bounds and min/max for a completed export GeoTIFF."""
    tif_path = _safe_uid_path(uid, "custom_band_output_aggregate.tif")
    if not os.path.exists(tif_path):
        raise HTTPException(status_code=404, detail="Export result not found")

    metadata = await asyncio.to_thread(_read_export_metadata, tif_path)
    return JSONResponse(content=metadata)


def _render_export_tile(
    tif_path: str, z: int, x: int, y: int, colormap: str, vmin: float, vmax: float
) -> bytes:
    """Read a tile from the export GeoTIFF and apply colormap using global min/max."""
    from io import BytesIO

    from rio_tiler.io import Reader

    with Reader(input=tif_path) as cog:
        img = cog.tile(x, y, z)

    mask = img.mask  # (height, width) 0=nodata, 255=valid

    if img.count == 1:
        # Single band - apply colormap with global min/max
        band_data = img.data[0].astype(float)
        nodata_mask = (mask == 0) | (band_data == -9999) | (~np.isfinite(band_data))

        if vmax == vmin:
            normalized = np.zeros_like(band_data)
        else:
            normalized = np.clip((band_data - vmin) / (vmax - vmin), 0, 1)

        # Map d3 colorscale names to matplotlib equivalents
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
        cmap_name = _CMAP_ALIASES.get(colormap, colormap)
        try:
            cmap = plt.get_cmap(cmap_name)
        except ValueError:
            cmap = plt.get_cmap("RdYlGn")
        colored = cmap(normalized)  # (h, w, 4) RGBA float 0-1
        rgba = (colored * 255).astype(np.uint8)
        rgba[nodata_mask] = [0, 0, 0, 0]  # transparent nodata
    else:
        # Multi-band (RGB) - use as-is
        rgb = img.data_as_image()[:, :, :3]
        alpha = mask.reshape(rgb.shape[0], rgb.shape[1], 1)
        rgba = np.concatenate([rgb, alpha], axis=2).astype(np.uint8)

    image = Image.fromarray(rgba, "RGBA")
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()


def _read_export_metadata(tif_path: str) -> dict:
    """Read bounds and statistics from the export GeoTIFF. Cached per path."""
    import rasterio as rio
    from rasterio.warp import transform_bounds

    with rio.open(tif_path) as src:
        bounds = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        data = src.read(1).astype(float)
        nodata = src.nodata
        # Mask out nodata, -9999, and non-finite values
        valid_mask = np.isfinite(data)
        if nodata is not None:
            valid_mask &= data != nodata
        valid_mask &= data != -9999
        valid = data[valid_mask]

        vmin = float(valid.min()) if valid.size > 0 else 0
        vmax = float(valid.max()) if valid.size > 0 else 1

    west, south, east, north = bounds
    return {
        "bounds": [[south, west], [north, east]],
        "min": vmin,
        "max": vmax,
    }


@app.get("/image-download", tags=["compute"])
@limiter.limit(RATE_LIMIT_EXPORT)
async def extract_raw_bands_as_image(
    request: Request,
    background_tasks: BackgroundTasks,
    bbox: str = Query(..., description="Bounding box: west,south,east,north"),
    start_date: str = Query(
        (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
        description="Start date (YYYY-MM-DD)",
    ),
    end_date: str = Query(
        datetime.now().strftime("%Y-%m-%d"),
        description="End date (YYYY-MM-DD)",
    ),
    cloud_cover: int = Query(30, ge=0, le=100, description="Cloud cover percentage"),
    bands_list: str = Query(
        "red,green,blue",
        description="Comma-separated bands to extract",
    ),
    smart_filter: bool = Query(False, alias="smart_filters", description="Apply smart filter"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
    mode: str | None = Query(
        None,
        description=(
            "Sentinel-1 acquisition mode (IW, EW, SM, WV). Only valid for sentinel-1-rtc."
        ),
    ),
):
    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    extra_query = _validate_mode(collection, mode)

    invalid = config.validate_bands(bands_list.split(","))
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid bands: {', '.join(invalid)}. Not found in {collection}",
        )

    bbox_coords = _parse_bbox(bbox)

    uid = datetime.now().strftime("%Y%m%d%H%M%S") + "_" + str(uuid.uuid4())[:8]
    output_dir = os.path.join(STATIC_EXPORT_DIR, uid)
    os.makedirs(output_dir, exist_ok=True)

    logger.info("image_download_started", uid=uid, collection=collection)

    background_tasks.add_task(
        _run_image_download,
        bbox_coords,
        start_date,
        end_date,
        cloud_cover,
        bands_list.split(","),
        output_dir,
        smart_filter,
        collection,
        uid,
        extra_query,
    )
    return JSONResponse(
        content={
            "message": f"Raw band extraction started in background: {output_dir}",
            "uid": uid,
        }
    )


# endregion

# region Background tasks


async def _run_computation(
    bbox: list[float],
    start_date: str,
    end_date: str,
    cloud_cover: int,
    formula: str,
    bands: list[str],
    operation: str | None,
    timeseries: bool,
    output_dir: str,
    smart_filter: bool,
    collection: str,
    uid: str,
    extra_query: dict[str, Any] | None = None,
) -> None:
    log_file_path = os.path.join(output_dir, "runtime.log")

    def _sync_compute() -> None:
        with open(log_file_path, "w") as f:
            console = Console(file=f)
            console.print("Starting processing...")
            try:
                processor = VirtughanProcessor(
                    bbox=bbox,
                    start_date=start_date,
                    end_date=end_date,
                    cloud_cover=cloud_cover,
                    formula=formula,
                    bands=bands,
                    operation=operation,
                    timeseries=timeseries,
                    output_dir=output_dir,
                    log_file=f,
                    smart_filter=smart_filter,
                    collection=collection,
                    extra_query=extra_query,
                )
                processor.compute()
                console.print(f"Processing completed. Results saved in {output_dir}")
            except Exception as exc:
                console.print(f"Error processing: {exc}")
                raise

    try:
        await asyncio.to_thread(_sync_compute)
        logger.info("export_completed", uid=uid)
    except Exception:
        logger.exception("export_failed", uid=uid)


async def _run_image_download(
    bbox: list[float],
    start_date: str,
    end_date: str,
    cloud_cover: int,
    bands_list: list[str],
    output_dir: str,
    smart_filter: bool,
    collection: str,
    uid: str,
    extra_query: dict[str, Any] | None = None,
) -> None:
    log_file_path = os.path.join(output_dir, "runtime.log")

    def _sync_extract() -> None:
        with open(log_file_path, "w") as f:
            console = Console(file=f)
            console.print("Starting raw band extraction...")
            try:
                processor = ExtractProcessor(
                    bbox=bbox,
                    start_date=start_date,
                    end_date=end_date,
                    cloud_cover=cloud_cover,
                    bands_list=bands_list,
                    output_dir=output_dir,
                    log_file=f,
                    zip_output=True,
                    smart_filter=smart_filter,
                    collection=collection,
                    extra_query=extra_query,
                )
                processor.extract()
                console.print(f"Raw band extraction completed. Results saved in {output_dir}")
            except Exception as exc:
                console.print(f"Error during raw band extraction: {exc}")
                raise

    try:
        await asyncio.to_thread(_sync_extract)
        logger.info("image_download_completed", uid=uid)
    except Exception:
        logger.exception("image_download_failed", uid=uid)


async def _cleanup_expired_folders() -> None:
    while True:
        try:
            os.makedirs(STATIC_EXPORT_DIR, exist_ok=True)
            now = datetime.now()
            for folder_name in os.listdir(STATIC_EXPORT_DIR):
                folder_path = os.path.join(STATIC_EXPORT_DIR, folder_name)
                if not os.path.isdir(folder_path):
                    continue
                try:
                    timestamp_str = folder_name.split("_")[0]
                    folder_time = datetime.strptime(timestamp_str, "%Y%m%d%H%M%S")
                    if now - folder_time > EXPIRY_DURATION:
                        shutil.rmtree(folder_path)
                        logger.info("expired_folder_deleted", folder=folder_name)
                except (ValueError, IndexError):
                    continue
        except Exception:
            logger.exception("cleanup_error")
        await asyncio.sleep(3600)


# endregion
