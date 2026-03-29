var map = L.map("map").setView([28.202082, 83.987222], 10);
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

        // Add the default base layer to the map
        osm.addTo(map);

        // Create a base layers object
        var baseLayers = {
            "OpenStreetMap": osm,
            "Satellite":satellite,
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
      var highlightedLayer = L.layerGroup();
      var clickedResultList = false;
      var previousListMouseIn;
      var export_params_bbox_changed = false;

      var tile_params = {
          "bbox": "",                  
          "startDate": "",         
          "endDate": "",           
          "cloudCover": 30,        
          "band1": "visual",        
          "band2": "nir",           
          "formula": "band1",
          "timeseries": "false",
          "operation": "median",
          "collection": "sentinel-2-l2a"
      }

      var export_params = {
        "bbox": "",
        "startDdate": "2024-01-02",
        "endDate": "2025-01-01",
        "cloudCover": 30,
        "formula": "(band2 - band1) / (band2 + band1)",
        "band1": "red",
        "band2": "nir",
        "operation": "median",
        "timeseries": "false",
        "bands_list":"",
        "smart_filters":"false",
        "collection": "sentinel-2-l2a"
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
      });

      function loadTiles(){
        if (liveLayer) {
          map.removeLayer(liveLayer);
        }

        var checkedTimeseriesSearch = document.getElementById("timeSeries_search").checked;
        
        var encodedUrl_tiles = `/tile/{z}/{x}/{y}?start_date=${encodeURIComponent(tile_params.startDate)}&end_date=${encodeURIComponent(tile_params.endDate)}&cloud_cover=${encodeURIComponent(tile_params.cloudCover)}&formula=${encodeURIComponent(tile_params.formula)}&band1=${encodeURIComponent(tile_params.band1)}&band2=${encodeURIComponent(tile_params.band2)}&timeseries=${encodeURIComponent(tile_params.timeseries)}&collection=${encodeURIComponent(tile_params.collection)}`;
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

        showLoaderOnMap(liveLayer, false);
        liveLayer.addTo(map);
      }

      document
        .getElementById("search-button")
        .addEventListener("click", function () {
          //track button click google analytics
          trackLiveViewButtonClick("LiveViewButton");

          //goto next tab to show result
          document.getElementById("resultTab").click();
          document.getElementById("layerSwitcherContainer").classList.remove("hidden");
          document.getElementById("searchLayerSwitcher").classList.remove("hidden");
          document.getElementById("searchBboxLayerSwitcher").classList.remove("hidden");
          document.getElementById("feature-list").innerHTML = '';
          // startProgressComputation('search', null);

          startLoader('feature-list');
          document.getElementById("search_layer").checked = true;

          var bounds = map.getBounds();
          tile_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
          tile_params.startDate = document.getElementById("start-date").value;
          tile_params.endDate = document.getElementById("end-date").value;
          tile_params.cloudCover = document.getElementById("cloud-cover").value;


          function createPopup(feature){
            var popupContent = `
              <div class="popup-content max-h-72 overflow-y-auto custom-scrollbar p-2">
                <div class="mb-2">
                  <strong class="text-base text-gray-800">${feature.id}</strong>
                </div>
                <div class="mb-2">
                  <strong class="text-xs text-gray-600">Date:</strong>
                  <span class="text-xs text-gray-500">${feature.properties.datetime}</span>
                </div>
                <div class="mb-2">
                  <strong class="text-xs text-gray-600">Cloud Cover:</strong>
                  <span class="text-xs text-gray-500">${feature.properties["eo:cloud_cover"]}</span>
                </div>
                <hr class="my-2">
                <div class="mb-2">
                  <strong class="text-xs">Properties:</strong>
                  <div class="max-w-md overflow-x-auto custom-scrollbar">
                    <table class="min-w-full table-fixed divide-y divide-gray-200">
                      <!--<thead class="bg-gray-50">
                        <tr>
                          <th scope="col" class="w-1/3 px-2 py-1 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Key</th>
                          <th scope="col" class="w-2/3 px-2 py-1 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Value</th>
                        </tr>
                      </thead>-->
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

          fetch(
            `/search?bbox=${tile_params.bbox}&start_date=${tile_params.startDate}&end_date=${tile_params.endDate}&cloud_cover=${tile_params.cloudCover}&collection=${encodeURIComponent(tile_params.collection)}`
          )
            .then((response) => response.json())
            .then((data) => {
              if (geojsonLayer) {
                map.removeLayer(geojsonLayer);
              }

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
                      // map.removeLayer(highlightedLayer);
                      highlightedLayer.clearLayers();
                      
                    }
                    var clickedLayer = createLayer(feature);
                    highlightedLayer.addLayer(clickedLayer);
                    highlightedLayer.addTo(map);
                    // map.fitBounds(clickedLayer.getBounds());
                    if(document.getElementById("search_bbox_layer").checked){
                      map.fitBounds(geojsonLayer.getBounds());
                    }
                    
                    
                    layer.bindPopup(createPopup(feature)/*, { keepInView: true }*/).openPopup();

                    // Add event listener for download section toggle
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
              if(document.getElementById("search_bbox_layer").checked){
                geojsonLayer.addTo(map);
                initializeTransparency();
              }

              var featureList = document.getElementById("feature-list");
              featureList.innerHTML = "";
              
              //add count of images
              // console.log("count "+data.features.length);
              document.getElementById("display-image-count").innerHTML = `Images: <span class="text-xs">${data.features.length}<span>`;

              data.features.forEach(function (feature, index) {
                var featureItem = document.createElement("div");
                featureItem.className = "feature-item";
                featureItem.innerHTML = `
                            <ul role="list" class="divide-y divide-gray-100">
                              <li id = "result_list_${index}" class="result-list-items flex justify-between gap-x-6 py-5 hover:bg-gray-100 transition-colors duration-300 cursor-pointer">
                                <div class="flex min-w-0 gap-x-4">
                                  <img class="size-12 flex-none rounded-full bg-gray-50" src="static/img/satellite-basemap.png" alt="">
                                  <div class="min-w-0 flex-auto">
                                    <p class="text-sm/6 font-semibold text-gray-900">${feature.id}</p>
                                    <p class="mt-1 truncate text-xs/5 text-gray-500">${feature.properties.datetime}</p>
                                  </div>
                                </div>
                                <div class="hidden shrink-0 sm:flex sm:flex-col sm:items-end">
                                  <!--<p class="text-sm/6 text-gray-900">Co-Founder / CEO</p>-->
                                  <p class="mt-auto text-xs/5 text-gray-400"><i class="fa-solid fa-cloud"></i> ${parseInt(feature.properties["eo:cloud_cover"])} % </time></p>
                                  <!--<p class="result-icons text-sm/6 text-gray-500 hover:text-gray-900"><i id = "result_icon_${index}" class="fa-regular fa-eye"></i></p>-->
                                </div>
                              </li>            
                        `;
                featureItem.addEventListener("mouseleave", function (e) {
                  // console.log(previousListMouseIn);
                  // console.log(e.target.querySelector('.result-list-items').id);
                  // console.log(clickedResultList);
                  if (Object.keys(highlightedLayer._layers).length > 0) {
                    // map.removeLayer(highlightedLayer);
                    if(clickedResultList == false && previousListMouseIn != e.target.querySelector('.result-list-items').id){
                      map.closePopup();
                      highlightedLayer.clearLayers();
                      // console.log("entered")
                    }
                    else if(previousListMouseIn == e.target.querySelector('.result-list-items').id){
                      map.removeLayer(highlightedLayer);
                    }
                    
                  }
                  previousListMouseIn = e.target.querySelector('.result-list-items').id;
                });
                featureItem.addEventListener("mouseenter", function (e) {
                  if (Object.keys(highlightedLayer._layers).length > 0) {
                    map.closePopup();
                    highlightedLayer.clearLayers();
                  }
                  var hoveredLayer = createLayer(feature);
                  // if(previousListMouseIn != e.target.querySelector('.result-list-items').id){
                    
                    highlightedLayer.addLayer(hoveredLayer);
                    
                    // console.log(e)
                    
                    hoveredLayer.bindPopup(createPopup(feature));
                  // }
                  // else{

                  // }
                  highlightedLayer.addTo(map);
                  // map.fitBounds(hoveredLayer.getBounds());
                  if(document.getElementById("search_bbox_layer").checked){
                    map.fitBounds(geojsonLayer.getBounds());
                  }
                 
                  clickedResultList = false;
                  

                });

                featureItem.addEventListener("click", function () {
                  // console.log(highlightedLayer.getLayers()[0]);
                  highlightedLayer.getLayers()[0].openPopup();
                  clickedResultList = true;
                })
                featureList.appendChild(featureItem);
              });
              stopLoader('feature-list');

              document.getElementById("sidebar").style.display = "block";

             
                loadTiles();

                initializeTransparency();
              
            });
        });