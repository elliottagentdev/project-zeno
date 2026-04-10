# Draft Plan 1: Minimal Surgery Fix for Light Basemap Tile Layer

## Lens: Smallest Possible Change Set

This plan modifies **one file** (`frontend/utils.py`) to fix the broken Light basemap and add reliable basemap switching. No new files, no new abstractions, no backend changes.

## Root Cause

The `folium.Map(tiles="OpenStreetMap")` built-in tile provider is failing to render. Folium's built-in `"OpenStreetMap"` string relies on an internal URL mapping that may be outdated or unreliable in the transitive folium version pulled by `streamlit_folium==0.25.0`. The map renders with a blank white background because the tile server request silently fails.

## Architecture

No architectural changes. The fix stays entirely within the existing Folium map rendering pipeline in `frontend/utils.py`. Both `render_aoi_map()` and `render_dataset_map()` are modified to use explicit tile URLs instead of Folium's built-in provider strings.

## Specific File Changes

### File: `frontend/utils.py`

#### Change 1: Add basemap tile URL constants (after imports, before first function)

Add three constants near the top of the file (after the existing `API_BASE_URL` constant) defining reliable free tile provider URLs and their attributions:

```python
# Basemap tile providers (free, no API key required)
CARTO_LIGHT_TILES = (
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
)
CARTO_LIGHT_ATTR = (
    '&copy; <a href="https://www.openstreetmap.org/copyright">'
    "OpenStreetMap</a> contributors &copy; "
    '<a href="https://carto.com/attributions">CARTO</a>'
)
CARTO_DARK_TILES = (
    "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
)
CARTO_DARK_ATTR = CARTO_LIGHT_ATTR
ESRI_SATELLITE_TILES = (
    "https://server.arcgisonline.com/ArcGIS/rest/services/"
    "World_Imagery/MapServer/tile/{z}/{y}/{x}"
)
ESRI_SATELLITE_ATTR = (
    "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, "
    "USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, "
    "UPR-EGP, and the GIS User Community"
)
```

#### Change 2: Create a helper function to add basemap layers

Add a small helper function (right before `render_aoi_map`) that adds the three basemap tile layers to any folium map object. This avoids duplicating the same block in both `render_aoi_map` and `render_dataset_map`:

```python
def _add_basemap_layers(m):
    """Add Light, Dark, and Satellite basemap tile layers to a folium map."""
    folium.TileLayer(
        tiles=CARTO_LIGHT_TILES,
        attr=CARTO_LIGHT_ATTR,
        name="Light",
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles=CARTO_DARK_TILES,
        attr=CARTO_DARK_ATTR,
        name="Dark",
        control=True,
    ).add_to(m)
    folium.TileLayer(
        tiles=ESRI_SATELLITE_TILES,
        attr=ESRI_SATELLITE_ATTR,
        name="Satellite",
        control=True,
    ).add_to(m)
```

This is a private helper (underscore prefix per project conventions), not a new abstraction. It simply deduplicates 15 lines.

#### Change 3: Modify `render_aoi_map()` (line 105)

**Before:**
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

**After:**
```python
m = folium.Map(location=center, zoom_start=5, tiles=None)
_add_basemap_layers(m)
```

The key change: `tiles=None` tells folium to create a map with NO default basemap. Then `_add_basemap_layers(m)` adds all three basemap options. The first one added (Light/CartoDB Positron) becomes the default visible layer.

Additionally, add `folium.LayerControl().add_to(m)` just before the `folium_static()` call (line ~151) so users can switch basemaps on AOI maps too. Currently only `render_dataset_map` has LayerControl.

**Insert after the subregion rendering block (before `st.subheader`):**
```python
folium.LayerControl().add_to(m)
```

#### Change 4: Modify `render_dataset_map()` (lines 194-195)

**Before:**
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
)
```

**After:**
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles=None
)
_add_basemap_layers(m2)
```

The rest of `render_dataset_map` remains unchanged. The dataset tile layer is still added with `overlay=True` (line 200-206), so it renders on top of whichever basemap is selected. The AOI GeoJson overlay is added after that. The existing `folium.LayerControl().add_to(m2)` at line 227 stays as-is.

## Layer Rendering Order (Preserved)

### `render_aoi_map`:
1. Basemap tile layers (Light default, Dark, Satellite) -- added first via `_add_basemap_layers(m)`
2. AOI GeoJson overlay (gray fill) -- added second
3. Subregion GeoJson overlays (red fill) -- added third
4. LayerControl -- added last (NEW)

### `render_dataset_map`:
1. Basemap tile layers (Light default, Dark, Satellite) -- added first via `_add_basemap_layers(m2)`
2. Dataset tile layer (`overlay=True`) -- added second (unchanged)
3. AOI GeoJson overlay (blue fill) -- added third (unchanged)
4. LayerControl -- added last (unchanged)

This matches the required order: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top).

## Data Models

No changes. The basemap is purely a frontend rendering concern. The `dataset_data` dict structure, `aoi_data` dict structure, and agent state (`src/agent/state.py`) are untouched.

## API Design

No changes. No backend endpoints are affected.

## Error Handling

No changes to error handling patterns. The existing `try/except` blocks in both functions already handle rendering failures gracefully by showing `st.error()` with raw data fallback. If a tile provider URL fails, the map will show a blank background (same failure mode as today) but the user can switch to an alternative basemap via LayerControl.

## Migration Plan

No database migrations. No configuration changes. This is a pure frontend rendering fix.

**Deployment:** The change takes effect immediately on next deploy or frontend restart. No cache invalidation or state migration needed.

**Rollback:** Revert the single file change to restore `tiles="OpenStreetMap"` behavior.

## Testing Strategy

### Manual Testing (Primary)

Since there are no existing frontend tests in the project, and adding a test framework for Streamlit/Folium rendering would be disproportionate to this fix:

1. **Default basemap renders:** Run the Streamlit app, execute any query that triggers a map render. Verify the Light (CartoDB Positron) basemap shows country borders, terrain labels, and geographic context.

2. **LayerControl switching:** On both AOI maps and dataset maps, use the LayerControl to switch between Light, Dark, and Satellite. Verify all three render correctly.

3. **Dataset tile overlay:** Execute a query that returns a dataset with tiles (e.g., tree cover loss). Verify the dataset tile layer renders on top of the basemap and can be toggled via LayerControl.

4. **AOI overlay on top:** Verify the AOI boundary polygon renders on top of both the basemap and the dataset tile layer.

5. **No API key required:** Verify all three tile providers load without any environment variables or API keys configured.

### Automated Smoke Test (Optional)

If desired, a minimal unit test could verify the helper function produces valid folium objects:

```python
def test_add_basemap_layers():
    import folium
    m = folium.Map(tiles=None)
    _add_basemap_layers(m)
    html = m._repr_html_()
    assert "basemaps.cartocdn.com/light_all" in html
    assert "basemaps.cartocdn.com/dark_all" in html
    assert "arcgisonline.com" in html
```

This is optional and not required for the fix to ship.

## Summary of Changes

| File | Lines Changed | What |
|------|--------------|------|
| `frontend/utils.py` | ~25 lines added, 2 lines modified | Add tile URL constants, `_add_basemap_layers()` helper, replace `tiles="OpenStreetMap"` with `tiles=None` + helper call in both map functions, add LayerControl to `render_aoi_map` |

**Total: 1 file modified. Zero new files. Zero backend changes.**
