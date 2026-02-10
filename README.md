# virtughan

<img src="https://github.com/user-attachments/assets/e7ba177c-cd5e-453c-9790-679d7f83e5a7" alt="virtughan Logo" width="100" height="100"> 

![Tests Passing](https://img.shields.io/badge/tests-passing-brightgreen)
![Build Status](https://img.shields.io/github/actions/workflow/status/virtughan/virtughan/tests.yml?branch=master)
![Website Status](https://img.shields.io/website-up-down-green-red/https/virtughan.com)
![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=flat&logo=fastapi)
![PyPI Version](https://img.shields.io/pypi/v/virtughan)
![Python Version](https://img.shields.io/pypi/pyversions/virtughan)
![License](https://img.shields.io/github/license/virtughan/virtughan)
![Dependencies](https://img.shields.io/librariesio/release/pypi/virtughan)
![Last Commit](https://img.shields.io/github/last-commit/virtughan/virtughan)

 Name is combination of two words `virtual` & `cube` , where `cube` translated to Nepali word `घन`,  also known as virtual computation cube.

**Demo** : https://virtughan.com/ 


### Install 

As a python package : 

https://pypi.org/project/virtughan/ 

```bash
pip install virtughan
```

### Basic Usage 

Follow Notebook [Here](https://github.com/virtughan/virtughan/blob/master/docs/examples/usage.ipynb)


### Background

We started initially by looking at how Google Earth Engine (GEE) computes results on-the-fly at different zoom levels on large-scale Earth observation datasets. We were fascinated by the approach and felt an urge to replicate something similar on our own in an open-source manner. We knew Google uses their own kind of tiling, so we started from there.

Initially, we faced a challenge – how could we generate tiles and compute at the same time without pre-computing the whole dataset? Pre-computation would lead to larger processed data sizes, which we didn’t want. And so, the exploration began and the concept of on the fly tiling computation introduced 

At university, we were introduced to the concept of data cubes and the advantages of having a time dimension and semantic layers in the data. It seemed fascinating, despite the challenge of maintaining terabytes of satellite imagery. We thought – maybe we could achieve something similar by developing an approach where one doesn’t need to replicate data but can still build a data cube with semantic layers and computation. This raised another challenge – how to make it work? And hence come the virtual data cube

We started converting Sentinel-2 images to Cloud Optimized GeoTIFFs (COGs) and experimented with the time dimension using Python’s xarray to compute the data. We found that [earth-search](https://github.com/Element84/earth-search)’s effort to store Sentinel images as COGs made it easier for us to build virtual data cubes across the world without storing any data. This felt like an achievement and proof that modern data cubes should focus on improving computation rather than worrying about how to manage terabytes of data.

We wanted to build something to show that this approach actually works and is scalable. We deliberately chose to use only our laptops to run the prototype and process a year’s worth of data without expensive servers.

Learn about COG and how to generate one for this project [Here](./docs/cog.md)

## Purpose

### 1. Efficient On-the-Fly Tile Computation

This research explores how to perform real-time calculations on satellite images at different zoom levels, similar to Google Earth Engine, but using open-source tools. By using Cloud Optimized GeoTIFFs (COGs) with Sentinel-2 imagery, large images can be analyzed without needing to pre-process or store them. The study highlights how this method can scale well and work efficiently, even with limited hardware. Our main focus is on how to scale the computation on different zoom-levels without introducing server overhead 

[Watch](https://krschap.nyc3.cdn.digitaloceanspaces.com/ontheflydemo.gif)

#### Example python usage

```python
import mercantile
from PIL import Image
from io import BytesIO
from virtughan.tile import TileProcessor

lat, lon = 28.28139, 83.91866
zoom_level = 12
x, y, z = mercantile.tile(lon, lat, zoom_level)

tile_processor = TileProcessor()

image_bytes, feature = await tile_processor.cached_generate_tile(
    x=x,
    y=y,
    z=z,
    start_date="2020-01-01",
    end_date="2025-01-01",
    cloud_cover=30,
    band1="red",
    band2="nir",
    formula="(band2-band1)/(band2+band1)",
    colormap_str="RdYlGn",
)

image = Image.open(BytesIO(image_bytes))

print(f"Tile: {x}_{y}_{z}")
print(f"Date: {feature['properties']['datetime']}")
print(f"Cloud Cover: {feature['properties']['eo:cloud_cover']}%")

image.save(f'tile_{x}_{y}_{z}.png')
```


### 2. Virtual Computation Cubes: Focusing on Computation 
While storing large images can offer some benefits, we believe that placing emphasis on efficient computation yields far greater advantages and effectively removes the need to worry about large-scale image storage. COGs make it possible to analyze images directly without storing the entire dataset. This introduces the idea of virtual computation cubes, where images are stacked and processed over time, allowing for analysis across different layers ( including semantic layers ) without needing to download or save everything. So original data is never replicated. In this setup, a data provider can store and convert images to COGs, while users or service providers focus on calculations. This approach reduces the need for terra-bytes of storage and makes it easier to process large datasets quickly.

#### Example python usage

Example NDVI calculation 

```python
from virtughan.engine import VirtughanProcessor

processor = VirtughanProcessor(
    bbox=[83.84765625, 28.22697003891833, 83.935546875, 28.304380682962773],
    start_date="2023-01-01",
    end_date="2025-01-01",
    cloud_cover=30,
    formula="(band2-band1)/(band2+band1)",
    band1="red",
    band2="nir",
    operation="median",
    timeseries=True,
    output_dir="virtughan_output",
    workers=16
)

processor.compute()
```


### Summary 

This research introduces methods on how to use COGs, the SpatioTemporal Asset Catalog (STAC) API, and NumPy arrays to improve the way large Earth observation datasets are accessed and processed. The method allows users to focus on specific areas of interest, process data across different bands and layers over time, and maintain optimal resolution while ensuring fast performance. By using the STAC API, it becomes easier to search for and only process the necessary data without needing to download entire images ( not even the single scene , only accessing the parts ) The study shows how COGs can improve the handling of large datasets, not only making  the access faster but also making computation efficient, and scalable across different zoom levels . 

![flowchart](flowchart-virtughan.png)


### Sample case study : 
[Watch Video](https://krschap.nyc3.cdn.digitaloceanspaces.com/virtughan.MP4)
 

## Local Setup 

This project has FASTAPI and Plain JS Frontend.

Inorder to setup project , follow [here](./docs/install.md)

## Tech Stack 
<p align="left">
 <img src="https://github.com/user-attachments/assets/86e41e87-5269-48e4-a462-8b355cbe552f" style="width:100px;"/>
 <img src="https://github.com/user-attachments/assets/5805b809-28f7-4574-a0f2-9a41af63d20b" style="width:100px;"/>
 <img src="https://github.com/user-attachments/assets/00ea7127-6954-4003-9ed5-a8840373ea2a" style="width:100px;"/>
</p>

## Resources and Credits 

- https://registry.opendata.aws/sentinel-2-l2a-cogs/ COGS Stac API for sentinel-2

## Contribute

Liked the concept? Want to be part of it ?  

If you have experience with **JavaScript**, **FastAPI**, building geospatial **Python** libraries , we’d love your contributions! But you don’t have to be a coder to help—spreading the word is just as valuable.  

### How You Can Contribute ?

 **Code Contributions**  
- Fork the repository and submit a PR with improvements, bug fixes, or features. Use commitizen for your commits
- Help us refine our **development guidelines** !  

 **Documentation & Testing**  
- Improve our docs to make it easier for others to get started.  
- Test features and report issues to help us build a robust system.  

 **Spread the Word**  
- Share the project on social media or among developer communities.  
- Bring in more contributors who might be interested!  

 **Support Us**  
If you love what we’re building, consider buying us a coffee ☕ to keep the project going!  

[![Buy Us a Coffee](https://img.shields.io/badge/Buy%20Us%20a%20Coffee-Support-blue?style=flat&logo=buy-me-a-coffee)](#)  


## Acknowledgment

This project was initiated during the project work of our master's program , Coopernicus Masters in Digital Earth. 
We are thankful to all those involved and supported us from the program. 
<p align="left">
  <img src="https://github.com/user-attachments/assets/2f0555f8-67c3-49da-a0e8-037bdfd4ce10" alt="CMIDE-InLine-logoCMYK" style="width:200px;"/>
  <img src="https://github.com/user-attachments/assets/e553c675-f8e5-440a-b50f-625d0ce4f0c9" alt="EU_POS_transparent" style="width:200px;"/>
  <img src="https://kshitijrajsharma.com.np/PLUS_Logo-transparent.png" alt="PLUS" style="height:80px"/>
</p>

## Copyright 

© 2024 – Concept by Kshitij and Upen , Distributed under GNU General Public License v3.0 

