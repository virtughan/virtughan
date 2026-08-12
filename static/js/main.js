//adjust container height start
document.addEventListener('DOMContentLoaded', function () {
    function adjustMainHeight() {
        const header = document.querySelector('header');
        const tabs = document.getElementById('filterTab');
        const info = document.getElementById('info');
        const tabPanels = document.querySelectorAll('.tab-scrollable-content');

        // Get whichever has the maximum height between the buttons at the bottom live and export tabs
        var buttons = document.querySelectorAll('.bottom-sticky-buttons');

        var maxHeight = 0;

        // Loop through the buttons to find the one with the highest height
        buttons.forEach(function(button) {
            var buttonHeight = button.offsetHeight;
            if (buttonHeight > maxHeight) {
                maxHeight = buttonHeight;
            }
        });

        var containerHeight = header.offsetHeight + tabs.offsetHeight + maxHeight + 70; // extra 70 added for bottom sticky contents

        // Check if the viewport is a tablet or mobile
        var isTabletOrMobile = window.innerWidth <= 1024;

        // Calculate the height based on the condition
        var percentageHeight = isTabletOrMobile ? 90 : 100; // Use 90% for tablets and mobile, 100% otherwise
        var heightCalculation = `calc(${percentageHeight}vh - ${containerHeight}px)`;

        tabPanels.forEach(function(tabPanel) {
            tabPanel.style.height = heightCalculation;
        });
    }

    // Initial check on page load
    adjustMainHeight();

    // Update on window resize
    window.addEventListener('resize', adjustMainHeight);
});
//adjust container height end


//leftbar tab start
document.addEventListener('DOMContentLoaded', function() {
    const tabs = document.querySelectorAll('.tab');
    const tabPanels = document.querySelectorAll('.tab-panel');

    tabs.forEach((tab, index) => {
      tab.addEventListener('click', () => {
        tabs.forEach(tab => tab.classList.remove('border-blue-500', 'text-blue-500'));
        tab.classList.add('border-blue-500', 'text-blue-500');
        tabPanels.forEach(panel => panel.classList.add('hidden'));
        const panelIndex = parseInt(tab.dataset.panel || index);
        tabPanels[panelIndex].classList.remove('hidden');

        // When Compute & Download tab is activated (panel index 2), validate button state
        if (panelIndex === 2) {
          const exportBtn = document.getElementById("export-map-view-button");
          const analyzeChecked = document.getElementById("analyze-data").checked;
          if (exportBtn) {
            let shouldEnable = false;
            if (analyzeChecked) {
              const selectBtn = document.getElementById("select-button_export");
              const filterText = selectBtn ? selectBtn.querySelector('.truncate') : null;
              shouldEnable = filterText && filterText.innerText.trim() !== "Select Option";
            } else {
              shouldEnable = typeof export_params !== "undefined" && export_params && export_params.bands_list && export_params.bands_list.length > 0;
            }
            if (shouldEnable) {
              exportBtn.classList.remove('bg-gray-500', 'pointer-events-none');
              exportBtn.classList.add('bg-blue-700');
            } else {
              exportBtn.classList.add('bg-gray-500', 'pointer-events-none');
              exportBtn.classList.remove('bg-blue-700');
            }
          }
        }
      });
    });

    // Activate the first tab by default
    tabs[0].classList.add('border-blue-500', 'text-blue-500');
    tabPanels[0].classList.remove('hidden');

  });

  //leftbar tab end

const COLLECTION_DEFAULTS = {
  "sentinel-2-l2a": {
    search: { bands: "visual", formula: "visual" },
    export: { bands: "red,nir", formula: "(nir - red) / (nir + red)" },
  },
  "landsat-c2-l2": {
    search: { bands: "red", formula: "red" },
    export: { bands: "red,nir08", formula: "(nir08 - red) / (nir08 + red)" },
  },
  "sentinel-1-rtc": {
    search: { bands: "vv", formula: "10 * log10(vv)" },
    export: { bands: "vv,vh", formula: "10 * log10(vv / vh)" },
  },
};

const COLLECTION_BANDS_FALLBACK = {
  "sentinel-2-l2a": [
    "red", "green", "blue", "nir", "swir22", "rededge2", "rededge3", "rededge1",
    "swir16", "wvp", "nir08", "aot", "coastal", "nir09", "scl", "visual",
  ],
  "landsat-c2-l2": ["red", "green", "blue", "nir08", "swir16", "swir22", "coastal", "lwir11"],
  "sentinel-1-rtc": ["vv", "vh", "hh", "hv"],
};

const COLLECTION_LABELS = {
  "sentinel-2-l2a": "Sentinel-2",
  "landsat-c2-l2": "Landsat",
  "sentinel-1-rtc": "Sentinel-1",
};

const COLLECTION_STATE = {
  search: "sentinel-2-l2a",
  export: "sentinel-2-l2a",
};

let collectionMetadata = {};

function getBandNames(collection) {
  const collectionBands = collectionMetadata?.[collection]?.bands;
  if (collectionBands) {
    return Object.keys(collectionBands);
  }
  return COLLECTION_BANDS_FALLBACK[collection] || COLLECTION_BANDS_FALLBACK["sentinel-2-l2a"];
}

function getFinestResolution(bandsStr, collection) {
  if (!bandsStr || !collection) return '';
  var bands = bandsStr.split(',').map(function(b) { return b.trim(); });
  var bandData = collectionMetadata?.[collection]?.bands || {};
  var finest = null;
  bands.forEach(function(band) {
    var info = bandData[band];
    if (info && info.resolution) {
      if (finest === null || info.resolution < finest) {
        finest = info.resolution;
      }
    }
  });
  return finest || '';
}

function renderBandCheckboxes(collection) {
  const container = document.getElementById("list_of_bands");
  if (!container) {
    return;
  }

  const bandNames = getBandNames(collection);
  container.innerHTML = bandNames
    .map((bandName) => {
      const label = bandName.toUpperCase();
      return `<label class="flex items-center px-3 py-2"><input type="checkbox" value="${label}" class="form-checkbox h-4 w-4 text-blue-600 band-checkbox"><span class="ml-2 text-gray-700 text-sm">${label}</span></label>`;
    })
    .join("");

  container.querySelectorAll('.band-checkbox').forEach((checkbox) => {
    checkbox.addEventListener('change', function () {
      const selectedOptions = Array.from(container.querySelectorAll('.band-checkbox'))
        .filter((chk) => chk.checked)
        .map((chk) => chk.value);
      const dropdownButton = document.getElementById('dropdownButtonBands');
      if (dropdownButton) {
        dropdownButton.innerHTML = selectedOptions.length > 0
          ? selectedOptions.join(', ')
          : `<img src="static/img/select-icon.png" alt="" class="size-5 shrink-0 rounded-full mr-2">Select Bands`;
      }
      if (export_params) {
        export_params.bands_list = selectedOptions.length > 0 ? selectedOptions.join(',').toLowerCase() : "";
      }
      // Enable/disable export button based on band selection (for download mode)
      const exportBtn = document.getElementById("export-map-view-button");
      if (exportBtn && selectedOptions.length > 0) {
        exportBtn.classList.remove('bg-gray-500', 'pointer-events-none');
        exportBtn.classList.add('bg-blue-700');
      } else if (exportBtn && selectedOptions.length === 0) {
        const analyzeChecked = document.getElementById("analyze-data").checked;
        if (!analyzeChecked) {
          exportBtn.classList.add('bg-gray-500', 'pointer-events-none');
          exportBtn.classList.remove('bg-blue-700');
        }
      }
    });
  });
}

function populateBandSelectors(collection) {
  const bandNames = getBandNames(collection);
  const container = document.getElementById('formula-bands-container');
  if (!container) return;

  // Store available bands for use by addBandRow
  container.dataset.availableBands = JSON.stringify(bandNames);

  const calculatorLabel = document.getElementById('calculator_bands');
  if (calculatorLabel) {
    calculatorLabel.textContent = `${COLLECTION_LABELS[collection] || collection} Bands`;
  }

  // Populate band reference panel
  const refList = document.getElementById('band-reference-list');
  if (refList) {
    const bandData = collectionMetadata?.[collection]?.bands || {};
    refList.innerHTML = bandNames.map(name => {
      const info = bandData[name] || {};
      const res = info.resolution ? `${info.resolution}m` : '';
      const wl = info.wavelength || '';
      const desc = info.description || '';
      const meta = [wl, res].filter(Boolean).join(' · ');
      return `<div class="px-2 py-1 rounded hover:bg-gray-100 border-b border-gray-50">
        <span class="font-medium text-gray-800">${name}</span>
        ${meta ? `<span class="text-gray-400 ml-1">${meta}</span>` : ''}
        ${desc ? `<span class="text-gray-400 ml-1 text-[10px]">${desc}</span>` : ''}
      </div>`;
    }).join('');
  }

  // Rebuild band rows from current export_params.bands
  rebuildFormulaBandRows();
}

function rebuildFormulaBandRows() {
  const container = document.getElementById('formula-bands-container');
  if (!container) return;

  const bandNames = JSON.parse(container.dataset.availableBands || '[]');
  const currentBands = export_params.bands ? export_params.bands.split(',').map(b => b.trim()).filter(Boolean) : [];

  // Filter out bands that don't exist in the current collection
  const validBands = currentBands.filter(b => bandNames.includes(b));

  container.innerHTML = '';
  if (validBands.length === 0) {
    addBandRow(container, bandNames, '');
  } else {
    validBands.forEach(band => addBandRow(container, bandNames, band));
  }

  // Update export_params.bands to only valid bands
  export_params.bands = validBands.join(',');
}

function addBandRow(container, bandNames, selectedValue) {
  const row = document.createElement('div');
  row.className = 'flex items-center gap-2 mb-2 band-row';

  const select = document.createElement('select');
  select.className = 'w-full rounded-md border border-gray-300 bg-white px-2 py-1 text-sm text-gray-700 shadow-sm focus:border-blue-500 focus:outline-none band-select';

  // Only show bands not already used in other rows
  const usedBands = getUsedBands(container, null);
  const availableForThis = bandNames.filter(b => !usedBands.includes(b) || b === selectedValue);

  select.innerHTML = '<option value="">Select Band</option>' +
    availableForThis.map(b => `<option value="${b}" ${b === selectedValue ? 'selected' : ''}>${b.toUpperCase()}</option>`).join('');

  select.addEventListener('change', function() {
    updateBandsBox();
    refreshBandOptions(container, bandNames);
  });

  const removeBtn = document.createElement('button');
  removeBtn.type = 'button';
  removeBtn.className = 'text-red-400 hover:text-red-600 text-sm px-2';
  removeBtn.innerHTML = '<i class="fas fa-times"></i>';
  removeBtn.addEventListener('click', function() {
    if (container.querySelectorAll('.band-row').length > 1) {
      row.remove();
      updateBandsBox();
      refreshBandOptions(container, bandNames);
    }
  });

  row.appendChild(select);
  row.appendChild(removeBtn);
  container.appendChild(row);
}

function getUsedBands(container, excludeSelect) {
  const used = [];
  container.querySelectorAll('.band-select').forEach(s => {
    if (s !== excludeSelect && s.value) used.push(s.value);
  });
  return used;
}

function refreshBandOptions(container, bandNames) {
  container.querySelectorAll('.band-select').forEach(select => {
    const currentValue = select.value;
    const usedByOthers = getUsedBands(container, select);
    const available = bandNames.filter(b => !usedByOthers.includes(b));

    select.innerHTML = '<option value="">Select Band</option>' +
      available.map(b => `<option value="${b}" ${b === currentValue ? 'selected' : ''}>${b.toUpperCase()}</option>`).join('');
  });
}

function updateFormulaBandsUI() {
  const container = document.getElementById('formula-bands-container');
  if (!container) return;
  rebuildFormulaBandRows();
}

function applyCollectionDefaults(scope, collection) {
  const defaults = COLLECTION_DEFAULTS[collection] || COLLECTION_DEFAULTS['sentinel-2-l2a'];
  if (scope === 'search') {
    tile_params.collection = collection;
    tile_params.mode = collection === 'sentinel-1-rtc' ? getSelectedMode(scope) : null;
    tile_params.bands = defaults.search.bands;
    tile_params.formula = defaults.search.formula;
  } else {
    export_params.collection = collection;
    export_params.mode = collection === 'sentinel-1-rtc' ? getSelectedMode(scope) : null;
    export_params.bands = defaults.export.bands;
    export_params.formula = defaults.export.formula;
    export_params.bands_list = '';
    const dropdownButton = document.getElementById('dropdownButtonBands');
    if (dropdownButton) {
      dropdownButton.innerHTML = `<img src="static/img/select-icon.png" alt="" class="size-5 shrink-0 rounded-full mr-2">Select Bands`;
    }
    const bandList = document.getElementById('list_of_bands');
    if (bandList) {
      bandList.querySelectorAll('input.band-checkbox').forEach((checkbox) => {
        checkbox.checked = false;
      });
    }
  }

  // Always update the formula band selectors with the current collection's bands
  populateBandSelectors(collection);
  renderBandCheckboxes(collection);
  updateCollectionSpecificUI(scope, collection);

  if (scope === 'export' && typeof updateBandsBox === 'function') {
    updateBandsBox();
  }
}

function getSelectedCollection(scope) {
  const select = document.getElementById(`satellite-collection-${scope}`);
  return select?.value || COLLECTION_STATE[scope] || 'sentinel-2-l2a';
}

function getSelectedMode(scope) {
  const select = document.getElementById(`sentinel1-mode-${scope}`);
  return select?.value || 'IW';
}

function updateCollectionSpecificUI(scope, collection) {
  const isSentinel1 = collection === 'sentinel-1-rtc';
  document.getElementById(`sentinel1-mode-container-${scope}`)?.classList.toggle('hidden', !isSentinel1);
  document.getElementById(`cloud-cover-container-${scope}`)?.classList.toggle('hidden', isSentinel1);

  const listSelector = scope === 'search' ? '#select-list_search' : '#select-list_export';
  document.querySelectorAll(`${listSelector} .template-filters`).forEach((item) => {
    const isRadarTemplate = item.classList.contains('radar-template');
    const templateValue = item.querySelector('.template-filters-value')?.getAttribute('value');
    const isUnsupportedVisual = collection === 'landsat-c2-l2' && templateValue === 'visual';
    const shouldHide = isSentinel1 ? !isRadarTemplate : isRadarTemplate || isUnsupportedVisual;
    item.classList.toggle('hidden', shouldHide);
  });

  const operationSelect = document.getElementById(
    scope === 'search' ? 'operation_menu_search' : 'operation_menu',
  );
  operationSelect?.querySelectorAll('.optical-operation').forEach((option) => {
    option.hidden = isSentinel1;
    option.disabled = isSentinel1;
  });
  if (isSentinel1 && !['median', 'mean'].includes(operationSelect?.value)) {
    operationSelect.value = 'median';
    if (scope === 'search') {
      tile_params.operation = 'median';
    } else {
      export_params.operation = 'median';
    }
  }
}

function resetCollectionFilterSelection(scope) {
  const selectButton = document.getElementById(`select-button_${scope}`);
  const selectedLabel = selectButton?.querySelector('.truncate');
  if (selectedLabel) {
    selectedLabel.textContent = 'Select Option';
  }

  const listSelector = scope === 'search' ? '#select-list_search' : '#select-list_export';
  document.querySelectorAll(`${listSelector} .template-filters`).forEach((item) => {
    item.classList.remove('bg-indigo-600', 'text-white', 'font-semibold');
    item.querySelector('span')?.classList.remove('text-white');
    item.querySelector('svg')?.classList.add('hidden');
  });

  const actionButton = document.getElementById(
    scope === 'search' ? 'search-button' : 'export-map-view-button',
  );
  actionButton?.classList.add('bg-gray-500', 'pointer-events-none');
  actionButton?.classList.remove('bg-blue-700');
}

async function loadCollectionMetadata() {
  try {
    const response = await fetch('/collections');
    collectionMetadata = await response.json();
  } catch (error) {
    console.warn('Unable to load collection metadata, using fallback bands.', error);
  }
}

function setCollectionBySelect(select) {
  const scope = select.dataset.scope;
  const collection = select.value;
  const collectionChanged = COLLECTION_STATE[scope] !== collection;
  COLLECTION_STATE[scope] = collection;

  applyCollectionDefaults(scope, collection);
  if (collectionChanged) {
    resetCollectionFilterSelection(scope);
  }
}

//band box change - advance filter (formula) start
//band box change - advance filter (formula) start
function updateBandsBox() {
    const container = document.getElementById('formula-bands-container');
    if (!container) return;

    const selects = container.querySelectorAll('.band-select');
    const selectedBands = [];
    selects.forEach(select => {
      if (select.value) selectedBands.push(select.value);
    });

    export_params.bands = selectedBands.join(',');

    const mappedBandsList = document.getElementById("mapped-bands");
    if (mappedBandsList) {
      mappedBandsList.innerHTML = selectedBands.map(band => `<li class="attribute-item hover:bg-gray-100 p-1">${band}</li>`).join('');
    }

    // Check for resolution mismatch
    var note = document.getElementById('resolution-mismatch-note');
    if (note && selectedBands.length > 1) {
      var collection = export_params.collection || 'sentinel-2-l2a';
      var bandData = collectionMetadata?.[collection]?.bands || {};
      var resolutions = selectedBands.map(function(b) { return bandData[b]?.resolution; }).filter(Boolean);
      var unique = [...new Set(resolutions)];
      if (unique.length > 1) {
        var finest = Math.min(...unique);
        document.getElementById('finest-res-value').textContent = finest;
        note.classList.remove('hidden');
      } else {
        note.classList.add('hidden');
      }
    } else if (note) {
      note.classList.add('hidden');
    }
}

// Add Band button handler
document.addEventListener('click', function(event) {
  if (event.target && (event.target.id === 'add-band-btn' || event.target.closest('#add-band-btn'))) {
    const container = document.getElementById('formula-bands-container');
    if (!container) return;
    const bandNames = JSON.parse(container.dataset.availableBands || '[]');
    if (container.querySelectorAll('.band-row').length >= 12) return;
    // Don't add if all bands are already used
    const usedBands = getUsedBands(container, null);
    if (usedBands.length >= bandNames.length) return;
    addBandRow(container, bandNames, '');
    refreshBandOptions(container, bandNames);
  }
});
//band box change - advance filter (formula) end

document.addEventListener('DOMContentLoaded', async function () {
  await loadCollectionMetadata();

  document.querySelectorAll('.satellite-collection-select').forEach((select) => {
    select.addEventListener('change', function () {
      setCollectionBySelect(this);
    });
    setCollectionBySelect(select);
  });

  document.querySelectorAll('.sentinel1-mode-select').forEach((select) => {
    select.addEventListener('change', function () {
      const scope = this.dataset.scope;
      if (scope === 'search') {
        tile_params.mode = this.value;
      } else {
        export_params.mode = this.value;
      }
    });
  });
});



//buttons and filters start

document.addEventListener('DOMContentLoaded', function() {
    const dropdowns = document.querySelectorAll('.relative.mt-2');
  
    dropdowns.forEach(dropdown => {
      const selectButton = dropdown.querySelector('button[type="button"]');
      const selectList = dropdown.querySelector('ul');
      const listItems = selectList.querySelectorAll('[role="option"]');
  
      selectButton.addEventListener('click', function() {
        const expanded = selectButton.getAttribute('aria-expanded') === 'true' || false;
        selectButton.setAttribute('aria-expanded', !expanded);
        selectList.classList.toggle('hidden');
      });
  
      listItems.forEach(item => {
        item.addEventListener('click', function() {
          if (this.closest('#select-list_search')) {
            document.getElementById("search-button").classList.remove('bg-gray-500', 'pointer-events-none');
            document.getElementById("search-button").classList.add('bg-blue-700');
          }
          else if (this.closest('#select-list_export')) {
            document.getElementById("export-map-view-button").classList.remove('bg-gray-500', 'pointer-events-none');
            document.getElementById("export-map-view-button").classList.add('bg-blue-700');
          }
          //activate visualize/search button
          // console.log("entered here");
          if (this.closest('#select-list-bbox')) {
            // console.log("entered inside");
            // console.log(drawToolbar);
            if (drawToolbar) {
              drawToolbar.style.display = 'none';
            }
            // if(drawnItems){
            //   map.removeLayer(drawnItems);
            // }
          }
  
          document.getElementById("formulaHeading").classList.add('hidden'); 
          document.getElementById("formulaHeading-export").classList.add('hidden'); 
  
  
          // Update the button text and image/icon with the selected item's data
          const selectedItemId = item.id;
          const selectedItemText = item.querySelector('.truncate').innerText;
          const selectedItemIcon = item.querySelector('img, i'); // Select either img or i element
  
          // Update button text
          selectButton.querySelector('.truncate').innerText = selectedItemText;
  
          // Update button image/icon
          const buttonIcon = selectButton.querySelector('img, i'); // Select either img or i element
          if (selectedItemIcon.tagName === 'IMG') {
            buttonIcon.src = selectedItemIcon.src;
          } else if (selectedItemIcon.tagName === 'I') {
            buttonIcon.className = selectedItemIcon.className;
          }
  
          // Update the selected class
          listItems.forEach(i => {
            i.classList.remove('bg-indigo-600', 'text-white', 'font-semibold');
            i.querySelector('span').classList.remove('text-white');
          });
          item.classList.add('bg-indigo-600', 'text-white', 'font-semibold');
          item.querySelector('span').classList.add('text-white');
  
          // Show the checkmark for the selected item
          const checkIcon = item.querySelector('svg');
          listItems.forEach(i => i.querySelector('svg').classList.add('hidden'));
          checkIcon.classList.remove('hidden');
  
          // Close the select list
          selectButton.setAttribute('aria-expanded', false);
          selectList.classList.add('hidden');
  
          // Show/Hide content based on the selected option
          const coords = document.getElementById('map-window-content');
          const drawBBoxOption = document.getElementById('draw-bbox-option');
          const uploadBBoxFileOption = document.getElementById('upload-bbox-file-option');
  
          // Hide all sections first
          // coords.classList.add('hidden');
          drawBBoxOption.classList.add('hidden');
          uploadBBoxFileOption.classList.add('hidden');
  
          // Show the corresponding section based on the selected item
          if (selectedItemId === 'map-window-bbox') {
            coords.classList.remove('hidden');
  
            if(Object.keys(drawnItems._layers).length > 0){
              // console.log(drawnItems);
              if(rectangle){
                map.removeLayer(rectangle);
              }
              map.removeLayer(drawnItems);
              export_params_bbox_changed = false;
            }
            //reset bbox html
            export_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
            document.getElementById("map-window-content").innerHTML = export_params.bbox;
          } else if (selectedItemId === 'draw-aoi-on-map') {
            // console.log("fired");
            // coords.classList.add('hidden');
            drawBBoxOption.classList.remove('hidden');
            if (drawnItems) {
              drawnItems.clearLayers();
              map.addLayer(drawnItems);
            }
            if (rectangle) {
              map.removeLayer(rectangle);
              rectangle = null;
            }
            export_params_bbox_changed = false;
            export_params.bbox = `${bounds.getWest()},${bounds.getSouth()},${bounds.getEast()},${bounds.getNorth()}`;
            document.getElementById("map-window-content").innerHTML = export_params.bbox;
          } else if (selectedItemId === 'upload-file-bbox') {
            coords.classList.add('hidden');
            uploadBBoxFileOption.classList.remove('hidden');
          }
        });
      });
  
      document.addEventListener('click', function(event) {
        if (!dropdown.contains(event.target)) {
          selectButton.setAttribute('aria-expanded', false);
          selectList.classList.add('hidden');
        }
      });
    });
  });
  
  //if template provided options clicked eg. NDVI, NDWI
  document.querySelectorAll('.template-filters').forEach(function(item) {
      item.addEventListener('click', function() {
          const templateText = item.querySelector('.template-filters-value').getAttribute('value');
          // console.log(templateText); 
          var param;
          //check if dropwn inside export is clicked or search is clicked
          if (this.closest('#select-list_export')) {
            // console.log("yes this is export");
            param = export_params;
          }
          else{
            // console.log("no this is search");
            param = tile_params;
          }
  
        if(templateText == "NDVI"){
          const nirBand = param.collection === 'landsat-c2-l2' ? 'nir08' : 'nir';
          param.formula = `(${nirBand} - red) / (${nirBand} + red)`;
          param.bands = `red,${nirBand}`;
        }
        else if(templateText == "NDWI"){
          const nirBand = param.collection === 'landsat-c2-l2' ? 'nir08' : 'nir';
          param.formula = `(green - ${nirBand}) / (green + ${nirBand})`;
          param.bands = `${nirBand},green`;
        }
        else if(templateText == "NDBI"){
          const nirBand = param.collection === 'landsat-c2-l2' ? 'nir08' : 'nir';
          param.formula = `(swir16 - ${nirBand}) / (swir16 + ${nirBand})`;
          param.bands = `swir16,${nirBand}`;
        }
        else if(templateText == "NDSI"){
          param.formula = '(green - swir16) / (green + swir16)';
          param.bands = 'green,swir16';
        }
        else if(templateText == "SAVI"){
          const nirBand = param.collection === 'landsat-c2-l2' ? 'nir08' : 'nir';
          param.formula = `1.5 * (${nirBand} - red) / (${nirBand} + red + 0.5)`;
          param.bands = `red,${nirBand}`;
        }
        else if(templateText == "EVI"){
          const nirBand = param.collection === 'landsat-c2-l2' ? 'nir08' : 'nir';
          param.formula = `2.5 * (${nirBand} - red) / (${nirBand} + 6*red - 7.5*blue + 1)`;
          param.bands = `red,${nirBand},blue`;
        }
        else if(templateText == "moisture"){
          param.formula = '(nir08 - swir16) / (nir08 + swir16)';
          param.bands = 'nir08,swir16';
        }
        else if(templateText == "visual"){
          const visBand = param.collection === 'landsat-c2-l2' ? 'red' : 'visual';
          param.formula = visBand;
          param.bands = visBand;
        }
        else if(templateText == "S1_VV_DB"){
          param.formula = '10 * log10(vv)';
          param.bands = 'vv';
        }
        else if(templateText == "S1_VV_VH_DB"){
          param.formula = '10 * log10(vv / vh)';
          param.bands = 'vv,vh';
        }

        // Update formula band UI if export was changed
        if (param === export_params && typeof updateFormulaBandsUI === 'function') {
          updateFormulaBandsUI();
        }
        
      });
  });
  //buttons and filters end


  //loader script start
  function startLoader(divId) {
    const targetDiv = document.getElementById(divId);
    targetDiv.style.position = 'relative';
    if (!targetDiv.querySelector('.html-loader')) {
      const loaderDiv = document.createElement('div');
      loaderDiv.classList.add('html-loader');
      targetDiv.appendChild(loaderDiv);
    }
    targetDiv.querySelector('.html-loader').style.display = 'block'; // Show loader
  }

  // Function to stop the new loader for a specific div
  function stopLoader(divId) {
    const targetDiv = document.getElementById(divId);
    const loader = targetDiv.querySelector('.html-loader');
    if (loader) {
      loader.style.display = 'none'; // Hide loader
    }
  }
  //loader script end


  // Function to handle icon clicks
function handleInfoClick(event) {
  const title = event.target.title;
  // console.log('Info clicked:', title);
  // You can show a tooltip, modal, toast, etc. here
  showMessage('message', 30000, title);
}

// Wait until DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  const infoIcons = document.querySelectorAll('.info-icons');
  infoIcons.forEach(icon => {
    icon.style.cursor = 'pointer';
    icon.addEventListener('click', handleInfoClick);
  });
});

  
      
