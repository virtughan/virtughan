from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = (PROJECT_ROOT / "templates" / "index.html").read_text()
MAIN_JS = (PROJECT_ROOT / "static" / "js" / "main.js").read_text()
MAP_JS = (PROJECT_ROOT / "static" / "js" / "map.js").read_text()
EXPORT_JS = (PROJECT_ROOT / "static" / "js" / "export_download.js").read_text()
RESULT_SOURCES_JS = (PROJECT_ROOT / "static" / "js" / "result_sources.js").read_text()


def test_satellite_source_dropdowns_have_expected_order():
    expected_options = (
        '<option value="sentinel-2-l2a">Sentinel-2</option>',
        '<option value="landsat-c2-l2">Landsat</option>',
        '<option value="sentinel-1-rtc">Sentinel-1</option>',
    )

    for scope in ("search", "export"):
        select_start = INDEX_HTML.index(f'id="satellite-collection-{scope}"')
        select_end = INDEX_HTML.index("</select>", select_start)
        select_html = INDEX_HTML[select_start:select_end]
        positions = [select_html.index(option) for option in expected_options]
        assert positions == sorted(positions)

    assert 'name="select_satellite_search"' not in INDEX_HTML
    assert 'name="select_satellite_export"' not in INDEX_HTML


def test_sentinel1_controls_and_presets_are_available():
    assert 'id="sentinel1-mode-search"' in INDEX_HTML
    assert 'id="sentinel1-mode-export"' in INDEX_HTML
    assert INDEX_HTML.count('<option value="IW">') == 2
    assert INDEX_HTML.count('value="S1_VV_DB"') == 2
    assert INDEX_HTML.count('value="S1_VV_VH_DB"') == 2
    assert '"sentinel-1-rtc": ["vv", "vh", "hh", "hv"]' in MAIN_JS


def test_sentinel1_mode_is_sent_to_every_data_request():
    assert "encodedUrl_tiles += `&mode=" in MAP_JS
    assert "url_compute += `&mode=" in EXPORT_JS
    assert "download_url += `&mode=" in EXPORT_JS
    assert "const mode = params.mode ? `&mode=" in RESULT_SOURCES_JS


def test_cloud_cover_and_optical_presets_are_collection_aware():
    assert 'id="cloud-cover-container-search"' in INDEX_HTML
    assert 'id="cloud-cover-container-export"' in INDEX_HTML
    assert "classList.toggle('hidden', isSentinel1)" in MAIN_JS
    assert "isRadarTemplate || isUnsupportedVisual" in MAIN_JS


def test_changing_collection_clears_an_incompatible_filter_selection():
    assert "function resetCollectionFilterSelection(scope)" in MAIN_JS
    assert "selectedLabel.textContent = 'Select Option'" in MAIN_JS
    assert "resetCollectionFilterSelection(scope)" in MAIN_JS


def test_sentinel1_only_offers_mean_and_median_reducers():
    assert INDEX_HTML.count('class="text-gray-600 optical-operation"') == 12
    assert "option.hidden = isSentinel1" in MAIN_JS
    assert "option.disabled = isSentinel1" in MAIN_JS
    assert "!['median', 'mean'].includes(operationSelect?.value)" in MAIN_JS
