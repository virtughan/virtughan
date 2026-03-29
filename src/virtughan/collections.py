from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


def _parse_sentinel2_tile_id(item_id: str) -> tuple[str, str]:
    parts = item_id.split("_")
    zone = parts[1][:2]
    date = parts[2]
    return zone, date


def _parse_landsat_tile_id(item_id: str) -> tuple[str, str]:
    parts = item_id.split("_")
    path_row = parts[2]
    date = parts[3]
    return path_row, date


@dataclass(frozen=True)
class BandInfo:
    asset_key: str
    common_name: str
    resolution: int


@dataclass(frozen=True)
class CollectionConfig:
    collection_id: str
    catalog_url: str
    bands: dict[str, BandInfo]
    cloud_cover_property: str | None
    tile_id_parser: Callable[[str], tuple[str, str]]
    url_signer: Callable[[str], str] | None = None
    stac_query_fields: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def band_names(self) -> list[str]:
        return list(self.bands.keys())

    def validate_bands(self, requested_bands: list[str]) -> list[str]:
        return [b for b in requested_bands if b not in self.bands]


EARTH_SEARCH_URL = "https://earth-search.aws.element84.com/v1"
PLANETARY_COMPUTER_URL = "https://planetarycomputer.microsoft.com/api/stac/v1"

SENTINEL2_BANDS = {
    "red": BandInfo("red", "red", 10),
    "green": BandInfo("green", "green", 10),
    "blue": BandInfo("blue", "blue", 10),
    "nir": BandInfo("nir", "nir", 10),
    "swir22": BandInfo("swir22", "swir22", 20),
    "rededge2": BandInfo("rededge2", "rededge", 20),
    "rededge3": BandInfo("rededge3", "rededge", 20),
    "rededge1": BandInfo("rededge1", "rededge", 20),
    "swir16": BandInfo("swir16", "swir16", 20),
    "wvp": BandInfo("wvp", "wvp", 20),
    "nir08": BandInfo("nir08", "nir08", 20),
    "aot": BandInfo("aot", "aot", 20),
    "coastal": BandInfo("coastal", "coastal", 60),
    "nir09": BandInfo("nir09", "nir09", 60),
    "scl": BandInfo("scl", "scl", 20),
    "visual": BandInfo("visual", "visual", 10),
}

LANDSAT_BANDS = {
    "red": BandInfo("red", "red", 30),
    "green": BandInfo("green", "green", 30),
    "blue": BandInfo("blue", "blue", 30),
    "nir08": BandInfo("nir08", "nir08", 30),
    "swir16": BandInfo("swir16", "swir16", 30),
    "swir22": BandInfo("swir22", "swir22", 30),
    "coastal": BandInfo("coastal", "coastal", 30),
    "lwir11": BandInfo("lwir11", "lwir11", 100),
}


def _sign_planetary_computer_url(url: str) -> str:
    import planetary_computer

    return planetary_computer.sign_url(url)


COLLECTIONS: dict[str, CollectionConfig] = {
    "sentinel-2-l2a": CollectionConfig(
        collection_id="sentinel-2-l2a",
        catalog_url=EARTH_SEARCH_URL,
        bands=SENTINEL2_BANDS,
        cloud_cover_property="eo:cloud_cover",
        tile_id_parser=_parse_sentinel2_tile_id,
    ),
    "landsat-c2-l2": CollectionConfig(
        collection_id="landsat-c2-l2",
        catalog_url=PLANETARY_COMPUTER_URL,
        bands=LANDSAT_BANDS,
        cloud_cover_property="eo:cloud_cover",
        tile_id_parser=_parse_landsat_tile_id,
        url_signer=_sign_planetary_computer_url,
    ),
}


def get_collection(name: str) -> CollectionConfig:
    if name not in COLLECTIONS:
        available = ", ".join(COLLECTIONS.keys())
        raise ValueError(f"Unknown collection '{name}'. Available: {available}")
    return COLLECTIONS[name]
