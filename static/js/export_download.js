var completed_log = false;
downloading = false;
      document.getElementById("export-map-view-button").addEventListener('click', function() {
        //track button click google analytics
        trackExportButtonClick("visualizeAndExportButton");

        completed_log = false;
        var analyzeChecked = document.getElementById("analyze-data").checked;
        var smartFilters = document.getElementById("smart-filters").checked;

        export_params.startDdate = document.getElementById("start-date-export").value;
        export_params.endDate = document.getElementById("end-date-export").value;
        export_params.cloudCover = document.getElementById("cloud-cover-export").value;

        document.getElementById("after-compute-buttons").classList.add("hidden");
        document.getElementById('compute_progress_text').style.color = 'white';

        document.getElementById("layerSwitcherBox").classList.add("hidden");
        var textCon =  "Please Wait Computing...";
        var textTitl = "Computation Progress";
        
        if(!analyzeChecked){
          textCon = "Please Wait Downloading...";
          textTitl = "Download Progress";
        }
        document.getElementById('ProgressTextsBefore').innerHTML = `<li style = "font-size: 10px;">${textCon}</li>`;
        document.getElementById('computation_progress_text').innerHTML = textTitl;
        

        document.getElementById('operationImageView').src ="";
        document.getElementById('trendImageView').src ="";
        clearPreviousTimeSeriesData();

        document.getElementById("colorPalettes").classList.remove("hidden");

        if(document.getElementById("operation").checked){
          document.getElementById("compute_layer").classList.remove("hidden");
          document.getElementById("colorPalettes").classList.remove("hidden");
        }
        else{
          document.getElementById("compute_layer").classList.add("hidden");
          document.getElementById("colorPalettes").classList.add("hidden");
        }

        //remove legend if there is a legend
        document.getElementById("legend").classList.add("hidden");

        //show warning if the area of bbox is greater than 500 SQ Km.
        // var aoiText = document.getElementById("selected-filter-value-bbox").innerText;
        //  console.log(export_params.bbox);
        //  console.log(bounds);
         const [west, south, east, north] = export_params.bbox.split(',').map(Number);

          const boundsObject = {
              west: west,
              south: south,
              east: east,
              north: north
          };
          // Use the object to create a rectangle in Leaflet
          const bounds_rect = [
            [boundsObject.south, boundsObject.west], // Southwest corner
            [boundsObject.north, boundsObject.east]  // Northeast corner
          ];
          var bbox_rectangle = L.rectangle(bounds_rect, {fillOpacity: 0.1, opacity: 0.6});
          var geojson = bbox_rectangle.toGeoJSON();
  
          // Calculate the area using turf.js
          var area = turf.area(geojson);
  
          // Convert area to square kilometers (optional)
          var areaKm2 = area / 1000000;
          // console.log('Area: ' + areaKm2.toFixed(2) + ' square kilometers');
  
          if(areaKm2 > 500){
            // showMessage('success', "message");
            showMessage('warning', 10000, "Zoom in or reduce the size of your area of interest. <br/> Eg. smaller AOI than 500 SQ.Km. Sorry, this is due to limited server specs.");
          }
          else{ // if aoi area is fine
        
        var url_compute = `/export?bbox=${export_params.bbox}&start_date=${encodeURIComponent(export_params.startDdate)}&end_date=${encodeURIComponent(export_params.endDate)}&cloud_cover=${export_params.cloudCover}&formula=${encodeURIComponent(export_params.formula)}&band1=${encodeURIComponent(export_params.band1)}&band2=${encodeURIComponent(export_params.band2)}&timeseries=${encodeURIComponent(export_params.timeseries)}&smart_filters=${export_params.smart_filters}&collection=${encodeURIComponent(export_params.collection)}`;

        //if operation and timeseries should not be sent in url. 
        // var url_compute = `/export?bbox=${export_params.bbox}&start_date=${encodeURIComponent(export_params.startDdate)}&end_date=${encodeURIComponent(export_params.endDate)}&cloud_cover=${export_params.cloudCover}&formula=${encodeURIComponent(export_params.formula)}&band1=${encodeURIComponent(export_params.band1)}&band2=${encodeURIComponent(export_params.band2)}`;
        
        if(document.getElementById("operation").checked){
          url_compute += `&operation=${encodeURIComponent(export_params.operation)}`;
        }
        // else if(document.getElementById("timeSeries").checked){
        //   url_compute += "&timeseries=${encodeURIComponent(export_params.timeseries)}";
        // }
        // else if(document.getElementById("operation").checked && document.getElementById("timeSeries").checked){
        //   url_compute += "&operation=${encodeURIComponent(export_params.operation)}&timeseries=${encodeURIComponent(export_params.timeseries)}";
        // }
        
        // console.log(url_compute);

        var download_url = `/image-download?bbox=${export_params.bbox}&start_date=${encodeURIComponent(export_params.startDdate)}&end_date=${encodeURIComponent(export_params.endDate)}&cloud_cover=${export_params.cloudCover}&bands_list=${export_params.bands_list}&smart_filters=${smartFilters}&collection=${encodeURIComponent(export_params.collection)}`;
        
        
        var url;
        if(analyzeChecked){
          url = url_compute;
        }
        else{
          url = download_url;
        }

        fetch(url, { 
          method: 'GET' 
        }) 
        .then(response => response.json()) 
        .then(data => {
          console.log('Success:', data);

          // Store the UID in localStorage
          if (data.uid) {
            localStorage.setItem('UID', data.uid);
          }

        })
        .catch((error) => {
          console.error('Error:', error);
        });
        
        //Open Result Tab
        document.getElementById("resultTab").click();
        document.getElementById("layerSwitcherContainer").classList.remove("hidden");
        document.getElementById("computeLayerSwitcher").classList.remove("hidden");

        document.getElementById("download-complete").classList.add("hidden");

        //show the progress to the user
        
        function checkProcessingStatus() {
          const uid = localStorage.getItem('UID');
          // console.log("UID: ", uid)

          const logUrl = "/logs?uid="+uid;

          fetch(logUrl, { 
            method: 'GET' 
          })
            .then(response => response.text())
            .then(data => {
              // console.log('Success log:', data);
              updateProgress(data);
              if (data.includes('Processing completed.') || data.includes('100%')) {
                clearInterval(intervalId);
                console.log('Processing completed. Stopped checking.');
                if(completed_log){}
                else{
                  if(data.includes('Filtered 0 items') || data.includes('Scenes covering input area: 0')){}
                  else{
                    if(analyzeChecked){
                      document.getElementById("layerSwitcherBox").classList.remove("hidden");
                      if(document.getElementById("operation").checked){
                        plotGeoTIFF('static/export/'+uid+'/custom_band_output_aggregate.tif');
                        completed_log = true;
                      }
                    }
                    else{
                      document.getElementById("download-complete").classList.remove("hidden");
                    }
                
                  }  
                }  
              }
            })
            .catch((error) => {
              console.error('Error:', error);
            });
        }

        // Initial call to set progress to 0%
        startProgressComputation('compute', 0);
        
        // Start checking the processing status every 5 seconds
        const intervalId = setInterval(checkProcessingStatus, 5000);

        function updateProgress(logData) {
          if (logData.includes('No images found') || logData.includes('Filtered 0 items') || logData.includes('Scenes covering input area: 0')) {
              displayNoImageFoundMessage();
          } else {
              // Extract log lines
              const logLines = logData.split('\n');
              const nonComputationLogs = logLines.filter(line => !line.includes('Computing Band Calculation') && !line.includes('Extracting Bands'));

              document.getElementById('ProgressTextsBefore').innerHTML = "";

              // Get the progress list element
              const progressTextsBefore = document.getElementById('ProgressTextsBefore');
              // Get the existing list items text content
              const existingItems = Array.from(progressTextsBefore.getElementsByTagName('li')).map(item => item.textContent);

              // Add non-computation logs to the progress list if they are not already present
              nonComputationLogs.forEach(step => {
                  if (!existingItems.includes(step)) {
                      const listItem = document.createElement('li');
                      listItem.style.fontSize = "10px !important";
                      listItem.textContent = step;
                      progressTextsBefore.appendChild(listItem);
                  }
              });

              // Handle "Computing Band Calculation" logs
              const computationLogs = logLines.filter(line => line.includes('Computing Band Calculation') || line.includes('Extracting Bands'));
              const latestLog = computationLogs[computationLogs.length - 1]; // Get the latest log

              if (latestLog) {
                  const matches = latestLog.match(/(\d+)%.*\| (\d+)\/(\d+).* \[(.*?)<(.*?)\]/);
                  if (matches) {
                      const current = matches[2];
                      const total = matches[3];
                      const elapsed = matches[4];
                      const remaining = matches[5].split(",")[0]; // remove miliseconds after comma
                      const perImageTime = matches[5].split(",")[1];

                      const logMessages = [
                          '-', //one space added
                          `Images Processed: ${current}/${total}`,
                          `Time Elapsed: ${elapsed}`,
                          `Time Remaining: ${remaining}`,
                          `Time Per Image: ${perImageTime}`
                      ];

                      // Add/update the log messages
                      logMessages.forEach((logMessage, index) => {
                          let existingLog = progressTextsBefore.querySelector(`.computation-log-${index}`);
                          if (existingLog) {
                              existingLog.textContent = logMessage;
                          } else {
                              const listItem = document.createElement('li');
                              listItem.classList.add(`computation-log-${index}`);
                              listItem.style.fontSize = "10px !important";
                              listItem.innerHTML = logMessage === ' ' ? '&nbsp;' : logMessage;
                              progressTextsBefore.appendChild(listItem);
                          }
                      });
                  }
              }

              // Handle progress bar updates
              const progressMatches = logData.match(/(\d+)%/g);
              if (progressMatches) {
                  const lastProgress = progressMatches[progressMatches.length - 1];
                  const progress = parseInt(lastProgress.replace('%', ''), 10);
                  startProgressComputation('compute', progress);
              }
              // Scroll the progress list to the bottom 
              progressTextsBefore.scrollTop = progressTextsBefore.scrollHeight;
          }
        }

        if (computeLayer) {
            map.removeLayer(computeLayer);
        }

        }//end of else, warning

      });


      var min;
      var max;
      var geoRaster;

      // console.log(interpolatedColorScales);

      var selectedPalette = getSelectedPalette();
      // console.log(selectedPalette);

      

      function plotGeoTIFF(tifUrl) {
        if (computeLayer) {
            map.removeLayer(computeLayer);
        }
        showLoaderOnMap(null, true);// for loader to load until it downloads file

        fetch(tifUrl)
          .then(response => {
            if (!response.ok) {
              showLoaderOnMap(null, false);
                if (response.status == 404) {
                  showMessage('error', 0, '404 Not Found: Couldnot load data on map. The requested file does not exist.')
                } else {
                  showMessage('error', 0, `HTTP error! Status: ${response.status}`)  
                }
              }
              return response.arrayBuffer();
          })
          .then(arrayBuffer => {
            parseGeoraster(arrayBuffer).then(georaster => {
              downloading = false; //remove loader afer file is downloaded.
              console.log("georaster:", georaster);
              geoRaster = georaster;

              /*
                  GeoRasterLayer is an extension of GridLayer,
                  which means can use GridLayer options like opacity.

                  Just make sure to include the georaster option!

                  Optionally set the pixelValuesToColorFn function option to customize
                  how values for a pixel are translated to a color.

                  https://leafletjs.com/reference.html#gridlayer
              */
              
              //uncomment this if the raster contains min and max and handled nodata values. eg. min and max doesnot have values like 100000000000000.
              min = georaster.mins[0];
              max = georaster.maxs[0];

              //uncomment this if raster min, max has values like 1000000000000.
              // const validValues = processRasterData(georaster); 
              // Calculate min and max values
              // console.log(validValues);
              // min = Math.min(...validValues);
              // max = Math.max(...validValues);

              console.log('Min Value:', min);
              console.log('Max Value:', max);

              computeLayer = new GeoRasterLayer({
                  georaster: georaster,
                  opacity: 0.8,
                  resolution: 256,
                  zIndex: 5,
                  // updateWhenZooming:true,
                  pixelValuesToColorFn: values => {
                      // var normalizedValue = (values[0] - min) / (max - min);
                        // console.log(values);
                        if(values[0] == -9999){
                          return 'rgba(0, 0, 0, 0)';
                        }
                        else{
                          return updateColor(values, selectedPalette);
                        }
                       // Get continuous color
                  }
              });
              
              showLoaderOnMap(computeLayer, false);
              map.addLayer(computeLayer);
              updateLegend(selectedPalette);


              map.fitBounds(computeLayer.getBounds());

              //add legend after adding layer
              document.getElementById("legend").classList.remove("hidden");
              
              initializeTransparency();
          });
        }).catch((error) => {
          console.log("error downloading data", error);
          showLoaderOnMap(null, false);
        });
      }

      // document.getElementById('paletteSelect').addEventListener('change', (event) => {
      //   updateRasterColor(event.target.value);
      //   updateLegend(event.target.value);
      // });
      

      function updateRasterColor(scaleName) {
        // console.log("entered updaterastercolor");
        if (computeLayer) {
          computeLayer.updateColors(pixelValuesToColorFn = values => {
              if (values[0] == -9999) {
                  return 'rgba(0, 0, 0, 0)'; // Transparent color for NaN values
              } else {
                  return updateColor(values, scaleName); // Handle single-band and multi-band rasters
              }
            });
          }
      }


      function updateLegend(paletteName) {
        const legend = document.getElementById('legend');
        const colorScale = colorScales[paletteName];
        const steps = 10; // Number of steps in the legend
        const stepValue = (max - min) / (steps - 1);

        // Clear existing legend items
        legend.innerHTML = '';

        // Create legend items based on color scale and pixel value range
        for (let i = 0; i < steps; i++) {
            const value = min + i * stepValue;
            const color = d3.scaleSequential(colorScale).domain([min, max])(value);

            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';

            const colorBox = document.createElement('div');
            colorBox.className = 'legend-color';
            colorBox.style.backgroundColor = color;

            const labelText = document.createElement('span');
            labelText.textContent = `${value.toFixed(2)}`;

            legendItem.appendChild(colorBox);
            legendItem.appendChild(labelText);
            legend.appendChild(legendItem);
        }
    }


      //for updating the transparency of layers
      
      function setLayerTransparency(layerName, value) {
          const layers = {
            "liveLayer": liveLayer,
            "geojsonLayer": geojsonLayer,
            "computeLayer": computeLayer
          };
          const layer = layers[layerName];
          // console.log(layer);
          if (layer) {
              if (layer.setOpacity) {
                  // For raster layers (e.g., imageOverlay)
                  layer.setOpacity(value / 100);
              } else if (layer.setStyle) {
                  // For vector layers (e.g., geoJSON)
                  layer.setStyle({ opacity: value / 100/*, fillOpacity: value / 100*/ });
              }
              // console.log(`Setting transparency of ${layerName} to ${value}%`);
          } else {
              console.error(`Layer ${layerName} not found`);
          }
      }

      // Initialize the slider values based on current layer transparency
      function initializeTransparency() {
        const layers = {
            "liveLayer": liveLayer,
            "geojsonLayer": geojsonLayer,
            "computeLayer": computeLayer
          };
          document.querySelectorAll('input[id^="transparency_"]').forEach(input => {
              const layerName = input.id.split('_')[1];
              const layer = layers[layerName];
              if (layer) {
                  let transparencyValue = 100; // Default to 100% if no transparency is set

                  if (layer.options && layer.options.opacity !== undefined) {
                      transparencyValue = layer.options.opacity * 100;
                  } else if (layer.options && layer.options.fillOpacity !== undefined) {
                      transparencyValue = layer.options.fillOpacity * 100;
                  }

                  input.value = transparencyValue;
              }
          });
      }

      // Query all inputs with an ID starting with "transparency_"
      document.querySelectorAll('input[id^="transparency_"]').forEach(input => {
          input.addEventListener('input', function() {
              const layerName = this.id.split('_')[1];
              const transparencyValue = this.value;
              setLayerTransparency(layerName, transparencyValue);
          });
      });
      