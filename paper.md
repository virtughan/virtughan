---
title: "virtughan: A Virtual Computation Cube for EO Data Using On-the-Fly Tiling Computation"
tags:
  - geospatial
  - data cube
  - STAC
  - COG
  - Python
authors:
  - name: "Kshitij Raj Sharma"
    affiliation: 1
  - name: "Upendra Oli"
    affiliation: 1
affiliations:
  - name: "Paris Lodron University of Salzburg, Austria"
    index: 1
date: "2025-02-08"
bibliography: paper.bib
---

# Summary

**virtughan** is a Python-based geospatial data pipeline designed for on-the-fly computations on raster tiles. By leveraging Cloud-Optimized GeoTIFFs (COGs) and SpatioTemporal Asset Catalog (STAC) endpoints [@stacspec, @cogeo], virtughan enables on-demand data processing across multiple zoom levels and time dimensions. virtughan focuses on on-demand tile computation, dynamically computing results as needed while minimizing data transfers and infrastructure overhead for entire scenes [@rio-tiler; @mercantile]. This cost-effective approach ensures that only the necessary tiles (i.e., bounding boxes of interest) are retrieved, with computations applied directly during data access [@sentinel2cogs]. The framework supports user-defined band math, multi-temporal analyses, and partial reads from Cloud-Optimized Sentinel-2 data, along with a caching mechanism to optimize repeated requests [@fastapi]. The architecture is conceptually similar to existing STAC/COG tile services such as TiTiler [@titiler], but virtughan emphasizes the integration of STAC querying, tile-level computation, temporal aggregation, overlap filtering, and AOI export within a lightweight Python workflow. Ultimately, virtughan provides an open-source framework for lightweight EO visualization and analysis. Rather than replacing EO data cubes, virtughan is intended to complement them in workflows where users need dynamic access to derived EO products without downloading complete scenes. This lightweight approach makes the satellite imagery processing more accessible for researchers, analysts, and developers.

# Statement of Need

Big Earth Data, with its high-resolution, multi-temporal satellite imagery, poses growing challenges for storage and real-time processing, often exceeding traditional workflows' capacities [@Sudmanns:2019]. As EO data volumes expand, efficient management strategies are needed to address rising computational and storage demands. Data cubes have emerged as a structured approach to managing large-scale EO datasets, facilitating efficient data access and analysis through precomputed storage architectures [@Giuliani:2019]. However, data cubes often store pre-aggregated or processed data layers, which can lead to increased storage requirements and may not support frequent or dynamic data updates effectively. This approach can result in inefficiencies, as the storage of multiple processed layers extends the storage burden. Additionally, pre-computation is done on entire images rather than individual tiles, storing pre-aggregated layers for later analysis [@Sudmanns:2019]. This approach improves query efficiency but also increases memory usage and computational load, potentially allocating resources to areas that may not always be relevant. While cloud-based EO platforms like Google Earth Engine offer scalable solutions, they require significant infrastructure, limiting accessibility. Also, Downloading images within a user's area of interest is often time-consuming, as platforms like Copernicus Browser typically require downloading the entire image.

The architecture of virtughan is conceptually similar to existing STAC/COG tile services such as TiTiler [@titiler], but it emphasizes the integration of STAC querying, temporal aggregation, overlap filtering, and AOI export within a lightweight Python workflow. To address the challenges of storage and precomputation in EO analysis, virtughan retrieves and computes only the image tiles required for a requested area of interest. By performing computations on demand rather than storing precomputed products for complete scenes, it reduces storage needs and computational overhead while enabling efficient processing across multiple zoom levels. Consequently, virtughan provides a lightweight and cost-effective framework that complements traditional EO data cubes and cloud-based processing platforms in workflows requiring dynamic access to derived EO products.

## Implementation

### Tile Requests and Partial Reads

A user or front-end requests map tiles via `(z, x, y)` coordinates (along with an optional date/time range and custom band math). Using mercantile’s approach[@mercantile], virtughan determines the tile’s bounding box. It then queries Sentinel-2 STAC metadata to identify scenes covering that region. Via the Cloud-Optimized GeoTIFF specification [@sentinel2cogs], windowed reads fetch only the portion of the image corresponding to the requested tile [@rio-tiler].

### On-the-Fly Computation

Once partial reads are loaded, virtughan applies user-defined formulas or filters (e.g., NDVI, cloud masking) per pixel. Because all computations occur at tile-creation time, the framework can flexibly incorporate new formulas or data corrections without reprocessing entire scenes. For requests spanning multiple acquisition dates, intersecting scenes are filtered and aggregated using the selected reduction method (e.g., median, max, or min). For requests involving bands with different native spatial resolutions, virtughan resamples bands to a common grid before computation. The current implementation does not perform radiometric harmonization between overlapping scenes acquired at different dates.

### Tiling and Caching

Tile requests are handled using the standard Web Mercator tile matrix (z, x, y). The processed tiles (e.g., PNG or JPEG) can be cached. If an identical tile request recurs, virtughan serves it directly from the cache; improving performance and lowering bandwidth usage. As zoom levels shift, the system adjusts how the partial reads are resampled, ensuring minimal repeated data access. The current implementation uses a local in-memory cache maintained separately for each running process.

### Download Images within Area of Interest

virtughan allows the users to download the images within their area of interest instead of downloading the whole image. The area of interest can be a polygon, rectangle, or a map window. The original level-2A images can be downloaded by filtering bands, date, and cloud cover. If multiple images fall within the selected time range and area, all relevant images captured at different time are retrieved. These downloaded images can further be visualized and analyzed using tools like QGIS and other geospatial applications.

# Performance Comparison

To illustrate the practical differences between workflows, we compared virtughan with the Sentinel Image Downloader QGIS plugin for generating Sentinel-2 indices (e.g., NDWI) for selected Areas of Interest (AOI).

| Area of Interest  | Virtughan (s) | Sentinel Downloader (s) |
| :---------------- | :-----------: | :---------------------: |
| Fewa Lake, Nepal  |      84       |          1283           |
| Kathmandu, Nepal  |      219      |          1744           |
| Salzburg, Austria |      50       |           559           |

_Table 1: Workflow time required to obtain a visualizable EO product for each AOI. Virtughan computes tiles on-the-fly, whereas the traditional approach requires downloading full scenes._

This comparison should be interpreted as a workflow-level comparison rather than a direct computational benchmark. The Sentinel Image Downloader workflow includes full-scene transfer, local storage, and processing within QGIS before the requested index can be visualized. In contrast, virtughan retrieves and processes only the data required for the selected area.

For AOIs located in scene overlaps (e.g., Fewa Lake), the Sentinel Image Downloader workflow required downloading multiple overlapping Sentinel-2 scenes, which further increased transfer and processing time. In contrast, virtughan processed only the required image data for the requested area.

The evaluation was performed on a system with an AMD Ryzen 9 5900HX processor (3.30 GHz), 32 GB RAM, Windows 11, and a 15 Mbps internet connection. The reported measurements exclude authentication time (e.g., CDSE login) for the Sentinel Image Downloader workflow and polygon extraction time for both workflows. For virtughan, the values reported in Table 1 correspond to the single-worker runs used during testing. Using four workers reduced the processing time for the Fewa Lake AOI from 84 s to 64 s.

# Figures

![Performance Comparison](comparison.png)

![Flowchart-virtughan](flowchart-virtughan.png)

# Application Areas

virtughan enables on-the-fly geospatial data processing for various Earth observation applications. It helps monitor environmental changes like deforestation, glacial lake expansion, urban heat islands, and wildfires without requiring extensive data storage. In disaster response, it provides rapid analysis of floods, landslides, cyclones, and earthquakes. Urban planners can analyze land use, infrastructure growth, and air quality. AI integration on virtughan obtained datasets can support automated land classification, object detection, and biodiversity tracking. It also aids security efforts, including border monitoring and conflict damage assessment. As an open-source platform, virtughan enhances accessibility for citizen science, environmental advocacy, and academic research.

## Future Directions

virtughan already enables users to retrieve and process only the necessary image tiles on demand, reducing storage and computational overhead. To further enhance its capabilities, several key improvements are planned, enabling virtughan to integrate more data sources, and support advanced analytics while maintaining its lightweight framework.

- **Mosaicking**: Automating multi-scene merges for larger coverage areas.
- **Additional Sensors**: Adding Landsat, MODIS, and commercial satellite data.
- **Plugins and ML Integration**: A QGIS plugin has been developed to support AOI selection, temporal filtering, and custom band calculations. Future work will extend it with additional sensors, machine-learning inference and advanced band math.
- **Distributed Caching**: Supporting scalable deployments for high-traffic or cluster-based environments.

These future developments will increase virtughan’s flexibility, efficiency, and usability, making Earth observation data processing more accessible across a wider range of applications.

# Acknowledgments

We extend our gratitude to the maintainers of foundational GIS libraries such as Rasterio [@rasterio], rio-tiler [@rio-tiler], Mercantile [@mercantile], and FastAPI [@fastapi]. Additionally, we are grateful to our colleagues and mentors at the Copernicus Masters in Digital Earth program, co-funded by the European Union and hosted at Paris Lodron University of Salzburg, for their valuable insights and support. A special thanks to Professor Dirk Tiede and Dr. Martin Sudmanns for their guidance on existing data cube methodologies.

# References
