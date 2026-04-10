# Relevant Code Reconnaissance

## Primary File: `frontend/utils.py`

This is the **only file that needs modification** to fix the light basemap tile layer issue. It contains both map rendering functions and all folium-related logic.

### 1. `render_aoi_map()` (lines 70-157)

This function renders the AOI-only map. It creates a folium map with `tiles="OpenStreetMap"` and does NOT add any LayerControl or alternative basemaps.

**Key code (line 105):**
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

**Layer order in this function:**
1. Base tiles (OpenStreetMap) - via `folium.Map()`
2. AOI GeoJson overlay (lines 108-119)
3. Subregion GeoJson overlays (lines 122-145)

**No LayerControl is added** to this map instance, so no basemap switching is available here.

### 2. `render_dataset_map()` (lines 160-265)

This is the function with the reported bug. It creates a map, adds a dataset tile layer, optionally adds an AOI overlay, and adds a `LayerControl`.

**Key code (lines 194-206):**
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
)

# Add dataset tile layer
dataset_name = dataset_data.get("data_layer", "Dataset Layer")
folium.raster_layers.TileLayer(
    tiles=tile_url,
    attr="Dataset Tiles",
    name=dataset_name,
    overlay=True,
    control=True,
).add_to(m2)
```

**AOI overlay (lines 209-223):**
```python
if aoi_data and isinstance(aoi_data, dict) and "geometry" in aoi_data:
    folium.GeoJson(
        geojson_data,
        style_function=lambda feature: {
            "fillColor": "blue",
            "color": "blue",
            "weight": 2,
            "fillOpacity": 0.1,
        },
        ...
    ).add_to(m2)
```

**LayerControl (line 227):**
```python
folium.LayerControl().add_to(m2)
```

### Root Cause Analysis

The issue description says "Light tile layer fails to render" and users must switch to Satellite as a workaround. However, looking at the code:

1. **`tiles="OpenStreetMap"` is the default basemap** passed to `folium.Map()`. In recent versions of folium (the project uses `streamlit_folium==0.23.0` and `folium-vectorgrid==0.1.3` but does NOT pin folium itself), the `"OpenStreetMap"` built-in tile option may have changed or become unreliable.

2. **There is NO explicit Light/Dark/Satellite tile layer setup** in the current code. The issue description mentions "a LayerControl with Light/Satellite options visible to the user" but the code only has a bare `folium.LayerControl()` which would show the default OpenStreetMap base layer and the dataset overlay. There are no additional `TileLayer` objects for Light, Dark, or Satellite basemaps.

3. **The `folium.Map(tiles="OpenStreetMap")` call** may be failing silently if the OpenStreetMap tile server URL has changed or if folium's built-in tile provider mapping is outdated.

**The fix needs to:**
- Replace `tiles="OpenStreetMap"` with a reliable free tile URL (e.g., CartoDB Positron for "Light")
- Add explicit `TileLayer` objects for Light/Dark/Satellite basemap options
- Ensure the dataset tile layer has `overlay=True` (already done) so it renders on top of basemaps
- Ensure AOI GeoJson is added after dataset tiles so it renders on top
- Add `LayerControl` after all layers are added (already done)

## Secondary File: `frontend/requirements.txt`

```
streamlit==1.40.1
streamlit_folium==0.23.0
pandas==2.2.3
python-dotenv==1.0.1
geopandas==1.0.1
folium-vectorgrid==0.1.3
```

**Note:** `folium` itself is NOT pinned in requirements.txt. It is an implicit dependency of `streamlit_folium==0.23.0`. This means the folium version may vary between installations, which could affect tile provider behavior. The fix should use explicit tile URLs rather than relying on folium's built-in tile name shortcuts.

## Data Flow: How Dataset Maps Get Rendered

### Backend: `src/agent/tools/pick_dataset.py`

The `pick_dataset` tool (line 235) returns a `Command` with `update={"dataset": selection_result.model_dump(), ...}`. The `DatasetSelectionResult` model (line 114) includes:

```python
class DatasetSelectionResult(DatasetOption):
    tile_url: str = Field(...)
    dataset_name: str = Field(...)
    # ... other fields
```

The tile URL is constructed from `analytics_datasets.yml` and modified based on dataset type (lines 286-312).

### Frontend rendering chain:

1. `render_stream()` in `frontend/utils.py` (line 648) processes streamed updates
2. If `"dataset"` key is in the update (line 696), it calls `render_dataset_map(dataset_data, aoi_data)`
3. If `"aoi"` key is in the update (line 686), it calls `render_aoi_map(aoi_data, subregion_data)`

Both pages (`frontend/pages/1_..._Uni_Guana.py` and `frontend/pages/2_..._Threads.py`) use `render_stream()` to display results.

## Folium Tile Provider Reference

For the fix, these are reliable free tile URLs:

- **CartoDB Positron (Light):** `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png`
- **CartoDB Dark Matter (Dark):** `https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png`
- **ESRI World Imagery (Satellite):** `https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}`

These can be added as `folium.TileLayer(tiles=url, attr="...", name="Light", ...)` objects.

## Files That Will Need Modification

| File | What to change |
|------|---------------|
| `frontend/utils.py` | Both `render_aoi_map()` and `render_dataset_map()` functions: replace `tiles="OpenStreetMap"` with explicit tile layer setup using reliable free providers. Add Light/Dark/Satellite `TileLayer` objects. Ensure correct z-ordering. |

No backend changes are needed. The tile_url construction in `pick_dataset.py` is for dataset data layers, not basemaps.
