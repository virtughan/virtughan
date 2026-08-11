# virtughan 1.1.1

Sentinel-1 compatibility patch.

## Fixes

- Smart filtering now supports collections without a cloud-cover property, so Sentinel-1 works with the Python package defaults.
- Sentinel-1 tile responses no longer require an `eo:cloud_cover` field.
- Empty smart-filter inputs now return an empty result instead of raising an indexing error.
- The FastAPI metadata version now matches the package version.

## Improvements

- Sentinel-1 acquisition-mode filtering is available consistently from `/search`, `/export`, `/tile`, and `/image-download`.
- Raw-band extraction accepts generic STAC field filters through `extra_query`.
- Added regression coverage for Sentinel-1 collection metadata, formulas, smart filtering, and API tile responses.

# virtughan 1.1.0

JOSS submission release. Highlights since 1.0.2.

## New features

- **Sentinel-1 RTC support** via Planetary Computer. Polarization bands (`vv`, `vh`, `hh`, `hv`), terrain-corrected gamma0, free public HTTPS access. New `mode` query parameter on `/export` and `/tile` for filtering by acquisition mode (`IW`, `EW`, `SM`, `WV`).
- **N-band engine and formula validator.** `bands` parameter accepts an arbitrary list of band names. Formulas can reference any subset of the supplied bands by name (e.g. `(nir - red) / (nir + red)`, `10 * log10(vv / vh)`). Validation rejects unknown band names, unused bands, syntax errors, and forbidden expressions before any data is fetched.
- **Generic STAC field filters.** New `extra_query` plumbing through `VirtughanProcessor` and `TileProcessor` enables collection-specific server-side filters (initial use case: `sar:instrument_mode` for S1).
- **Frontend additions.** Map tools (export map, measure, upload temporary layer, point tools). Band info modal showing wavelength, pixel size, and band number. Default formula presets for NDBI, SAVI, EVI, and others.
- **Larger AOI ceiling.** Compute and download limits raised to 5000 sq km.

## Improvements

- **Robust visualization normalization.** PNG outputs and the per-scene GIF now use p2/p98 percentile clipping with real physical-unit colorbar labels. Removes the min/max-stretch artifact that crushed meaningful SAR and optical ranges when scenes contained layover, cloud shadow, or saturated pixels.
- **Smart filter cadence retuned for Landsat.** First-window broadened from one month to three months; weekly cadence broadened to two-week intervals. Sentinel-2 cadence unchanged.
- **Tile parser contract extended.** Parsers now receive the full STAC feature dict, so collection-specific keys (e.g., S1 ascending vs descending orbit state) can participate in dedup and latest-per-grid filtering.
- **Tile UX.** Loading spinner persists to last tile. Export PNG/PDF warns while tiles are still loading. Tile layer order fixed; legend now horizontal with title.

## Bug fixes

- Tile loading no longer continues after a layer is turned off or reset.
- Tile not rendering at certain zoom levels due to vmin/vmax issues fixed.
- Tile layer visibility in the layer list at low zoom levels fixed.
- Color palette application to map and legend orientation fixes.
- GeoTIFF transform now correct for clipped bounding boxes.
- Compute progress no longer shown after visualizing existing tiles.

## CI / tooling

- `ty` static type checking added to `pre-commit` hooks.
- Documentation now builds on pull requests.
- Per-file `ty` overrides extended to `API.py` for upstream-library typing gaps.

## Paper

- Sudmanns reference updated to final 2020 publication metadata (vol 13, issue 7, pp 832-850).
- Disputed citation on data cube pre-aggregation removed.
- Newer development (Kröber et al. 2025) cited for context.
- Acknowledgments cleaned (academic titles removed per author request).
