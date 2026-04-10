# Draft Plan 2: Clean Architecture Approach

## Architectural Lens

This plan prioritizes **proper separation of concerns** and **extensibility**. Rather than patching tile URLs inline, we extract basemap configuration into a dedicated abstraction, making it trivial to add/remove/modify basemap options without touching rendering logic. We accept a slightly larger changeset in exchange for a design that scales cleanly.

---

## 1. Architecture Overview

### Current State (Problem)

Both `render_aoi_map()` and `render_dataset_map()` in `frontend/utils.py` hardcode `tiles="OpenStreetMap"` in `folium.Map()`. This has two issues:

1. **Reliability**: Folium's built-in `"OpenStreetMap"` tile name relies on an internal URL mapping that may be outdated or unreliable, causing a blank basemap.
2. **No basemap switching in `render_aoi_map`**: Only `render_dataset_map` has a `LayerControl`, but even there, there are no explicit Light/Dark/Satellite `TileLayer` objects -- only the default OSM base and the dataset overlay.
3. **No single source of truth**: Basemap configuration is scattered (implicit in `folium.Map()` constructor).

### Proposed Architecture

Introduce a **basemap configuration module** and a **shared map factory function** that both rendering functions use. This gives us:

- A single place to define all basemap tile providers (URLs, attributions, names)
- A single function that creates a properly-layered `folium.Map` with basemap options
- Consistent behavior across `render_aoi_map` and `render_dataset_map`
- Easy extensibility: add a new basemap by adding one entry to a list

### Layer Ordering Contract

All maps will enforce this z-order:
1. **Basemap tiles** (bottom) -- Light is default, Dark and Satellite are alternatives
2. **Dataset tile layer(s)** (middle) -- added by `render_dataset_map` only, with `overlay=True`
3. **AOI/subregion GeoJson overlays** (top) -- added last
4. **LayerControl** (UI element) -- added after all layers

This order is guaranteed because layers are added to `folium.Map` in sequence, and Leaflet renders them in add-order within their type (base layers vs overlays).

---

## 2. Specific File Changes

### File: `frontend/utils.py` (Primary -- all changes here)

#### 2a. Add basemap constants (new code, top of file after imports)

Add a module-level constant defining the basemap tile providers. Place this after the existing imports and before any function definitions (around line 30, after the existing constants like `API_BASE_URL`).

```python
# Basemap tile layer configurations
# Each entry: (url, attribution, name, is_default)
BASEMAP_TILES = [
    {
        "url": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors &copy; "
            '<a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Light",
        "default": True,
    },
    {
        "url": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors &copy; "
            '<a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Dark",
        "default": False,
    },
    {
        "url": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": (
            "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, "
            "USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, "
            "UPR-EGP, and the GIS User Community"
        ),
        "name": "Satellite",
        "default": False,
    },
]
```

**Rationale**: A list-of-dicts is the simplest extensible structure. Adding a new basemap is a single dict append. The `default` flag controls which one is shown on init. No classes needed -- this is configuration data, not behavior.

#### 2b. Add `_create_base_map()` helper function (new function)

Add a private helper function that encapsulates basemap creation. Place it before `render_aoi_map()`.

```python
def _create_base_map(center, zoom_start):
    """Create a folium Map with multiple basemap tile layer options.

    Args:
        center: [lat, lng] for the map center.
        zoom_start: Initial zoom level.

    Returns:
        A folium.Map instance with Light, Dark, and Satellite
        basemap layers. Light is shown by default.
    """
    # Create map with no default tiles -- we add our own
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,
    )

    # Add each basemap as a base layer (overlay=False)
    for tile_config in BASEMAP_TILES:
        folium.raster_layers.TileLayer(
            tiles=tile_config["url"],
            attr=tile_config["attr"],
            name=tile_config["name"],
            overlay=False,
            control=True,
            show=tile_config["default"],
        ).add_to(m)

    return m
```

**Key design decisions**:
- `tiles=None` in `folium.Map()` -- suppresses the default tile layer entirely so we control all basemaps explicitly.
- `overlay=False` -- marks these as **base layers** (radio buttons in LayerControl, mutually exclusive). This is critical: dataset tiles use `overlay=True` (checkboxes), ensuring they render on top and can be toggled independently.
- `show=tile_config["default"]` -- only the Light basemap is visible on init. The others are available via LayerControl but not loaded until selected.

#### 2c. Modify `render_aoi_map()` (lines 70-157)

**Change 1**: Replace the `folium.Map()` constructor call (line 105):

```python
# BEFORE (line 105):
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")

# AFTER:
m = _create_base_map(center=center, zoom_start=5)
```

**Change 2**: Add `LayerControl` before the `folium_static()` call (insert before line 151):

```python
# Add layer control for basemap switching
folium.LayerControl().add_to(m)
```

This gives `render_aoi_map` the same basemap switching capability as `render_dataset_map`. Previously, AOI-only maps had no way to switch basemaps.

**No other changes** to `render_aoi_map`. The AOI GeoJson overlay and subregion overlays are added after the basemap layers (via `_create_base_map`), preserving the correct z-order: basemaps at bottom, AOI/subregions on top.

#### 2d. Modify `render_dataset_map()` (lines 160-265)

**Change 1**: Replace the `folium.Map()` constructor call (lines 194-196):

```python
# BEFORE (lines 194-196):
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
)

# AFTER:
m2 = _create_base_map(center=center, zoom_start=zoom_start)
```

**No other changes** to `render_dataset_map`. The existing code already:
- Adds dataset tile layer with `overlay=True` (line 200-206) -- renders above basemaps
- Adds AOI GeoJson after dataset tiles (line 209-222) -- renders on top of everything
- Adds `folium.LayerControl().add_to(m2)` last (line 227) -- captures all layers

The layer order remains correct:
1. Basemaps (Light/Dark/Satellite via `_create_base_map`, `overlay=False`)
2. Dataset tile layer (`overlay=True`, added after basemaps)
3. AOI GeoJson (added after dataset tiles)
4. LayerControl (added last)

---

## 3. Data Models

No data model changes required. The basemap configuration is a module-level constant (`BASEMAP_TILES`), not stored in a database or passed through the API. The agent state (`src/agent/state.py`) and API schemas (`src/api/schemas.py`) are unaffected.

---

## 4. API Design

No API changes required. The basemap selection is purely a frontend concern. The backend continues to provide `tile_url` for dataset layers; basemap tiles are loaded directly from public CDNs by the browser.

---

## 5. Error Handling

### Basemap Tile Loading Failures

The existing error handling in both `render_aoi_map` and `render_dataset_map` already wraps the entire rendering logic in `try/except Exception` blocks with `st.error()` fallback. However, basemap tile loading failures are **silent by design** in Leaflet/Folium -- a failed tile request simply shows a gray/blank tile, not a Python exception.

**Mitigation strategy (already built into the design)**:
- CartoDB Positron (Light) is used as the default because it is one of the most reliable free tile services, backed by CARTO's CDN infrastructure.
- Multiple basemap options (Light, Dark, Satellite from different providers) give users a fallback if any single provider is temporarily unavailable.
- The `show=True/False` pattern means only the default basemap tiles are loaded on init, reducing the chance of hitting rate limits.

**No additional error handling code is needed** beyond what already exists. The architectural decision to offer multiple basemap providers IS the error handling strategy -- it provides user-accessible fallbacks.

---

## 6. Testing Strategy

### Context: No Existing Frontend Tests

The project has no frontend tests (`tests/` covers only backend). Adding a full Folium rendering test suite is out of scope for this bug fix. However, we can add targeted unit tests for the new abstraction.

### Recommended Tests

**File: `tests/frontend/__init__.py`** (new, empty)
**File: `tests/frontend/test_basemap.py`** (new)

```python
"""Tests for basemap configuration and map factory."""
import folium

from frontend.utils import BASEMAP_TILES, _create_base_map


def test_basemap_tiles_has_default():
    """Exactly one basemap should be marked as default."""
    defaults = [t for t in BASEMAP_TILES if t["default"]]
    assert len(defaults) == 1
    assert defaults[0]["name"] == "Light"


def test_basemap_tiles_all_have_required_keys():
    """Each basemap config must have url, attr, name, default."""
    required_keys = {"url", "attr", "name", "default"}
    for tile in BASEMAP_TILES:
        assert required_keys.issubset(tile.keys()), (
            f"Missing keys in {tile.get('name', 'unknown')}"
        )


def test_create_base_map_returns_folium_map():
    """_create_base_map should return a folium.Map instance."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    assert isinstance(m, folium.Map)


def test_create_base_map_has_no_default_tiles():
    """Map should not have the default OpenStreetMap tiles."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    # Should NOT contain the default OpenStreetMap tile reference
    # that folium adds when tiles="OpenStreetMap"
    assert "tile.openstreetmap.org" not in html


def test_create_base_map_has_carto_tiles():
    """Map should contain CartoDB tile URLs."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "basemaps.cartocdn.com/light_all" in html
    assert "basemaps.cartocdn.com/dark_all" in html


def test_create_base_map_has_satellite_tiles():
    """Map should contain ESRI satellite tile URL."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "server.arcgisonline.com" in html
```

### Why These Tests Are Sufficient

- **`BASEMAP_TILES` structure tests** catch configuration errors (missing keys, no default, multiple defaults).
- **`_create_base_map` output tests** verify the factory produces a map with the correct tile providers and without the broken default.
- **HTML assertion tests** verify tiles actually end up in the rendered Leaflet HTML, catching regressions where tiles might be silently dropped.
- These tests require only `folium` (already a transitive dep) and no network access, Streamlit, or browser.

### Manual Verification Checklist

Since Folium rendering is visual, automated tests supplement but do not replace manual verification:

1. Run `make frontend` and trigger an AOI query -- verify Light basemap renders with country borders/labels
2. Use LayerControl to switch to Dark -- verify it renders
3. Use LayerControl to switch to Satellite -- verify it renders
4. Trigger a dataset query -- verify dataset tiles render on top of Light basemap
5. Verify AOI boundary renders on top of dataset tiles
6. Switch basemap while dataset is visible -- verify dataset tiles stay visible
7. Check browser console (F12) for tile loading errors

---

## 7. Migration Plan

### Rollout

This is a **frontend-only, zero-migration change**. No database changes, no API changes, no configuration file changes.

**Deployment steps**:
1. Merge the PR
2. Rebuild the frontend Docker image (or hot-reload if using dev mode)
3. Verify via manual checklist above

### Rollback

If the CartoDB Positron tiles are unreliable in production:
- Revert the PR (single file change to `frontend/utils.py`)
- Or: update `BASEMAP_TILES[0]["url"]` to an alternative provider (e.g., Stadia Maps, Thunderforest) -- this is a one-line change thanks to the configuration abstraction

### Dependency Notes

- No new Python dependencies are added. `folium` is already a transitive dependency.
- CartoDB Positron, CartoDB Dark Matter, and ESRI World Imagery are all free-tier tile services that do not require API keys.
- CartoDB tiles use OpenStreetMap data (attributed in the `attr` field), which is standard practice.

---

## 8. Summary of Changes

| File | Change Type | Description |
|------|-------------|-------------|
| `frontend/utils.py` | Add constant | `BASEMAP_TILES` -- list of basemap tile provider configs |
| `frontend/utils.py` | Add function | `_create_base_map(center, zoom_start)` -- map factory with basemap layers |
| `frontend/utils.py` | Modify function | `render_aoi_map()` -- use `_create_base_map()`, add `LayerControl` |
| `frontend/utils.py` | Modify function | `render_dataset_map()` -- use `_create_base_map()` |
| `tests/frontend/__init__.py` | New file | Empty `__init__.py` for test package |
| `tests/frontend/test_basemap.py` | New file | Unit tests for `BASEMAP_TILES` and `_create_base_map()` |

**Total files changed**: 1 modified, 2 new (tests)
**Lines added**: ~80 (constants + helper + tests)
**Lines removed**: ~4 (two `folium.Map()` calls replaced)
**Risk**: Low -- all changes are frontend-only, no backend/API/DB impact

---

## 9. Why This Design Over Inline Fixes

An inline fix would simply replace `tiles="OpenStreetMap"` with a CartoDB URL string in both functions. That works but:

1. **Duplicates the URL** in two places (DRY violation)
2. **Hardcodes a single provider** -- if CartoDB goes down, you edit two functions
3. **Mixes configuration with rendering logic** -- the tile URL is data, not behavior
4. **Makes adding basemaps harder** -- you need to understand the Folium `TileLayer` API and edit rendering functions

The proposed design:
- **Single source of truth** for basemap providers (`BASEMAP_TILES`)
- **Single factory function** for map creation (`_create_base_map`)
- **Adding a basemap** = appending a dict to a list (no Folium knowledge needed)
- **Removing a basemap** = deleting a dict from a list
- **Changing the default** = flipping a boolean
- **Total overhead**: ~40 lines of well-documented code
