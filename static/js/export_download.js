var completed_log = false;
downloading = false;
      document.getElementById("export-map-view-button").addEventListener('click', function() {
        //track button click google analytics
        trackExportButtonClick("visualizeAndExportButton");

        export_params.collection = getSelectedCollection('export');
        export_params.mode = export_params.collection === 'sentinel-1-rtc' ? getSelectedMode('export') : null;

        completed_log = false;
        var analyzeChecked = document.getElementById("analyze-data").checked;
        var smartFilters = document.getElementById("smart-filters").checked;

        export_params.startDdate = document.getElementById("start-date-export").value;
        export_params.endDate = document.getElementById("end-date-export").value;
        export_params.cloudCover = document.getElementById("cloud-cover-export").value;

        document.getElementById("after-compute-buttons").classList.add("hidden");
        document.getElementById('compute_progress_text').style.color = 'white';

        if (analyzeChecked) {
          document.getElementById("layerSwitcherBox").classList.add("hidden");
          document.getElementById('ProgressTextsBefore').innerHTML = '<li style="font-size: 10px;">Please Wait Computing...</li>';
          document.getElementById('computation_progress_text').innerHTML = "Computation Progress";
          document.getElementById('compute_progressbar').style.display = '';
          // Hide download progress (not download-complete, that's a finished result)
          document.getElementById('download_progressbar').style.display = 'none';
        } else {
          document.getElementById('DownloadProgressTexts').innerHTML = '<li style="font-size: 10px;">Please Wait Downloading...</li>';
          document.getElementById('download_computation_progress_text').innerHTML = "Download Progress";
          document.getElementById('download_progressbar').style.display = '';
          document.getElementById('download-complete').classList.add("hidden");
          // Hide analyze progress (not layerSwitcherBox, that's a finished result)
          document.getElementById('compute_progressbar').style.display = 'none';
        }
        

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
  
          if(areaKm2 > 5000){
            showMessage('error', 0, "Area too large (" + areaKm2.toFixed(0) + " km²). Maximum allowed is 5,000 km². Please zoom in or draw a smaller area of interest.");
            return;
          }
          else if(areaKm2 > 2500){
            showMessage('warning', 15000, "Large area selected (" + areaKm2.toFixed(0) + " km²). Processing may take several minutes. Consider reducing the area for faster results.");
          }
          // proceed with export
        {
        
        var url_compute = `/export?bbox=${export_params.bbox}&start_date=${encodeURIComponent(export_params.startDdate)}&end_date=${encodeURIComponent(export_params.endDate)}&cloud_cover=${export_params.cloudCover}&formula=${encodeURIComponent(export_params.formula)}&bands=${encodeURIComponent(export_params.bands)}&timeseries=${encodeURIComponent(export_params.timeseries)}&smart_filters=${smartFilters}&collection=${encodeURIComponent(export_params.collection)}`;

        if (export_params.mode) {
          url_compute += `&mode=${encodeURIComponent(export_params.mode)}`;
        }

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
        if (export_params.mode) {
          download_url += `&mode=${encodeURIComponent(export_params.mode)}`;
        }
        
        
        var url;
        if(analyzeChecked){
          url = url_compute;
        }
        else{
          url = download_url;
        }

        const activeExportResultSource = analyzeChecked ? 'analyze' : 'download';
        setActiveResultSource(activeExportResultSource);

        const searchRequestParams = {
          bbox: export_params.bbox,
          startDate: export_params.startDdate,
          endDate: export_params.endDate,
          cloudCover: export_params.cloudCover,
          collection: export_params.collection,
          mode: export_params.mode,
        };

        const searchPromise = fetchSearchResults(searchRequestParams)
          .then((features) => {
            setResultSource(activeExportResultSource, {
              kind: 'scenes',
              items: features,
              bbox: export_params.bbox,
            });
          })
          .catch((error) => {
            console.error('Error fetching search results for result panel:', error);
          });

        const exportPromise = fetch(url, {
          method: 'GET'
        })
          .then((response) => response.json())
          .then((data) => {
            console.log('Success:', data);

            if (data.uid) {
              localStorage.setItem('UID', data.uid);
            }

            return data;
          })
          .catch((error) => {
            console.error('Error:', error);
          });

        Promise.allSettled([searchPromise, exportPromise]);
        
        //Open Result Tab
        document.getElementById("resultTab").click();
        document.getElementById("layerSwitcherContainer").classList.remove("hidden");
        if (analyzeChecked) {
          document.getElementById("computeLayerSwitcher").classList.remove("hidden");
          document.getElementById("compute_progressbar").style.display = '';
        } else {
          document.getElementById("downloadLayerSwitcher").classList.remove("hidden");
          document.getElementById("download-complete").classList.add("hidden");
          document.getElementById("download_progressbar").style.display = '';
        }

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
              updateProgress(data, analyzeChecked);
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
                      document.getElementById("download_progressbar").style.display = 'none';
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
        if (analyzeChecked) {
          startProgressComputation('compute', 0);
        } else {
          startProgressComputation('download', 0);
        }
        
        // Start checking the processing status every 5 seconds
        const intervalId = setInterval(checkProcessingStatus, 5000);

        function updateProgress(logData, isAnalyze) {
          if (logData.includes('No images found') || logData.includes('Filtered 0 items') || logData.includes('Scenes covering input area: 0')) {
              var msg = 'No image found / try smaller Area';
              if (logData.includes('Scenes covering input area: 0')) {
                msg = '0 scenes fully covering input area / try smaller Area';
              } else if (logData.includes('Filtered 0 items')) {
                msg = '0 items after filtering / adjust date or cloud cover';
              }
              displayNoImageFoundMessage(msg, isAnalyze);
          } else {
              const progressListId = isAnalyze ? 'ProgressTextsBefore' : 'DownloadProgressTexts';
              const progressName = isAnalyze ? 'compute' : 'download';

              // Extract log lines
              const logLines = logData.split('\n');
              const nonComputationLogs = logLines.filter(line => !line.includes('Computing Band Calculation') && !line.includes('Extracting Bands'));

              document.getElementById(progressListId).innerHTML = "";

              // Get the progress list element
              const progressTextsBefore = document.getElementById(progressListId);
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
                  startProgressComputation(progressName, progress);
              }
              // Scroll the progress list to the bottom 
              progressTextsBefore.scrollTop = progressTextsBefore.scrollHeight;
          }
        }

        // Only remove compute layer if starting a new analyze (not download)
        if (analyzeChecked && computeLayer) {
            map.removeLayer(computeLayer);
        }

        }//end of area check

      });


      var min;
      var max;

      var selectedPalette = getSelectedPalette();

      

      function plotGeoTIFF(tifUrl) {
        if (computeLayer) {
            map.removeLayer(computeLayer);
        }
        showLoaderOnMap(null, true);

        // Extract uid from the tifUrl path: static/export/{uid}/custom_band_output_aggregate.tif
        const parts = tifUrl.split('/');
        const uid = parts[2]; // static/export/{uid}/...

        selectedPalette = getSelectedPalette();

        // Fetch metadata (bounds + min/max) then add tile layer
        fetch(`/export-tile/${uid}/metadata`)
          .then(response => response.json())
          .then(metadata => {
            downloading = false;
            showLoaderOnMap(null, false);

            min = metadata.min;
            max = metadata.max;

            const tileUrl = `/export-tile/${uid}/{z}/{x}/{y}?colormap=${selectedPalette}&vmin=${min}&vmax=${max}`;
            computeLayer = L.tileLayer(tileUrl, {
              tileSize: 256,
              opacity: 1,
              zIndex: 5,
              maxZoom: 22,
              maxNativeZoom: 18,
              errorTileUrl: '',
            });

            // Store uid on the layer for palette changes
            computeLayer._exportUid = uid;

            showLoaderOnMap(computeLayer, false);
            map.addLayer(computeLayer);
            updateLegend(selectedPalette);

            if (typeof updateLayerCountSummary === "function") {
              updateLayerCountSummary();
            }
            // Update compute layer info tooltip
            var computeInfo = document.getElementById('compute-layer-info');
            if (computeInfo) {
              var filterBtn = document.getElementById('select-button_export');
              var filterName = filterBtn ? filterBtn.querySelector('.truncate').innerText : '';
              var label = (filterName && filterName !== 'Select Option') ? filterName + ' | ' : 'Custom | ';
              var pixelSize = (typeof getFinestResolution === 'function') ? getFinestResolution(export_params.bands, export_params.collection) : '';
              computeInfo.setAttribute('data-formula', label + export_params.formula + (pixelSize ? ' | Pixel: ' + pixelSize + 'm' : ''));
            }

            // Fit map to the raster bounds
            var bounds = L.latLngBounds(metadata.bounds);
            computeLayerBounds = bounds;
            map.fitBounds(bounds);

            document.getElementById("legend").classList.remove("hidden");
            initializeTransparency();
          })
          .catch(error => {
            console.log("error loading export tiles", error);
            showLoaderOnMap(null, false);
          });
      }

      // document.getElementById('paletteSelect').addEventListener('change', (event) => {
      //   updateRasterColor(event.target.value);
      //   updateLegend(event.target.value);
      // });
      

      function updateRasterColor(scaleName) {
        if (computeLayer && computeLayer._exportUid) {
          var uid = computeLayer._exportUid;
          var colormapForBackend = (typeof computePaletteFlipped !== 'undefined' && computePaletteFlipped) ? scaleName + '_r' : scaleName;
          if (typeof min !== 'undefined' && typeof max !== 'undefined' && min !== undefined && max !== undefined) {
            var newUrl = `/export-tile/${uid}/{z}/{x}/{y}?colormap=${colormapForBackend}&vmin=${min}&vmax=${max}`;
            computeLayer.setUrl(newUrl);
          }
        }
      }


      function updateLegend(paletteName) {
        const legend = document.getElementById('legend');
        const colorScale = colorScales[paletteName];
        const steps = 10;
        const stepValue = (max - min) / (steps - 1);
        const flipped = (typeof computePaletteFlipped !== 'undefined' && computePaletteFlipped);

        legend.innerHTML = '';

        // Title with minimize button
        const title = document.createElement('div');
        title.className = 'legend-title';
        title.innerHTML = '<span>Compute Output Layer</span><span class="legend-minimize-btn" id="legend-minimize" title="Minimize"><i class="fa-solid fa-minus"></i></span>';
        legend.appendChild(title);

        // Formula subtitle with pixel size
        var filterBtn = document.getElementById('select-button_export');
        var filterName = filterBtn ? filterBtn.querySelector('.truncate') : null;
        var filterLabel = (filterName && filterName.innerText.trim() !== 'Select Option') ? filterName.innerText.trim() : 'Custom';
        var pixelSize = getFinestResolution(export_params.bands, export_params.collection);
        var infoText = filterLabel + ' | ' + export_params.formula + (pixelSize ? ' | Pixel: ' + pixelSize + 'm' : '');
        var subtitle = document.createElement('div');
        subtitle.style.cssText = 'font-size:9px;color:#6b7280;margin-bottom:4px;';
        subtitle.textContent = infoText;
        legend.appendChild(subtitle);

        // Color bar container
        const bar = document.createElement('div');
        bar.className = 'legend-bar';
        bar.id = 'legend-bar-content';

        for (let i = 0; i < steps; i++) {
            const value = min + i * stepValue;
            const colorInput = flipped ? 1 - (i / (steps - 1)) : i / (steps - 1);
            const color = colorScale(colorInput);

            const legendItem = document.createElement('div');
            legendItem.className = 'legend-item';

            const colorBox = document.createElement('div');
            colorBox.className = 'legend-color';
            colorBox.style.backgroundColor = color;

            const labelText = document.createElement('span');
            labelText.textContent = value.toFixed(2);

            legendItem.appendChild(colorBox);
            legendItem.appendChild(labelText);
            bar.appendChild(legendItem);
        }

        legend.appendChild(bar);

        // Minimize toggle
        document.getElementById('legend-minimize').addEventListener('click', function() {
          var content = document.getElementById('legend-bar-content');
          if (content.style.display === 'none') {
            content.style.display = 'flex';
            this.innerHTML = '<i class="fa-solid fa-minus"></i>';
          } else {
            content.style.display = 'none';
            this.innerHTML = '<i class="fa-solid fa-plus"></i>';
          }
        });
    }


      //for updating the transparency of layers
      
      function setLayerTransparency(layerName, value) {
          const layers = {
            "liveLayer": liveLayer,
            "geojsonLayer": geojsonLayer,
            "computeLayer": computeLayer
          };
          // Add per-source bbox layers
          if (typeof sourceBboxLayers !== "undefined") {
            layers["analyzeBboxLayer"] = sourceBboxLayers.analyze;
            layers["downloadBboxLayer"] = sourceBboxLayers.download;
          }
          const layer = layers[layerName];
          if (layer) {
              if (layer.setOpacity) {
                  // For raster layers (e.g., imageOverlay)
                  layer.setOpacity(value / 100);
              } else if (layer.setStyle) {
                  // For vector layers (e.g., geoJSON)
                  layer.setStyle({ opacity: value / 100/*, fillOpacity: value / 100*/ });
              }
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
          // Add per-source bbox layers
          if (typeof sourceBboxLayers !== "undefined") {
            layers["analyzeBboxLayer"] = sourceBboxLayers.analyze;
            layers["downloadBboxLayer"] = sourceBboxLayers.download;
          }
          document.querySelectorAll('input[id^="transparency_"]').forEach(input => {
              const layerName = input.id.substring("transparency_".length);
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
              const layerName = this.id.substring("transparency_".length);
              const transparencyValue = this.value;
              setLayerTransparency(layerName, transparencyValue);
          });
      });
      
