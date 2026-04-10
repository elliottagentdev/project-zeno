# Relevant Code Reconnaissance: Fix Basemap Selector Layer Ordering

## Important Clarification: Codebase Is Python/Streamlit/Folium (NOT React/MapLibre GL)

The PROMPT.md references `app/components/map/BasemapSelector.tsx`, `MapLibre GL`, `HighlightedFeaturesLayer`, and `DynamicTileLayers` — **none of these exist in the actual codebase**. The project uses a Python/Streamlit/Folium stack, not React. All map rendering is done via the `folium` Python library rendered through `streamlit_folium`.

---

## Primary File: `frontend/utils.py`

This is the **only file that needs modification** to fix the layer ordering issue.

### 1. `BASEMAP_CONFIGS` (lines 21–61)

Module-level list defining the three basemap providers. Added in commit `7e83efb`:

```python
BASEMAP_CONFIGS = [
    {
        "tiles": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attr": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        "name": "Light",
    },
    {
        "tiles": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attr": '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        "name": "Dark",
    },
    {
        # ESRI uses {z}/{y}/{x} order (not {z}/{x}/{y})
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Tiles &copy; Esri ...",
        "name": "Satellite",
    },
]
```

The first entry (Light) is shown by default (`show=(i == 0)`).

### 2. `_create_base_map()` (lines 64–80)

Factory function that creates a `folium.Map` with all basemaps as base layers:

```python
def _create_base_map(center, zoom_start):
    """Create a folium Map with Light, Dark, and Satellite basemaps."""
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,  # Suppress default OSM layer
    )
    for i, config in enumerate(BASEMAP_CONFIGS):
        folium.raster_layers.TileLayer(
            tiles=config["tiles"],
            attr=config["attr"],
            name=config["name"],
            overlay=False,   # <-- base layer, not overlay
            control=True,
            show=(i == 0),   # Only Light shown by default
        ).add_to(m)
    return m
```

### 3. `render_aoi_map()` (lines 134–224)

Renders AOI boundaries using folium. Layer construction order:

1. `_create_base_map()` → adds Light, Dark, Satellite TileLayers (base layers, `overlay=False`)
2. `folium.GeoJson(geojson_data, ...)` → AOI polygon (line 173)
3. `folium.GeoJson(subregion_geojson, ...)` → subregion polygons (line 197)
4. `folium.LayerControl().add_to(m)` (line 214)

Key call at line 169:
```python
m = _create_base_map(center=center, zoom_start=5)
```

### 4. `render_dataset_map()` (lines 227–396)

Renders dataset tile layers (TCL, DIST-ALERT, etc.) with optional AOI overlay. Layer construction order:

1. `_create_base_map()` → adds Light, Dark, Satellite TileLayers (base layers, `overlay=False`)
2. `folium.raster_layers.TileLayer(tiles=tile_url, overlay=True, ...)` → dataset tiles (line 328)
3. `folium.GeoJson(geometry, ...)` → AOI overlay (line 339), if geometry is available
4. `folium.LayerControl().add_to(m2)` (line 358)

Key call at line 304:
```python
m2 = _create_base_map(center=center, zoom_start=zoom_start)
```

Dataset tile layer construction at lines 328–334:
```python
folium.raster_layers.TileLayer(
    tiles=tile_url,
    attr="Dataset Tiles",
    name=dataset_name,
    overlay=True,   # <-- overlay layer, NOT a base layer
    control=True,
).add_to(m2)
```

AOI overlay at lines 339–354:
```python
if geometry and isinstance(geometry, dict):
    try:
        folium.GeoJson(
            geometry,
            style_function=lambda feature: {
                "fillColor": "blue",
                "color": "blue",
                "weight": 2,
                "fillOpacity": 0.1,
            },
            popup=folium.Popup("Area of Interest", parse_html=True),
            tooltip="AOI",
        ).add_to(m2)
    except Exception as e:
        st.warning(f"Could not render AOI overlay: {str(e)}")
```

### 5. `render_stream()` (lines 779–870)

The main event loop called from both Streamlit pages. Renders maps based on state updates:

```python
def render_stream(stream):
    update = json.loads(stream["update"])
    # ...
    aoi_data = None
    if "aoi" in update:
        aoi_data = update["aoi"]
        st.session_state["last_aoi_data"] = aoi_data
        subregion_data = (
            update.get("subregion_aois")
            if update.get("subregion") is not None
            else None
        )
        render_aoi_map(aoi_data, subregion_data)

    if "dataset" in update:
        dataset_data = update["dataset"]
        aoi_data = (
            update.get("aoi")
            or st.session_state.get("last_aoi_data")
        )
        render_dataset_map(dataset_data, aoi_data)
```

---

## Root Cause Analysis (Actual Codebase)

The PROMPT.md describes the issue as a **layer ordering problem** when switching basemaps. In the Folium/Leaflet context, the relevant behavior is:

**When the user switches basemaps in the `LayerControl`**, Leaflet/Folium handles base layers as radio buttons. The base layers (Light/Dark/Satellite) each have `overlay=False`. When the user switches from Light to Satellite, Leaflet removes the Light TileLayer and adds the Satellite TileLayer.

**The actual problem**: In Folium, layers are added to the Leaflet map **in the order they are appended** to the `folium.Map` object. The current implementation adds basemaps FIRST (inside `_create_base_map()`), then dataset TileLayers, then GeoJson overlays. This means the intended z-order from bottom to top is:

1. Basemap (Light/Dark/Satellite) — bottom
2. Dataset TileLayer (TCL, etc.) — middle  
3. AOI GeoJson polygon — top

However, **when the user switches basemaps via the `LayerControl`**, Leaflet swaps base layers. The newly activated base layer (e.g. Satellite) gets added to the Leaflet layer stack at the moment of the switch. Depending on Leaflet's internal behavior for `setZIndex` on TileLayers, the newly activated base layer may render on top of the overlay TileLayers (dataset tiles) and GeoJson layers.

**Key code section for the fix** — `_create_base_map()` at lines 64–80:

The fix should ensure basemap `TileLayer` objects are explicitly assigned a lower `zIndex` so that when a new basemap is activated, it renders below overlay layers. Options:
- Pass `zIndex=100` (or similar low value) to basemap `TileLayer` objects in `BASEMAP_CONFIGS` / `_create_base_map()`
- Pass higher `zIndex` to dataset `TileLayer` in `render_dataset_map()`

Folium's `TileLayer` accepts a `z_index` parameter (or maps the `**kwargs` to Leaflet's `options.zIndex`).

---

## Data Flow: How Maps Are Rendered

```
render_stream(stream)
  └── if "aoi" in update:
        └── render_aoi_map(aoi_data, subregion_data)
              └── _create_base_map()  [adds Light/Dark/Satellite]
              └── folium.GeoJson(aoi)
              └── folium.GeoJson(subregion) (if present)
              └── folium.LayerControl()
              └── folium_static(m)

  └── if "dataset" in update:
        └── render_dataset_map(dataset_data, aoi_data)
              └── _create_base_map()  [adds Light/Dark/Satellite]
              └── folium.raster_layers.TileLayer(tile_url, overlay=True)
              └── folium.GeoJson(geometry) (if present)
              └── folium.LayerControl()
              └── folium_static(m2)
```

---

## Existing Tests: `tests_frontend/`

### `tests_frontend/test_basemap.py`

Tests covering `BASEMAP_CONFIGS` and `_create_base_map()`:

```python
def test_basemap_layers_are_base_not_overlay():
    """All basemaps must be base layers (overlay=False)."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.raster_layers.TileLayer)
    ]
    for tl in tile_layers:
        assert tl.overlay is False, f"{tl.tile_name} should be a base layer"
```

A test for `zIndex` enforcement would need to check that basemap TileLayers have lower zIndex than overlay TileLayers.

### `tests_frontend/conftest.py`

- Mocks `streamlit.session_state` as a dict-like `_SessionState` for all tests
- Provides `mock_folium_static` fixture that patches `utils.folium_static`
- Adds `frontend/` to `sys.path`

### `tests_frontend/test_render_dataset_map.py`

Tests for geometry resolution, session state caching, and fallback behavior.

---

## Files That May Need Modification

| File | What to change |
|------|---------------|
| `frontend/utils.py` | In `_create_base_map()`: add explicit `z_index` (or `zIndex` kwargs) to basemap `TileLayer` objects to ensure they render below overlay layers after a basemap switch. Possibly also set higher `z_index` on dataset `TileLayer` in `render_dataset_map()`. |
| `tests_frontend/test_basemap.py` | Add test(s) verifying basemap layers have lower zIndex than overlay layers. |

---

## Folium TileLayer zIndex API

Folium's `TileLayer` passes extra keyword arguments to the underlying Leaflet `L.tileLayer()`. The relevant Leaflet option is `zIndex` (camelCase). In Folium, you can pass it as:

```python
folium.raster_layers.TileLayer(
    tiles=config["tiles"],
    attr=config["attr"],
    name=config["name"],
    overlay=False,
    control=True,
    show=(i == 0),
    # Leaflet zIndex for layer ordering
    zIndex=100,  # or via extra_options param depending on folium version
).add_to(m)
```

Alternatively, Folium ≥0.14 accepts `**kwargs` forwarded to Leaflet. The exact parameter name to use should be verified against the installed folium version (implicit dependency of `streamlit_folium==0.23.0`).

---

## Related Spec Context: Previous Fixes

The commit `7e83efb` ("fix: replace broken OpenStreetMap basemap with reliable tile providers") introduced `BASEMAP_CONFIGS` and `_create_base_map()`. The layer ordering issue for the basemap selector was NOT addressed in that fix — only the tile provider reliability issue was fixed.

The previous spec `1-fix-light-basemap-tile-layer-failing-to-render-on/recon/relevant_code.md` describes the state before `7e83efb`, where `tiles="OpenStreetMap"` was used directly. That has already been resolved.

This spec addresses the remaining issue: **z-ordering / layer stacking when switching between the Light/Dark/Satellite base layers**.
