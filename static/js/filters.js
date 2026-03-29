document.addEventListener('DOMContentLoaded', (event) => {
    document.querySelectorAll('.radio-action').forEach((radio) => {
      radio.addEventListener('change', function(event){
        analyze_checked = document.getElementById("analyze-data").checked;
        download_checked = document.getElementById("download-data").checked;
        console.log("changed");

        if(analyze_checked){
          document.getElementById("band-list-container").classList.add("hidden");
          document.getElementById("export-filter-option").classList.remove("hidden");
          document.getElementById("analyze-filters").classList.remove("hidden");
          document.getElementById('export-map-view-button').innerHTML = `<i class="fa-regular fa-eye"></i> Visualize and Export`;
        }
        else{
          document.getElementById("band-list-container").classList.remove("hidden");
          document.getElementById("export-filter-option").classList.add("hidden");
          document.getElementById("analyze-filters").classList.add("hidden");
          document.getElementById('export-map-view-button').innerHTML = `<i class="fas fa-download"></i> Download`;
        }
      })
    })
  })

    document
      .getElementById("sidebar-clear-button")
      .addEventListener("click", function () {
        document.getElementById("feature-list").innerHTML = '<label class="block text-sm font-medium text-gray-400 pt-4">Apply the Filter First!!!</label>';
        document.getElementById("display-image-count").innerHTML = `Images: `;

        document.getElementById("search-clear-button").click();   
        document.getElementById("export-clear-button").click();
      });

      document
      .getElementById("search-clear-button")
      .addEventListener("click", function () {
        if (geojsonLayer) {
          map.removeLayer(geojsonLayer);
        }
        if (highlightedLayer) {
          map.removeLayer(highlightedLayer);
        }
        if (liveLayer) {
          map.removeLayer(liveLayer);
        }
        setDefaultFilters();
        
        document.getElementById("sidebar-clear-button").click(); 
        document.getElementById("searchLayerSwitcher").classList.add("hidden");
        document.getElementById("searchBboxLayerSwitcher").classList.add("hidden");

        document.getElementById("operation_search").checked = true;
        document.getElementById("timeSeries_search").checked = false;
      })

      document
      .getElementById("export-clear-button")
      .addEventListener("click", function () {
        if (geojsonLayer) {
          map.removeLayer(geojsonLayer);
        }
        if (highlightedLayer) {
          map.removeLayer(highlightedLayer);
        }
        if (liveLayer) {
          map.removeLayer(liveLayer);
        }
        setDefaultFiltersExport();
        document.getElementById("sidebar-clear-button").click();
        document.getElementById("custom-formula-view_export").classList.add('hidden'); 
        document.getElementById("dropdownButtonBands").innerHTML = `<img src="static/img/select-icon.png" alt="" class="size-5 shrink-0 rounded-full mr-2">Select Bands`;

        document.getElementById("computeLayerSwitcher").classList.add("hidden");

        document.getElementById("select-button-bbox").innerHTML = `<span class="col-start-1 row-start-1 flex items-center gap-3 pr-6">
                    <i class="fa-regular fa-square"></i>
                    <span id = "selected-filter-value-bbox" class="block truncate text-gray-600">Map Window</span>
                  </span>
                  <svg class="col-start-1 row-start-1 size-5 self-center justify-self-end text-gray-500 sm:size-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
                    <path fill-rule="evenodd" d="M5.22 10.22a.75.75 0 0 1 1.06 0L8 11.94l1.72-1.72a.75.75 0 1 1 1.06 1.06l-2.25 2.25a.75.75 0 0 1-1.06 0l-2.25-2.25a.75.75 0 0 1 0-1.06ZM10.78 5.78a.75.75 0 0 1-1.06 0L8 4.06 6.28 5.78a.75.75 0 0 1-1.06-1.06l2.25-2.25a.75.75 0 0 1 1.06 0l2.25 2.25a.75.75 0 0 1 0 1.06Z" clip-rule="evenodd" />
                  </svg>`;

        export_params_bbox_changed = false;

        //clear drawn items and bbox
        if(drawnItems){
          drawnItems.clearLayers();
        }
        export_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
        document.getElementById("map-window-content").innerHTML = export_params.bbox;
        
        document.getElementById("operation").checked = true;
        document.getElementById("timeSeries").checked = false;
        document.getElementById("operation-container").classList.remove("hidden");

      })

    function setDefaultFilters(){
      // Set default dates

      var today = new Date().toISOString().split("T")[0];
      var lastYear = new Date();
      lastYear.setFullYear(lastYear.getFullYear() - 1);
      var lastYearDate = lastYear.toISOString().split("T")[0];

      var lastMonth = new Date(); 
      lastMonth.setMonth(lastMonth.getMonth() - 1); 
      lastMonthDate = lastMonth.toISOString().split("T")[0];


      document.getElementById("start-date").value = lastMonthDate;
      document.getElementById("end-date").value = today;

      document.getElementById("cloud-cover").value = "30";

      document.getElementById("select-button_search").innerHTML = `<span class="col-start-1 row-start-1 flex items-center gap-3 pr-6">
                    <img src="static/img/select-icon.png" alt="" class="size-5 shrink-0 rounded-full">
                    <span id = "selected-filter-value_search" class="block truncate">Select Option</span>
                  </span>`;

      document.getElementById("search-button").classList.add('bg-gray-500', 'pointer-events-none');
      document.getElementById("search-button").classList.remove('bg-blue-700');

      tile_params.collection = "sentinel-2-l2a";
    }
    setDefaultFilters();

    function setDefaultFiltersExport(){
      // Set default dates
      var today = new Date().toISOString().split("T")[0];
      var lastYear = new Date();
      lastYear.setFullYear(lastYear.getFullYear() - 1);
      var lastYearDate = lastYear.toISOString().split("T")[0];

      var lastMonth = new Date(); 
      lastMonth.setMonth(lastMonth.getMonth() - 1); 
      lastMonthDate = lastMonth.toISOString().split("T")[0];


      document.getElementById("start-date-export").value = lastMonthDate;
      document.getElementById("end-date-export").value = today;
      document.getElementById("select-button_export").innerHTML = `<span class="col-start-1 row-start-1 flex items-center gap-3 pr-6">
                    <img src="static/img/select-icon.png" alt="" class="size-5 shrink-0 rounded-full">
                    <span id = "selected-filter-value_search" class="block truncate">Select Option</span>
                  </span>`;

      document.getElementById("cloud-cover-export").value = "30";

      document.getElementById("export-map-view-button").classList.add('bg-gray-500', 'pointer-events-none');
      document.getElementById("export-map-view-button").classList.remove('bg-blue-700');

      document.getElementById("operation_menu").value = "median";

      export_params.collection = "sentinel-2-l2a";
    }
    setDefaultFiltersExport();



// Helper function to log date values and automatically tick smart filters if date range is high.
function handleDateChange(event) {
  const id = event.target.id;
  // const value = event.target.value;
  // console.log(`Changed: ${id} = ${value}`);

  if(id == 'start-date-export' || id == 'end-date-export'){
    var start_date_export = document.getElementById('start-date-export').value;
    var end_date_export = document.getElementById('end-date-export').value;

    const startDate = new Date(start_date_export);
    const endDate = new Date(end_date_export);

    const diffTime = endDate - startDate; // in milliseconds
    const diffDays = diffTime / (1000 * 60 * 60 * 24); // convert to days

    console.log(`Difference in days export: ${diffDays}`);

    if(diffDays > 90){
      document.getElementById("smart-filters").checked = true;
      showMessage('message', 30000, "Smart filters applied automatically since date filters exceed 90 days of date range. If you want all the images between this range, manually turn off smart filters below. No need to worry, it is just a message. This is due to our server limitation. ie to process lesser number of images.");
    }
    else{
      document.getElementById("smart-filters").checked = false;
    }

  }
  else{ //id should be start-date and end-date

    // var start_date = document.getElementById('start-date').value;
    // var end_date = document.getElementById('end-date').value;

    // const startDate = new Date(start_date);
    // const endDate = new Date(end_date);

    // const diffTime = endDate - startDate; // in milliseconds
    // const diffDays = diffTime / (1000 * 60 * 60 * 24); // convert to days

    // console.log(`Difference in days: ${diffDays}`);

    // if(diffDays > 90){

    // }
    
  }
}

// Add event listeners after DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  const dateInputs = [
    'start-date',
    'end-date',
    'start-date-export',
    'end-date-export'
  ];

  dateInputs.forEach(id => {
    const input = document.getElementById(id);
    if (input) {
      input.addEventListener('change', handleDateChange);
    }
  });
});
