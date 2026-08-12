const resultSourceState = {
  search: null,
  analyze: null,
  download: null,
};

let activeResultSource = null;

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getResultSourceLabel(source) {
  if (source === "search") return "Tiles";
  if (source === "analyze") return "Compute";
  if (source === "download") return "Download";
  return "None";
}

function getImagesBboxLabel(source) {
  if (source === "search") return "Images Bbox Search";
  if (source === "analyze") return "Images Bbox Analyze";
  if (source === "download") return "Images Bbox Download";
  return "Images Bbox";
}

function getClearModalTitle(source) {
  return `Clear ${getResultSourceLabel(source)} results?`;
}

function getClearModalMessage(source) {
  return `Are you sure you want to clear the ${getResultSourceLabel(source)} results?`;
}

function getResultContainer() {
  return document.getElementById("feature-list");
}

function getResultCountLabel() {
  return document.getElementById("display-image-count");
}

function getResultActiveLabel() {
  return document.getElementById("result-active-source");
}

function getResultSwitcher() {
  return document.getElementById("result-source-switcher");
}

function getClearModal() {
  return document.getElementById("clear-confirm-modal");
}

function getClearModalTitleLabel() {
  return document.getElementById("clear-confirm-title");
}

function getClearModalMessageLabel() {
  return document.getElementById("clear-confirm-message");
}

function updateImagesBboxLabel(source) {
  // No longer needed with per-source bbox labels, kept for backward compat
}

function updateLayerCountSummary() {
  const searchCount = countLayersForSource("search");
  const analyzeCount = countLayersForSource("analyze");
  const downloadCount = countLayersForSource("download");

  const searchEl = document.getElementById("layer-count-search");
  const analyzeEl = document.getElementById("layer-count-analyze");
  const downloadEl = document.getElementById("layer-count-download");

  if (searchEl) searchEl.textContent = `Tiles (${searchCount})`;
  if (analyzeEl) analyzeEl.textContent = `Compute (${analyzeCount})`;
  if (downloadEl) downloadEl.textContent = `Download (${downloadCount})`;
}

function countLayersForSource(source) {
  let count = 0;
  if (source === "search") {
    if (typeof liveLayer !== "undefined" && liveLayer && map && map.hasLayer(liveLayer)) count++;
    // geojsonLayer is the bbox layer for search - count it via checkbox only
    const bboxCheck = document.getElementById("search_bbox_layer");
    if (bboxCheck && bboxCheck.checked) count++;
  } else if (source === "analyze") {
    if (typeof computeLayer !== "undefined" && computeLayer && map && map.hasLayer(computeLayer)) count++;
    const bboxCheck = document.getElementById("analyze_bbox_layer");
    if (bboxCheck && bboxCheck.checked) count++;
  } else if (source === "download") {
    const bboxCheck = document.getElementById("download_bbox_layer");
    if (bboxCheck && bboxCheck.checked) count++;
  }
  return count;
}

function updateLayerSectionsForSource(source, hasResults) {
  const layerSwitcherContainer = document.getElementById("layerSwitcherContainer");
  const searchLayerSwitcher = document.getElementById("searchLayerSwitcher");
  const searchBboxLayerSwitcher = document.getElementById("searchBboxLayerSwitcher");
  const analyzeBboxLayerSwitcher = document.getElementById("analyzeBboxLayerSwitcher");
  const downloadBboxLayerSwitcher = document.getElementById("downloadBboxLayerSwitcher");
  const computeLayerSwitcher = document.getElementById("computeLayerSwitcher");
  const downloadLayerSwitcher = document.getElementById("downloadLayerSwitcher");

  const showSearchLayers = source === "search" && hasResults;
  const showAnalyzeLayers = source === "analyze" && hasResults;
  const showDownloadLayers = source === "download" && hasResults;

  // layerSwitcherContainer should be visible if ANY source has active content or liveLayer is on map
  var liveLayerOnMap = (typeof liveLayer !== "undefined" && liveLayer && typeof map !== "undefined" && map.hasLayer(liveLayer));
  var hasAnyContent = resultSourceState.search || resultSourceState.analyze || resultSourceState.download || liveLayerOnMap;
  if (layerSwitcherContainer) {
    layerSwitcherContainer.classList.toggle("hidden", !hasAnyContent);
  }

  // Search layers: show if active source is search AND (has results OR liveLayer is on map)
  var liveLayerActive = (typeof liveLayer !== "undefined" && liveLayer && typeof map !== "undefined" && map.hasLayer(liveLayer));
  if (searchLayerSwitcher) {
    searchLayerSwitcher.classList.toggle("hidden", !(showSearchLayers || (source === "search" && liveLayerActive)));
  }
  if (searchBboxLayerSwitcher) {
    searchBboxLayerSwitcher.classList.toggle("hidden", !(showSearchLayers));
  }

  // Bbox layers for analyze/download: toggle based on active source
  if (analyzeBboxLayerSwitcher) {
    analyzeBboxLayerSwitcher.classList.toggle("hidden", !showAnalyzeLayers);
  }
  if (downloadBboxLayerSwitcher) {
    downloadBboxLayerSwitcher.classList.toggle("hidden", !showDownloadLayers);
  }

  // computeLayerSwitcher: only visible when analyze is the active dropdown
  if (computeLayerSwitcher) {
    computeLayerSwitcher.classList.toggle("hidden", source !== "analyze");
  }

  // downloadLayerSwitcher: only visible when download is the active dropdown
  if (downloadLayerSwitcher) {
    downloadLayerSwitcher.classList.toggle("hidden", source !== "download");
  }

  updateLayerCountSummary();
}

function normalizeItems(payload) {
  if (!payload || !Array.isArray(payload.items)) {
    return [];
  }
  return payload.items;
}

function renderSceneList(items) {
  return items
    .map((feature, index) => {
      const datetime = feature?.properties?.datetime || "Unknown date";
      const cloudCover = feature?.properties?.["eo:cloud_cover"];
      const acquisitionMode = feature?.properties?.["sar:instrument_mode"];
      const sceneMetadata = cloudCover === undefined
        ? `<i class="fa-solid fa-satellite-dish"></i> ${escapeHtml(acquisitionMode || "SAR")}`
        : `<i class="fa-solid fa-cloud"></i> ${escapeHtml(`${parseInt(cloudCover, 10)} %`)}`;
      return `
        <ul role="list" class="divide-y divide-gray-100">
          <li id="result_list_${index}" data-result-index="${index}" class="result-list-items flex justify-between gap-x-6 py-5 hover:bg-gray-100 transition-colors duration-300 cursor-pointer">
            <div class="flex min-w-0 items-start gap-x-4">
              <img class="size-12 flex-none rounded-full bg-gray-50" src="static/img/satellite-basemap.png" alt="">
              <div class="min-w-0 flex-auto">
                <p class="text-sm/6 font-semibold text-gray-900">${escapeHtml(feature?.id || "Unknown scene")}</p>
                <p class="mt-1 truncate text-xs/5 text-gray-500">${escapeHtml(datetime)}</p>
              </div>
            </div>
            <div class="hidden shrink-0 sm:flex sm:flex-col sm:items-end">
              <p class="mt-auto text-xs/5 text-gray-400">${sceneMetadata}</p>
            </div>
          </li>
        </ul>
      `;
    })
    .join("");
}

function wireSceneResultInteractions(items) {
  const listItems = document.querySelectorAll(".result-list-items");
  listItems.forEach((element, index) => {
    const feature = items[index];
    if (!feature) {
      return;
    }

    element.addEventListener("mouseleave", function (event) {
      if (typeof highlightedLayer !== "undefined" && Object.keys(highlightedLayer._layers || {}).length > 0) {
        const rowId = event.currentTarget?.id;
        if (clickedResultList === false && previousListMouseIn != rowId) {
          map.closePopup();
          highlightedLayer.clearLayers();
        } else if (previousListMouseIn == rowId) {
          map.removeLayer(highlightedLayer);
        }
      }
      previousListMouseIn = event.currentTarget?.id;
    });

    element.addEventListener("mouseenter", function () {
      if (typeof highlightedLayer !== "undefined" && Object.keys(highlightedLayer._layers || {}).length > 0) {
        map.closePopup();
        highlightedLayer.clearLayers();
      }
      const hoveredLayer = createLayer(feature);
      highlightedLayer.addLayer(hoveredLayer);
      hoveredLayer.bindPopup(createPopup(feature));
      highlightedLayer.addTo(map);
      clickedResultList = false;
    });

    element.addEventListener("click", function () {
      if (highlightedLayer.getLayers()[0]) {
        highlightedLayer.getLayers()[0].openPopup();
        clickedResultList = true;
      }
    });
  });
}

function renderFileList(items) {
  return items
    .map((file, index) => {
      const name = typeof file === "string" ? file : file.name;
      const size = typeof file === "string" ? null : file.size;
      const sizeLabel = typeof size === "number" ? `${(size / 1024).toFixed(1)} KB` : "";
      const ext = (name || "").split(".").pop().toLowerCase();
      const icon = ext === "png" || ext === "jpg" || ext === "jpeg" ? "fa-image" : ext === "zip" ? "fa-file-zipper" : "fa-file";
      return `
        <ul role="list" class="divide-y divide-gray-100">
          <li id="result_list_${index}" class="result-list-items flex flex-col gap-2 rounded-md py-4 px-2 hover:bg-gray-100 transition-colors duration-300 cursor-pointer">
            <div class="flex min-w-0 items-start gap-x-4">
              <div class="size-12 flex-none rounded-full bg-gray-100 text-gray-600 flex items-center justify-center">
                <i class="fa-solid ${icon}"></i>
              </div>
              <div class="min-w-0 flex-auto">
                <p class="text-sm/6 font-semibold text-gray-900 break-words">${escapeHtml(name || "Unnamed file")}</p>
                <p class="mt-1 truncate text-xs/5 text-gray-500">${escapeHtml(sizeLabel)}</p>
              </div>
            </div>
            <div class="flex items-center justify-between text-xs text-gray-500 pl-16">
              <span>${escapeHtml(ext.toUpperCase())}</span>
              <span class="text-gray-400">Available output</span>
            </div>
          </li>
        </ul>
      `;
    })
    .join("");
}

function renderResultPayload(source, payload) {
  const container = getResultContainer();
  const countLabel = getResultCountLabel();
  const activeLabel = getResultActiveLabel();
  const items = normalizeItems(payload);
  const hasResults = Boolean(payload && items.length > 0);

  if (!container || !countLabel) {
    return;
  }

  if (!hasResults) {
    container.innerHTML = '<label class="block text-sm font-medium text-gray-400 pt-4">No results available yet.</label>';
    countLabel.innerHTML = 'Images: <span class="text-xs">0</span>';
    if (activeLabel) {
      activeLabel.textContent = `Active result: ${getResultSourceLabel(source)}`;
    }
    updateImagesBboxLabel(source);
    updateLayerSectionsForSource(source, false);
    if (typeof clearBboxLayerForSource === "function") {
      clearBboxLayerForSource(source);
    }
    return;
  }

  const renderedList = payload.kind === "files" ? renderFileList(items) : renderSceneList(items);
  container.innerHTML = renderedList;
  countLabel.innerHTML = `Images: <span class="text-xs">${items.length}</span>`;
  if (activeLabel) {
    activeLabel.textContent = `Active result: ${getResultSourceLabel(source)}`;
  }
  updateImagesBboxLabel(source);
  updateLayerSectionsForSource(source, true);
  if (payload.kind !== "files") {
    wireSceneResultInteractions(items, source);
  }
  if (typeof syncResultBboxLayers === "function") {
    syncResultBboxLayers(source, payload);
  }
}

function refreshActiveResult() {
  const source = activeResultSource || getResultSwitcher()?.value || "search";
  const payload = resultSourceState[source];
  renderResultPayload(source, payload);
}

function setActiveResultSource(source) {
  if (!Object.prototype.hasOwnProperty.call(resultSourceState, source)) {
    return;
  }
  activeResultSource = source;
  const switcher = getResultSwitcher();
  if (switcher && switcher.value !== source) {
    switcher.value = source;
  }
  refreshActiveResult();
}

function setResultSource(source, payload) {
  if (!Object.prototype.hasOwnProperty.call(resultSourceState, source)) {
    return;
  }
  resultSourceState[source] = payload;
  if (!activeResultSource) {
    activeResultSource = source;
  }
  if (activeResultSource === source) {
    const switcher = getResultSwitcher();
    if (switcher) {
      switcher.value = source;
    }
    renderResultPayload(source, payload);
  }
}

function clearActiveOutputLayer() {
  const source = activeResultSource || getResultSwitcher()?.value || "search";
  resultSourceState[source] = null;

  if (source === "search") {
    if (geojsonLayer && map && map.hasLayer(geojsonLayer)) {
      map.removeLayer(geojsonLayer);
    }
    if (liveLayer && map && map.hasLayer(liveLayer)) {
      map.removeLayer(liveLayer);
    }
    if (typeof showLoaderOnMap === 'function') showLoaderOnMap(null, false);
  }

  if (source === "analyze") {
    if (computeLayer && map && map.hasLayer(computeLayer)) {
      map.removeLayer(computeLayer);
    }
  }

  // Clear the bbox layer for this source
  if (typeof clearBboxLayerForSource === "function") {
    clearBboxLayerForSource(source);
  }
  // Uncheck the bbox checkbox for this source
  const bboxCheck = document.getElementById(source + "_bbox_layer");
  if (bboxCheck) bboxCheck.checked = false;

  // Also clear highlighted layer
  if (typeof highlightedLayer !== "undefined" && highlightedLayer) {
    highlightedLayer.clearLayers();
  }
  if (typeof map !== "undefined" && map) {
    map.closePopup();
  }

  renderResultPayload(source, null);
  closeClearConfirmModal();
  updateLayerCountSummary();
}

function clearResultSources() {
  resultSourceState.search = null;
  resultSourceState.analyze = null;
  resultSourceState.download = null;
  activeResultSource = null;
  const container = getResultContainer();
  const countLabel = getResultCountLabel();
  const activeLabel = getResultActiveLabel();
  const switcher = getResultSwitcher();
  if (container) {
    container.innerHTML = '<label class="block text-sm font-medium text-gray-400 pt-4">Apply the Filter First!!!</label>';
  }
  if (countLabel) {
    countLabel.innerHTML = 'Images: <span class="text-xs"></span>';
  }
  if (activeLabel) {
    activeLabel.textContent = 'Active result: None';
  }
  updateImagesBboxLabel(null);
  updateLayerSectionsForSource(null, false);
  if (switcher) {
    switcher.value = 'search';
  }
  // Uncheck all per-source bbox checkboxes
  ["search_bbox_layer", "analyze_bbox_layer", "download_bbox_layer"].forEach(function(id) {
    const el = document.getElementById(id);
    if (el) el.checked = false;
  });
  if (typeof clearResultBboxLayers === "function") {
    clearResultBboxLayers();
  }
  if (typeof clearImagesBboxLayer === "function") {
    clearImagesBboxLayer();
  }
  closeClearConfirmModal();
  updateLayerCountSummary();
}

function openClearConfirmModal() {
  const source = activeResultSource || getResultSwitcher()?.value || "search";
  const modal = getClearModal();
  const title = getClearModalTitleLabel();
  const message = getClearModalMessageLabel();
  if (title) {
    title.textContent = getClearModalTitle(source);
  }
  if (message) {
    message.textContent = getClearModalMessage(source);
  }
  if (modal) {
    modal.classList.remove("hidden");
  }
}

function closeClearConfirmModal() {
  const modal = getClearModal();
  if (modal) {
    modal.classList.add("hidden");
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const switcher = getResultSwitcher();
  if (switcher) {
    switcher.addEventListener('change', (event) => {
      setActiveResultSource(event.target.value);
    });
  }

  const clearCancel = document.getElementById("clear-confirm-cancel");
  const clearAccept = document.getElementById("clear-confirm-accept");
  if (clearCancel) {
    clearCancel.addEventListener("click", closeClearConfirmModal);
  }
  if (clearAccept) {
    clearAccept.addEventListener("click", clearActiveOutputLayer);
  }

  if (!activeResultSource) {
    const activeLabel = getResultActiveLabel();
    if (activeLabel) {
      activeLabel.textContent = 'Active result: None';
    }
  }
});

window.setResultSource = setResultSource;
window.setActiveResultSource = setActiveResultSource;
window.refreshActiveResult = refreshActiveResult;
window.clearResultSources = clearResultSources;
window.clearActiveOutputLayer = clearActiveOutputLayer;
window.openClearConfirmModal = openClearConfirmModal;
window.closeClearConfirmModal = closeClearConfirmModal;
window.updateLayerCountSummary = updateLayerCountSummary;

function buildSearchRequestUrl(params) {
  const bbox = encodeURIComponent(params.bbox || "");
  const startDate = encodeURIComponent(params.startDate || "");
  const endDate = encodeURIComponent(params.endDate || "");
  const cloudCover = encodeURIComponent(params.cloudCover ?? "30");
  const collection = encodeURIComponent(params.collection || "sentinel-2-l2a");
  const mode = params.mode ? `&mode=${encodeURIComponent(params.mode)}` : "";
  return `/search?bbox=${bbox}&start_date=${startDate}&end_date=${endDate}&cloud_cover=${cloudCover}&collection=${collection}${mode}`;
}

function fetchSearchResults(params) {
  const requestUrl = buildSearchRequestUrl(params);
  return fetch(requestUrl, { method: "GET" })
    .then((response) => response.json())
    .then((data) => (data && Array.isArray(data.features) ? data.features : []));
}

window.buildSearchRequestUrl = buildSearchRequestUrl;
window.fetchSearchResults = fetchSearchResults;
