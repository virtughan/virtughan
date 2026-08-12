var map = L.map("map").setView([28.202082, 83.957222], 15);
      // L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      //   attribution:
      //     '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      // }).addTo(map);

      // Function to update scroll zoom based on screen size -this is set because mobile devices face problem when they scroll, map zooms.
      function updateMapInteractions() {
          if (window.innerWidth < 768) { // this is for screen size less than tablet
              map.scrollWheelZoom.disable();
              map.dragging.disable();
              map.touchZoom.disable();
              map.doubleClickZoom.disable();
              map.boxZoom.disable();
              map.keyboard.disable();
          } else {
              map.scrollWheelZoom.enable();
              map.dragging.enable();
              map.touchZoom.enable();
              map.doubleClickZoom.enable();
              map.boxZoom.enable();
              map.keyboard.enable();
          }
      }


      // Initial check on page load
      updateMapInteractions();
      // Update on window resize
      window.addEventListener('resize', updateMapInteractions);

        // Add custom control button: for mobile screens enable zoom and drag by clicking on this button. 
        var customControl = L.Control.extend({
          options: {
            position: 'topleft' // 'topleft', 'topright', 'bottomleft' or 'bottomright'
          },
          onAdd: function (map) {
            var container = L.DomUtil.create('div', 'leaflet-control-custom');

            container.onclick = function () {
              if (map.scrollWheelZoom.enabled()) {
                map.scrollWheelZoom.disable();
                map.dragging.disable();
                map.touchZoom.disable();
                map.doubleClickZoom.disable();
                container.style.border = '1px solid red'; //disabled
              } else {
                map.scrollWheelZoom.enable();
                map.dragging.enable();
                map.touchZoom.enable();
                map.doubleClickZoom.enable();
                container.style.border = '1px solid green'; // enabled
              }
            }
            return container;
          }
        });

        map.addControl(new customControl());

        function updateControlButtonState() {
          var container = document.querySelector('.leaflet-control-custom');
          if (window.innerWidth < 768) { // This is for screen size less than tablet
            container.style.border = map.scrollWheelZoom.enabled() ? '1px solid green' : '1px solid red';
          }
        }

        // Call this function initially and on window resize to set the correct control button state
        window.addEventListener('resize', updateControlButtonState);
        updateControlButtonState();


      var osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenStreetMap contributors',
            zIndex: 1,
            maxZoom: 22,
            maxNativeZoom:19,
        });

        var satellite = L.tileLayer('https://www.google.cn/maps/vt?lyrs=s@189&gl=cn&x={x}&y={y}&z={z}', {
            attribution: '&copy; Google',
            maxZoom: 22,
            maxNativeZoom:19,
            zIndex: 1
        });


        var opentopomap = L.tileLayer('https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png', {
            attribution: '&copy; OpenTopoMap contributors',
            zIndex: 1
        });

        var esriSatellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
            attribution: '&copy; Esri',
            maxZoom: 22,
            maxNativeZoom: 19,
            zIndex: 1
        });

        // Add the default base layer to the map
        osm.addTo(map);

        // Create a base layers object
        var baseLayers = {
            "OpenStreetMap": osm,
            "Satellite (Google)": satellite,
            "Satellite (ESRI)": esriSatellite,
            "Open Topomap": opentopomap,
        };

        // Add the layers control to the map
        L.control.layers(baseLayers).addTo(map);

        

      //add osm search control
      // container for address search results
      const addressSearchResults = new L.LayerGroup().addTo(map);

      /*** Geocoder ***/
      // OSM Geocoder
      const osmGeocoder = new L.Control.geocoder({
          collapsed: true,
          position: 'topleft',
          text: 'Address Search',
          placeholder: 'Enter street address',
        defaultMarkGeocode: false
      }).addTo(map);    

      // handle geocoding result event
      osmGeocoder.on('markgeocode', e => {
        // to review result object
        console.log(e);
        // const coords = [e.geocode.center.lat, e.geocode.center.lng];
        // map.setView(coords, 16);
        // const resultMarker = L.marker(coords).addTo(map);
        // resultMarker.bindPopup(e.geocode.name).openPopup();

        var bbox = e.geocode.bbox;
          var poly = L.polygon([
            bbox.getSouthEast(),
            bbox.getNorthEast(),
            bbox.getNorthWest(),
            bbox.getSouthWest()
          ]);//.addTo(map);
          map.fitBounds(poly.getBounds());
      });


        // Custom loader control
        const LoaderControl = L.Control.extend({
          onAdd: function(map) {
            const loaderDiv = L.DomUtil.create('div', 'leaflet-control-loader');
            loaderDiv.innerHTML = '<div class="map-loader"></div>';
            loaderDiv.style.display = 'none';
            return loaderDiv;
          },
        });

        const loaderControl = new LoaderControl({ position: 'topleft' });
        loaderControl.addTo(map);

      function showLoaderOnMap(layer, downloading){
        // console.log("entered");
        if(layer){
          // Show loader when tiles start loading
          layer.on('loading', () => {
            loaderControl.getContainer().style.display = 'block';
          });

          // Hide loader when tiles are fully loaded
          layer.on('load', () => {
            loaderControl.getContainer().style.display = 'none';
          });
          loaderControl.getContainer().style.display = 'none';
        }
        else{
          if(downloading){
            loaderControl.getContainer().style.display = 'block';
          }
          else{
            loaderControl.getContainer().style.display = 'none';
          }
          
        }
        
      }

      var geojsonLayer;
      var liveLayer;
      var computeLayer;
      var computeLayerBounds = null; // stored from metadata for zoom-to-layer
      var highlightedLayer = L.layerGroup();
      var activeImagesBboxLayer = null;
      var activeImagesBboxSource = null;
      // Per-source bbox layers
      var sourceBboxLayers = { search: null, analyze: null, download: null };
      var clickedResultList = false;
      var previousListMouseIn;
      var export_params_bbox_changed = false;

      var tile_params = {
          "bbox": "",                  
          "startDate": "",         
          "endDate": "",           
          "cloudCover": 30,        
          "bands": "visual",
          "formula": "visual",
          "timeseries": "false",
          "operation": "median",
          "collection": "sentinel-2-l2a",
          "mode": null
      }

      var export_params = {
        "bbox": "",
        "startDdate": "2024-01-02",
        "endDate": "2025-01-01",
        "cloudCover": 30,
        "formula": "(nir - red) / (nir + red)",
        "bands": "red,nir",
        "operation": "median",
        "timeseries": "false",
        "bands_list":"",
        "smart_filters":"false",
        "collection": "sentinel-2-l2a",
        "mode": null
      }

      // var formula = "(band2-band1)/(band2+band1)";
      // var band1 = "red";
      // var band2 = "nir";

      var bounds = map.getBounds();
      tile_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
      if(export_params_bbox_changed){}else{export_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;}
      document.getElementById("coords").textContent = tile_params.bbox;
      document.getElementById("zoom-level").textContent = map.getZoom();

      map.on("moveend", function () {
        bounds = map.getBounds();
        tile_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
        if(export_params_bbox_changed){}else{export_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;}
        document.getElementById("coords").textContent = tile_params.bbox;
        if(export_params_bbox_changed){}else{document.getElementById("map-window-content").innerHTML = export_params.bbox;}
        document.getElementById("zoom-level").textContent = map.getZoom();
        // Show zoom warning if tiles are active and zoom < 10
        var zoomWarning = document.getElementById('zoom-warning-overlay');
        if (zoomWarning) {
          if (map.getZoom() < 10 && liveLayer && map.hasLayer(liveLayer)) {
            zoomWarning.style.display = 'flex';
          } else {
            zoomWarning.style.display = 'none';
          }
        }
      });

      function parseBboxString(bboxValue) {
        if (!bboxValue || typeof bboxValue !== "string") {
          return null;
        }
        const parts = bboxValue.split(",").map((value) => Number(value));
        if (parts.length !== 4 || parts.some((value) => Number.isNaN(value))) {
          return null;
        }
        const [west, south, east, north] = parts;
        return [[south, west], [north, east]];
      }

      function clearResultBboxLayers() {
        if (activeImagesBboxLayer && map.hasLayer(activeImagesBboxLayer)) {
          map.removeLayer(activeImagesBboxLayer);
        }
        activeImagesBboxLayer = null;
        activeImagesBboxSource = null;
        // Clear all per-source bbox layers
        Object.keys(sourceBboxLayers).forEach(function(src) {
          if (sourceBboxLayers[src] && map.hasLayer(sourceBboxLayers[src])) {
            map.removeLayer(sourceBboxLayers[src]);
          }
          sourceBboxLayers[src] = null;
        });
        if (highlightedLayer) {
          highlightedLayer.clearLayers();
        }
        map.closePopup();
        if (typeof updateLayerCountSummary === "function") {
          updateLayerCountSummary();
        }
      }

      function clearImagesBboxLayer() {
        if (activeImagesBboxLayer && map.hasLayer(activeImagesBboxLayer)) {
          map.removeLayer(activeImagesBboxLayer);
        }
        activeImagesBboxLayer = null;
        activeImagesBboxSource = null;
      }

      function buildSourceBboxLayer(source, payload) {
        if (source === "search") {
          return geojsonLayer || null;
        }

        // For analyze and download, build a geojsonLayer from the image features
        // returned by the /search API (same as search does), not from the AOI bbox.
        const items = payload?.items || [];
        if (items.length === 0) {
          return null;
        }

        const data = {
          type: "FeatureCollection",
          features: items,
        };

        return L.geoJSON(data, {
          style: function (feature) {
            return {
              fillOpacity: 0,
              color: source === "analyze" ? "#f59e0b" : source === "download" ? "#3b82f6" : "red",
              weight: 1,
            };
          },
          onEachFeature: function (feature, layer) {
            layer.on("click", function () {
              if (Object.keys(highlightedLayer._layers).length > 0) {
                highlightedLayer.clearLayers();
              }
              var clickedLayer = createLayer(feature);
              highlightedLayer.addLayer(clickedLayer);
              highlightedLayer.addTo(map);
              layer.bindPopup(createPopup(feature)).openPopup();
              document
                .querySelector(".download-section h4")
                .addEventListener("click", function () {
                  var ul = this.nextElementSibling;
                  ul.style.display =
                    ul.style.display === "none" ? "block" : "none";
                });
            });
          },
        });
      }

      function syncResultBboxLayers(source, payload) {
        if (!source) {
          clearResultBboxLayers();
          return;
        }

        const bboxCheckId = source + "_bbox_layer";
        const bboxEnabled = document.getElementById(bboxCheckId)?.checked;
        activeImagesBboxSource = source;

        if (!bboxEnabled) {
          // Only clear this source's layer
          if (sourceBboxLayers[source] && map.hasLayer(sourceBboxLayers[source])) {
            map.removeLayer(sourceBboxLayers[source]);
          }
          sourceBboxLayers[source] = null;
          return;
        }

        const nextLayer = buildSourceBboxLayer(source, payload);
        // Remove only this source's previous layer
        if (sourceBboxLayers[source] && map.hasLayer(sourceBboxLayers[source])) {
          map.removeLayer(sourceBboxLayers[source]);
        }
        sourceBboxLayers[source] = nextLayer;

        if (nextLayer) {
          nextLayer.addTo(map);
          if (source === "search" && typeof initializeTransparency === "function") {
            initializeTransparency();
          }
        }

        if (typeof updateLayerCountSummary === "function") {
          updateLayerCountSummary();
        }
      }

      function syncResultBboxLayerForSource(source) {
        const payload = typeof resultSourceState !== "undefined" ? resultSourceState[source] : null;
        if (!payload) return;
        const nextLayer = buildSourceBboxLayer(source, payload);
        if (sourceBboxLayers[source] && map.hasLayer(sourceBboxLayers[source])) {
          map.removeLayer(sourceBboxLayers[source]);
        }
        sourceBboxLayers[source] = nextLayer;
        if (nextLayer) {
          nextLayer.addTo(map);
        }
        if (typeof updateLayerCountSummary === "function") {
          updateLayerCountSummary();
        }
      }

      function clearBboxLayerForSource(source) {
        if (sourceBboxLayers[source] && map.hasLayer(sourceBboxLayers[source])) {
          map.removeLayer(sourceBboxLayers[source]);
        }
        sourceBboxLayers[source] = null;
        if (typeof updateLayerCountSummary === "function") {
          updateLayerCountSummary();
        }
      }

      window.syncResultBboxLayers = syncResultBboxLayers;
      window.syncResultBboxLayerForSource = syncResultBboxLayerForSource;
      window.clearBboxLayerForSource = clearBboxLayerForSource;
      window.clearResultBboxLayers = clearResultBboxLayers;
      window.clearImagesBboxLayer = clearImagesBboxLayer;

      function createPopup(feature){
        const cloudCover = feature.properties["eo:cloud_cover"];
        const acquisitionMode = feature.properties["sar:instrument_mode"];
        const collectionSpecificDetails = cloudCover !== undefined
          ? `<div class="mb-2"><strong class="text-xs text-gray-600">Cloud Cover:</strong> <span class="text-xs text-gray-500">${cloudCover}</span></div>`
          : acquisitionMode
            ? `<div class="mb-2"><strong class="text-xs text-gray-600">Acquisition Mode:</strong> <span class="text-xs text-gray-500">${acquisitionMode}</span></div>`
            : '';
        var popupContent = `
          <div class="popup-content max-h-72 overflow-y-auto custom-scrollbar p-2">
            <div class="mb-2">
              <strong class="text-base text-gray-800">${feature.id}</strong>
            </div>
            <div class="mb-2">
              <strong class="text-xs text-gray-600">Date:</strong>
              <span class="text-xs text-gray-500">${feature.properties.datetime}</span>
            </div>
            ${collectionSpecificDetails}
            <hr class="my-2">
            <div class="mb-2">
              <strong class="text-xs">Properties:</strong>
              <div class="max-w-md overflow-x-auto custom-scrollbar">
                <table class="min-w-full table-fixed divide-y divide-gray-200">
                  <tbody class="bg-white divide-y divide-gray-200">
                    ${Object.entries(feature.properties).map(([key, value], index) =>
                      `<tr class="${index % 2 === 0 ? 'bg-gray-50' : 'bg-white'}">
                        <td class="w-1/3 px-2 py-1 text-xs text-gray-500 break-words">${key}</td>
                        <td class="w-2/3 px-2 py-1 text-xs text-gray-900 break-words">${value}</td>
                      </tr>`).join("")}
                  </tbody>
                </table>
              </div>
            </div>
            <div class="download-section mt-2">
              <h4 class="text-sm font-semibold">Download</h4>
              <ul class="list-disc list-inside text-xs">
                ${Object.entries(feature.assets).map(([key, asset]) =>
                  `<li><a href="${asset.href}" target="_blank" class="text-indigo-600 hover:underline break-words">${asset.title}</a></li>`
                ).join("")}
              </ul>
            </div>
          </div>
        `;
        return popupContent;
      }

      function createLayer(feature){
        var layerCreated = L.geoJSON(feature, {
                style: function () {
                  return {
                    fillOpacity: 0.5,
                    color: "yellow",
                    weight: 2,
                  };
                },
              });
        return layerCreated;
      }

      document
        .getElementById("search-button")
        .addEventListener("click", function () {
          trackLiveViewButtonClick("LiveViewButton");

          document.getElementById("resultTab").click();
          document.getElementById("layerSwitcherContainer").classList.remove("hidden");
          document.getElementById("searchLayerSwitcher").classList.remove("hidden");
          document.getElementById("searchBboxLayerSwitcher").classList.remove("hidden");
          document.getElementById("feature-list").innerHTML = "";
          startLoader('feature-list');
          document.getElementById("search_layer").checked = true;

          tile_params.collection = getSelectedCollection('search');
          tile_params.mode = tile_params.collection === 'sentinel-1-rtc' ? getSelectedMode('search') : null;

          const bounds = map.getBounds();
          tile_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
          tile_params.startDate = document.getElementById("start-date").value;
          tile_params.endDate = document.getElementById("end-date").value;
          tile_params.cloudCover = document.getElementById("cloud-cover").value;

          loadTiles();
        });

      function loadTiles(){
        if (liveLayer) {
          map.removeLayer(liveLayer);
        }

        tile_params.collection = getSelectedCollection('search');
        tile_params.mode = tile_params.collection === 'sentinel-1-rtc' ? getSelectedMode('search') : null;

        var checkedTimeseriesSearch = document.getElementById("timeSeries_search").checked;
        var transparentTile = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO2rjWQAAAAASUVORK5CYII=";

        var encodedUrl_tiles = `/tile/{z}/{x}/{y}?start_date=${encodeURIComponent(tile_params.startDate)}&end_date=${encodeURIComponent(tile_params.endDate)}&cloud_cover=${encodeURIComponent(tile_params.cloudCover)}&formula=${encodeURIComponent(tile_params.formula)}&bands=${encodeURIComponent(tile_params.bands)}&timeseries=${encodeURIComponent(tile_params.timeseries)}&collection=${encodeURIComponent(tile_params.collection)}&colormap_str=${encodeURIComponent(typeof selectedTilePalette !== 'undefined' ? selectedTilePalette : 'RdYlGn')}`;
        if (tile_params.mode) {
          encodedUrl_tiles += `&mode=${encodeURIComponent(tile_params.mode)}`;
        }
        if(checkedTimeseriesSearch){
          encodedUrl_tiles += `&operation=${encodeURIComponent(tile_params.operation)}`;
        }
        liveLayer = L.tileLayer(
          encodedUrl_tiles,
          {
            tileSize: 256,
            opacity: 0.8,
            zIndex: 5,
            maxZoom: 22,
            maxNativeZoom:22,
            attribution:
              '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
          }
        );

        var tileErrorShown = false;
        liveLayer.on('tileerror', function () {
          if (!tileErrorShown && map.getZoom() >= 10) {
            tileErrorShown = true;
            showMessage('warning', 8000, 'Some tiles failed to load from the server. The map shows a blank fallback tile instead of a broken image.');
          }
        });

        showLoaderOnMap(liveLayer, false);
        liveLayer.addTo(map);
        if (typeof updateLayerCountSummary === "function") {
          updateLayerCountSummary();
        }
        // Show zoom warning immediately if zoom < 10
        var zoomWarning = document.getElementById('zoom-warning-overlay');
        if (zoomWarning) {
          zoomWarning.style.display = map.getZoom() < 10 ? 'block' : 'none';
        }
        // Update tiles layer info tooltip
        var tilesInfo = document.getElementById('tiles-layer-info');
        if (tilesInfo) {
          var filterBtn = document.getElementById('select-button_search');
          var filterName = filterBtn ? filterBtn.querySelector('.truncate').innerText : '';
          var label = (filterName && filterName !== 'Select Option') ? filterName + ' | ' : 'Custom | ';
          tilesInfo.setAttribute('data-formula', label + tile_params.formula);
        }

        fetchSearchResults({
          bbox: tile_params.bbox,
          startDate: tile_params.startDate,
          endDate: tile_params.endDate,
          cloudCover: tile_params.cloudCover,
          collection: tile_params.collection,
          mode: tile_params.mode,
        })
          .then((features) => {
            if (geojsonLayer) {
              map.removeLayer(geojsonLayer);
            }

            const data = {
              type: "FeatureCollection",
              features,
            };

            geojsonLayer = L.geoJSON(data, {
              style: function (feature) {
                return {
                  fillOpacity: 0,
                  color: "red",
                  weight: 1,
                };
              },
              onEachFeature: function (feature, layer) {
                layer.on("click", function () {
                  if (Object.keys(highlightedLayer._layers).length > 0) {
                    highlightedLayer.clearLayers();
                  }
                  var clickedLayer = createLayer(feature);
                  highlightedLayer.addLayer(clickedLayer);
                  highlightedLayer.addTo(map);
                  if(document.getElementById("search_bbox_layer").checked){
                    map.fitBounds(geojsonLayer.getBounds());
                  }

                  layer.bindPopup(createPopup(feature)).openPopup();

                  document
                    .querySelector(".download-section h4")
                    .addEventListener("click", function () {
                      var ul = this.nextElementSibling;
                      ul.style.display =
                        ul.style.display === "none" ? "block" : "none";
                    });
                });
              },
            });

            setResultSource('search', {
              kind: 'scenes',
              items: features,
              bbox: tile_params.bbox,
            });
            stopLoader('feature-list');

            document.getElementById("sidebar").style.display = "block";
            if (typeof syncResultBboxLayers === "function") {
              syncResultBboxLayers('search', { kind: 'scenes', items: features, bbox: tile_params.bbox });
            }
          });
      }
