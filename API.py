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
import structlog
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from rich.console import Console
from shapely.geometry import box, mapping
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.status import HTTP_504_GATEWAY_TIMEOUT

from src.virtughan.collections import COLLECTIONS, get_collection
from src.virtughan.engine import VirtughanProcessor
from src.virtughan.extract import ExtractProcessor
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


def _validate_collection_bands(collection: str, band1: str, band2: str | None = None) -> None:
    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if config.validate_bands([band1]):
        raise HTTPException(
            status_code=400,
            detail=f"Band '{band1}' not found in {collection}",
        )
    if band2:
        if config.validate_bands([band2]):
            raise HTTPException(
                status_code=400,
                detail=f"Band '{band2}' not found in {collection}",
            )
        if band1 != band2:
            b1_res = config.bands[band1].resolution
            b2_res = config.bands[band2].resolution
            if b1_res != b2_res:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Resolution mismatch: '{band1}' ({b1_res}m) vs '{band2}' ({b2_res}m)"
                    ),
                )


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
        "Sentinel-2 and Landsat collections via STAC APIs."
    ),
    version="1.0.1",
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
                band_name: {"resolution": band.resolution, "common_name": band.common_name}
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
        band_name: {"resolution": band.resolution, "common_name": band.common_name}
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
):
    bbox_coords = _parse_bbox(bbox)
    start_date, end_date = _validate_dates(start_date, end_date)

    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    west, south, east, north = bbox_coords
    bbox_geojson = mapping(box(west, south, east, north))

    response = await search_stac_async(config, bbox_geojson, start_date, end_date, cloud_cover)
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
        "(band2 - band1) / (band2 + band1)",
        description="Band math formula (default: NDVI)",
    ),
    band1: str = Query("red", description="First band"),
    band2: str = Query("nir", description="Second band"),
    operation: str = Query(None, description="Aggregation operation"),
    timeseries: bool = Query(True, description="Generate timeseries"),
    smart_filter: bool = Query(False, alias="smart_filters", description="Apply smart filter"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
):
    if not timeseries and operation is None:
        raise HTTPException(status_code=400, detail="Operation is required when timeseries=false")
    if band1 is None:
        raise HTTPException(status_code=400, detail="band1 is required")
    if operation and operation not in VALID_OPERATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid operation '{operation}'. Choose from: {sorted(VALID_OPERATIONS)}",
        )

    bbox_coords = _parse_bbox(bbox)
    start_date, end_date = _validate_dates(start_date, end_date)
    _validate_collection_bands(collection, band1, band2)

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
        band1,
        band2,
        operation,
        timeseries,
        output_dir,
        smart_filter,
        collection,
        uid,
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
    band1: str = Query("red", description="First band"),
    band2: str | None = Query(None, description="Second band"),
    formula: str = Query("band1", description="Band math formula"),
    colormap_str: str = Query("RdYlGn", description="Colormap"),
    operation: str = Query("median", description="Aggregation operation"),
    timeseries: bool = Query(False, description="Analyze timeseries"),
    collection: str = Query("sentinel-2-l2a", description="Satellite collection"),
):
    if z < 10 or z > 23:
        raise HTTPException(status_code=400, detail="Zoom level must be between 10 and 23")
    if band1 is None:
        raise HTTPException(status_code=400, detail="band1 is required")

    _validate_collection_bands(collection, band1, band2)

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
            band1,
            band2,
            formula,
            colormap_str,
            operation=operation,
            latest=(timeseries is False),
            collection=collection,
        )
        computation_time = time.time() - start_time

        headers = {
            "X-Computation-Time": str(computation_time),
            "X-Image-Date": feature["properties"]["datetime"],
            "X-Cloud-Cover": str(feature["properties"]["eo:cloud_cover"]),
            "Cache-Control": "public, max-age=3600",
        }
        return Response(content=image_bytes, media_type="image/png", headers=headers)

    except Exception as exc:
        logger.exception("tile_computation_error", z=z, x=x, y=y, collection=collection)
        raise HTTPException(status_code=500, detail=f"Tile computation error: {exc!s}") from exc


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
):
    try:
        config = get_collection(collection)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
    band1: str,
    band2: str,
    operation: str | None,
    timeseries: bool,
    output_dir: str,
    smart_filter: bool,
    collection: str,
    uid: str,
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
                    band1=band1,
                    band2=band2,
                    operation=operation,
                    timeseries=timeseries,
                    output_dir=output_dir,
                    log_file=f,
                    smart_filter=smart_filter,
                    collection=collection,
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
