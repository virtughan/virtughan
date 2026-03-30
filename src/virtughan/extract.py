import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.warp import reproject
from rasterio.windows import from_bounds
from tqdm import tqdm

from .utils import (
    filter_intersected_features,
    remove_overlapping_sentinel2_tiles,
    search_stac_api,
    smart_filter_images,
    zip_files,
)

VALID_BANDS = {
    "red": "Red - 10m",
    "green": "Green - 10m",
    "blue": "Blue - 10m",
    "nir": "NIR 1 - 10m",
    "swir22": "SWIR 2.2μm - 20m",
    "rededge2": "Red Edge 2 - 20m",
    "rededge3": "Red Edge 3 - 20m",
    "rededge1": "Red Edge 1 - 20m",
    "swir16": "SWIR 1.6μm - 20m",
    "wvp": "Water Vapour (WVP)",
    "nir08": "NIR 2 - 20m",
    "aot": "Aerosol optical thickness (AOT)",
    "coastal": "Coastal - 60m",
    "nir09": "NIR 3 - 60m",
}


class ExtractProcessor:
    """
    Processor for extracting and saving bands from satellite images.
    """

    def __init__(
        self,
        bbox,
        start_date,
        end_date,
        cloud_cover,
        bands_list,
        output_dir,
        log_file=sys.stdout,
        workers=1,
        zip_output=False,
        smart_filter=True,
    ):
        """
        Initialize the ExtractProcessor.

        Parameters:
        bbox (list): Bounding box coordinates [min_lon, min_lat, max_lon, max_lat].
        start_date (str): Start date for the data extraction (YYYY-MM-DD).
        end_date (str): End date for the data extraction (YYYY-MM-DD).
        cloud_cover (int): Maximum allowed cloud cover percentage.
        bands_list (list): List of bands to extract.
        output_dir (str): Directory to save the extracted bands.
        log_file (file): File to log the extraction process.
        workers (int): Number of parallel workers.
        zip_output (bool): Whether to zip the output files.
        smart_filter (bool): Whether to apply smart filtering to the images.
        """
        self.bbox = bbox
        self.start_date = start_date
        self.end_date = end_date
        self.cloud_cover = cloud_cover
        self.bands_list = bands_list
        self.output_dir = output_dir
        self.log_file = log_file
        self.workers = workers
        self.zip_output = zip_output
        self.crs = None
        self.transform = None
        self.use_smart_filter = smart_filter

        self._validate_bands_list()

    def _validate_bands_list(self):
        """
        Validate the list of bands to ensure they are valid.
        """
        invalid_bands = [band for band in self.bands_list if band not in VALID_BANDS]
        if invalid_bands:
            raise ValueError(
                f"Invalid band names: {', '.join(invalid_bands)}. "
                f"Band names should be one of: {', '.join(VALID_BANDS.keys())}"
            )

    def _transform_bbox(self, crs):
        """
        Transform the bounding box coordinates to the specified CRS.

        Parameters:
        crs (str): Coordinate reference system to transform to.

        Returns:
        tuple: Transformed bounding box coordinates (min_x, min_y, max_x, max_y).
        """
        transformer = Transformer.from_crs("epsg:4326", crs, always_xy=True)
        min_x, min_y = transformer.transform(self.bbox[0], self.bbox[1])
        max_x, max_y = transformer.transform(self.bbox[2], self.bbox[3])
        return min_x, min_y, max_x, max_y

    def _calculate_window(self, cog, min_x, min_y, max_x, max_y):
        """
        Calculate the window for reading the data from the COG.

        Parameters:
        cog (rasterio.io.DatasetReader): COG dataset reader.
        min_x (float): Minimum x-coordinate.
        min_y (float): Minimum y-coordinate.
        max_x (float): Maximum x-coordinate.
        max_y (float): Maximum y-coordinate.

        Returns:
        rasterio.windows.Window: Window for reading the data.
        """
        return from_bounds(min_x, min_y, max_x, max_y, cog.transform)

    def _is_window_out_of_bounds(self, window):
        """
        Check if the window is out of bounds.

        Parameters:
        window (rasterio.windows.Window): Window to check.

        Returns:
        bool: True if the window is out of bounds, False otherwise.
        """
        return (
            window.col_off < 0
            or window.row_off < 0
            or window.width <= 0
            or window.height <= 0
        )

    def _get_band_urls(self, features):
        """
        Get the URLs of the bands to be extracted.

        Parameters:
        features (list): List of features containing the band URLs.

        Returns:
        list: List of band URLs.
        """
        band_urls = [
            [feature["assets"][band]["href"] for band in self.bands_list]
            for feature in features
        ]
        return band_urls

    def _fetch_and_save_bands(self, band_urls, feature_id):
        """
        Fetch and save the bands from the given URLs.

        Parameters:
        band_urls (list): List of band URLs.
        feature_id (str): Feature ID for naming the output file.

        Returns:
        str: Path to the saved GeoTIFF file.
        """
        try:
            band_records = []
            bands_meta = []

            for band_url in band_urls:
                with rasterio.open(band_url) as band_cog:
                    min_x, min_y, max_x, max_y = self._transform_bbox(band_cog.crs)
                    band_window = self._calculate_window(
                        band_cog, min_x, min_y, max_x, max_y
                    )

                    if self._is_window_out_of_bounds(band_window):
                        return None

                    band_data = band_cog.read(1, window=band_window).astype(float)
                    band_window_transform = band_cog.window_transform(band_window)

                    band_records.append(
                        {
                            "data": band_data,
                            "crs": band_cog.crs,
                            "transform": band_window_transform,
                            "resolution": band_cog.res,
                        }
                    )
                    bands_meta.append(band_url.split("/")[-1].split(".")[0])

            if not band_records:
                return None

            # Use the coarsest input band as the reference grid so all exported bands share
            # one geospatial transform and align correctly.
            reference_record = max(
                band_records,
                key=lambda rec: rec["resolution"][0] * rec["resolution"][1],
            )

            self.crs = reference_record["crs"]
            self.transform = reference_record["transform"]
            reference_shape = reference_record["data"].shape

            bands = []
            for record in band_records:
                if (
                    record["data"].shape == reference_shape
                    and record["crs"] == self.crs
                    and record["transform"] == self.transform
                ):
                    bands.append(record["data"])
                else:
                    destination = np.empty(reference_shape, dtype=record["data"].dtype)
                    reproject(
                        source=record["data"],
                        destination=destination,
                        src_transform=record["transform"],
                        src_crs=record["crs"],
                        dst_transform=self.transform,
                        dst_crs=self.crs,
                        resampling=Resampling.average,
                    )
                    bands.append(destination)

            print("Stacking Bands...")
            stacked_bands = np.stack(bands)
            output_file = os.path.join(
                self.output_dir, f"{feature_id}_bands_export.tif"
            )
            self._save_geotiff(stacked_bands, output_file, bands_meta)
            return output_file
        except Exception as ex:
            print(f"Error fetching bands: {ex}")
            raise ex
            return None

    def _save_geotiff(self, bands, output_file, bands_meta=None):
        """
        Save the bands as a GeoTIFF file.

        Parameters:
        bands (numpy.ndarray): Array of bands to save.
        output_file (str): Path to the output file.
        bands_meta (list): List of metadata for the bands.
        """

        band_shape = bands.shape
        nodata_value = -9999
        bands = np.where(np.isnan(bands), nodata_value, bands)
        with rasterio.open(
            output_file,
            "w",
            driver="GTiff",
            height=bands.shape[1],
            width=bands.shape[2],
            count=len(bands),
            dtype=bands.dtype,
            crs=self.crs,
            transform=self.transform,
            nodata=nodata_value,
        ) as dst:
            for band in range(1, band_shape[0] + 1):
                dst.write(bands[band - 1], band)
                if bands_meta:
                    dst.set_band_description(band, bands_meta[band - 1])

    def extract(self):
        """
        Extract the bands from the satellite images and save them as GeoTIFF files.
        """
        print("Extracting bands...")
        os.makedirs(self.output_dir, exist_ok=True)

        features = search_stac_api(
            self.bbox,
            self.start_date,
            self.end_date,
            self.cloud_cover,
        )
        print(f"Total scenes found: {len(features)}")
        filtered_features = filter_intersected_features(features, self.bbox)
        print(f"Scenes covering input area: {len(filtered_features)}")
        overlapping_features_removed = remove_overlapping_sentinel2_tiles(
            filtered_features
        )
        print(f"Scenes after removing overlaps: {len(overlapping_features_removed)}")
        if self.use_smart_filter:
            overlapping_features_removed = smart_filter_images(
                overlapping_features_removed, self.start_date, self.end_date
            )
            print(
                f"Scenes after applying smart filter: {len(overlapping_features_removed)}"
            )

        band_urls_list = self._get_band_urls(overlapping_features_removed)
        result_lists = []
        if self.workers > 1:
            print("Using Parallel Processing...")
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                futures = [
                    executor.submit(
                        self._fetch_and_save_bands, band_urls, feature["id"]
                    )
                    for band_urls, feature in zip(
                        band_urls_list, overlapping_features_removed
                    )
                ]
                for future in tqdm(
                    as_completed(futures),
                    total=len(futures),
                    desc="Extracting Bands",
                    file=self.log_file,
                ):
                    result = future.result()
                    result_lists.append(result)
        else:
            for band_urls, feature in tqdm(
                zip(band_urls_list, overlapping_features_removed),
                total=len(band_urls_list),
                desc="Extracting Bands",
                file=self.log_file,
            ):
                result = self._fetch_and_save_bands(band_urls, feature["id"])
                result_lists.append(result)
        if self.zip_output:
            zip_files(
                result_lists,
                os.path.join(self.output_dir, "tiff_files.zip"),
            )


if __name__ == "__main__":
    # Example usage
    bbox = [83.84765625, 28.22697003891833, 83.935546875, 28.304380682962773]
    start_date = "2024-12-15"
    end_date = "2024-12-31"
    cloud_cover = 30
    bands_list = ["red", "nir", "green"]
    output_dir = "./extracted_bands"
    workers = 1  # Number of parallel workers
    os.makedirs(output_dir, exist_ok=True)

    extractor = ExtractProcessor(
        bbox,
        start_date,
        end_date,
        cloud_cover,
        bands_list,
        output_dir,
        workers=workers,
    )
    extractor.extract()
