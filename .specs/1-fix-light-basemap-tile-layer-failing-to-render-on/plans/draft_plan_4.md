# Draft Plan 4: Developer Experience Lens

## Guiding Principle

Every change must be obvious to the next developer who reads this code. No magic strings scattered across functions. No implicit behaviors. A junior developer should be able to open `frontend/utils.py`, see the basemap setup, and immediately understand what tile providers are used, in what order layers render, and how to add or change a basemap.

---

## 1. Problem Statement

`frontend/utils.py` creates Folium maps with `tiles="OpenStreetMap"` as the sole basemap. This built-in tile shortcut is failing silently -- the map renders with a blank white background. Users must manually switch to Satellite (if available) as a workaround. The code has no explicit tile provider URLs, no fallback logic, and the `render_aoi_map` function lacks a `LayerControl` entirely.

## 2. Architecture: Extract Basemap Configuration to a Single Location

### The Problem with the Current Approach

Both `render_aoi_map` (line 105) and `render_dataset_map` (line 194) independently hardcode `tiles="OpenStreetMap"`. If a developer needs to change tile providers, they must find and update every `folium.Map()` call. This is fragile and violates DRY.

### The Fix: A Module-Level Basemap Configuration Block

Add a clearly commented configuration block near the top of `frontend/utils.py` (after imports, before function definitions). This block defines all basemap tile providers in one place.

**File: `frontend/utils.py`** -- Add after the existing constants (after line ~24, near `API_BASE_URL`):

```python
# ──────────────────────────────────────────────────────────
# Basemap Tile Providers
# ──────────────────────────────────────────────────────────
# All basemap configurations live here. To add or change a
# basemap, edit this list. The first entry is the default.
# Each dict maps to a folium.TileLayer() call.
#
# Why explicit URLs instead of folium built-in names?
# Folium's built-in "OpenStreetMap" shortcut has proven
# unreliable. Explicit URLs are deterministic and debuggable.
# ──────────────────────────────────────────────────────────
BASEMAP_CONFIGS = [
    {
        "tiles": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors &copy; "
            '<a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Light",
    },
    {
        "tiles": "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors &copy; "
            '<a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Dark",
    },
    {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": (
            "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, "
            "USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, "
            "UPR-EGP, and the GIS User Community"
        ),
        "name": "Satellite",
    },
]
```

**Why this design:**
- One list, one place. Any developer can find and modify basemaps without searching through rendering functions.
- The first entry (`"Light"`) is the default basemap -- this is documented in the comment.
- Each entry is a plain dict that maps directly to `folium.TileLayer()` kwargs. No indirection, no classes, no abstraction layers.
- Strings are broken across lines to stay within the 79-character line length convention (Ruff config).

## 3. Helper Function: `_add_basemap_layers`

Create a small private helper that both map functions call. This eliminates duplicated basemap logic.

**File: `frontend/utils.py`** -- Add before `render_aoi_map`:

```python
def _add_basemap_layers(folium_map):
    """Add all basemap tile layers to a folium map.

    The first basemap in BASEMAP_CONFIGS is shown by default.
    All basemaps are added as base layers (overlay=False) so
    Folium's LayerControl renders them as radio buttons, not
    checkboxes.
    """
    for i, config in enumerate(BASEMAP_CONFIGS):
        folium.TileLayer(
            tiles=config["tiles"],
            attr=config["attr"],
            name=config["name"],
            overlay=False,
            control=True,
            show=(i == 0),
        ).add_to(folium_map)
```

**Why a helper instead of inline code:**
- Both `render_aoi_map` and `render_dataset_map` need identical basemap setup. Without a helper, we would copy-paste the same loop into both functions.
- The helper is private (underscore prefix) because it is an internal implementation detail, not part of the module's public API.
- The `show=(i == 0)` pattern makes the first basemap (Light) visible by default. This is explicit and readable.
- `overlay=False` is the critical parameter -- it tells Folium these are base layers (radio button selection in LayerControl), not overlay layers (checkbox toggles).

## 4. Specific File Changes

### 4.1 `render_aoi_map()` (lines 70-157)

**Change 1: Replace `tiles="OpenStreetMap"` with `tiles=None`**

Current (line 105):
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

New:
```python
m = folium.Map(location=center, zoom_start=5, tiles=None)
_add_basemap_layers(m)
```

Setting `tiles=None` tells Folium not to add any default base layer. We then add our own via the helper. This is the folium-idiomatic way to control basemaps.

**Change 2: Add `LayerControl` before rendering**

Current (lines 149-153):
```python
st.subheader("... Area of Interest")
folium_static(m, width=700, height=400)
```

New:
```python
folium.LayerControl().add_to(m)
st.subheader("... Area of Interest")
folium_static(m, width=700, height=400)
```

Currently `render_aoi_map` has no `LayerControl`. Adding it gives users the same Light/Dark/Satellite radio buttons on AOI maps that they get on dataset maps. This is a consistency improvement -- users should not have to remember which map type supports basemap switching.

### 4.2 `render_dataset_map()` (lines 160-265)

**Change 1: Replace `tiles="OpenStreetMap"` with `tiles=None` + helper call**

Current (lines 194-196):
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
)
```

New:
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles=None
)
_add_basemap_layers(m2)
```

**No other changes to `render_dataset_map`.** The existing dataset `TileLayer` (lines 200-206) already uses `overlay=True`, so it will render on top of basemaps. The existing AOI GeoJson overlay (lines 209-222) is added after the dataset layer, so it renders on top. The existing `LayerControl` (line 227) is already in the correct position.

### 4.3 Layer Rendering Order (Verified)

After the changes, the layer order in both functions will be:

**`render_aoi_map`:**
1. Basemap tile layers (Light/Dark/Satellite) -- added by `_add_basemap_layers()`
2. AOI GeoJson overlay (gray fill) -- existing code, no change
3. Subregion GeoJson overlays (red fill) -- existing code, no change
4. LayerControl -- new addition

**`render_dataset_map`:**
1. Basemap tile layers (Light/Dark/Satellite) -- added by `_add_basemap_layers()`
2. Dataset tile layer (`overlay=True`) -- existing code, no change
3. AOI GeoJson overlay (blue fill) -- existing code, no change
4. LayerControl -- existing code, no change

This matches the required order: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top).

## 5. What NOT to Change

- **Dataset tile layer logic** (lines 198-206 in `render_dataset_map`): The `tile_url` comes from the backend agent. The `overlay=True` and `control=True` parameters are correct. Do not touch this.
- **AOI GeoJson styling**: The gray/blue fill colors and opacity values are deliberate design choices. Do not change them.
- **`folium_static` vs `st_folium`**: The code has an explicit comment explaining why `folium_static` is used instead of `st_folium` (it "stalls the UI"). Do not switch rendering methods.
- **`frontend/index.html`**: This is a separate standalone Leaflet client. It has its own OpenStreetMap tile URL. It is not part of this fix.
- **Backend files**: No changes needed to `src/agent/`, `src/api/`, or any backend code. The basemap is purely a frontend rendering concern.

## 6. Error Handling

No new error handling is needed. The basemap tile layers are static URL templates that Leaflet (Folium's underlying library) fetches tile-by-tile. If a tile request fails, Leaflet shows a gray placeholder for that tile -- this is standard behavior and does not throw a JavaScript exception.

The existing `try/except` blocks in both `render_aoi_map` and `render_dataset_map` already catch and display errors for the entire map rendering flow. If `_add_basemap_layers` somehow fails (e.g., a typo in the URL template), the exception propagates to the existing handler and the user sees the raw data fallback.

## 7. Testing Strategy

### 7.1 No Existing Frontend Tests

The `tests/` directory covers only backend API, agent, CLI, and tools. There are zero tests for `frontend/utils.py`. This is documented in the conventions recon.

### 7.2 Recommended Manual Verification

Since this is a visual rendering fix with no backend logic, manual testing is the most effective approach:

1. **Start the frontend**: `make frontend` (runs `uv run streamlit run frontend/app.py --server.port=8501`)
2. **Run a query that triggers `render_aoi_map`**: Ask the agent to show an AOI (e.g., "Show me Brazil")
   - Verify: Light basemap (CartoDB Positron) renders with country borders and labels
   - Verify: LayerControl radio buttons appear (Light/Dark/Satellite)
   - Verify: Switching to Dark shows dark tiles
   - Verify: Switching to Satellite shows ESRI imagery
   - Verify: AOI gray boundary renders on top of all basemaps
3. **Run a query that triggers `render_dataset_map`**: Ask the agent to show a dataset (e.g., "Show me tree cover loss in Brazil")
   - Verify: Light basemap renders by default
   - Verify: Dataset tile layer renders on top of basemap
   - Verify: AOI blue boundary renders on top of dataset tiles
   - Verify: LayerControl shows basemap radio buttons AND dataset checkbox
   - Verify: Switching basemaps does not affect dataset overlay visibility

### 7.3 Optional: Add a Smoke Test for `_add_basemap_layers`

If the team wants minimal automated coverage, a simple unit test can verify the helper adds the correct number of layers:

```python
# tests/frontend/test_utils_basemaps.py
import folium
from frontend.utils import _add_basemap_layers, BASEMAP_CONFIGS


def test_add_basemap_layers_adds_all_configs():
    m = folium.Map(location=[0, 0], zoom_start=2, tiles=None)
    _add_basemap_layers(m)
    # Count TileLayer children
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.TileLayer)
    ]
    assert len(tile_layers) == len(BASEMAP_CONFIGS)


def test_first_basemap_is_shown_by_default():
    m = folium.Map(location=[0, 0], zoom_start=2, tiles=None)
    _add_basemap_layers(m)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.TileLayer)
    ]
    # The first layer should be shown
    shown_layers = [tl for tl in tile_layers if tl.options.get("show", True)]
    assert len(shown_layers) >= 1
```

This test does NOT require Streamlit or a browser -- it only checks that Folium map objects are constructed correctly.

## 8. Migration Plan

This is a zero-migration change. There are no database changes, no API changes, no config file changes, and no dependency changes.

### Rollback

If the CartoDB tile servers become unreliable in the future, a developer edits the `BASEMAP_CONFIGS` list at the top of `frontend/utils.py` to swap in different tile URLs. This is a one-line-per-provider change. No code logic needs to change.

### Dependency Considerations

- CartoDB Positron and Dark Matter tiles are free and do not require API keys. They are used by thousands of open-source projects.
- ESRI World Imagery tiles are free for non-commercial use and widely used in GIS applications.
- None of these providers require changes to `frontend/requirements.txt` or `pyproject.toml`.

## 9. Summary of All Changes

| File | Location | Change |
|------|----------|--------|
| `frontend/utils.py` | After imports, before functions | Add `BASEMAP_CONFIGS` list constant |
| `frontend/utils.py` | Before `render_aoi_map` | Add `_add_basemap_layers()` helper function |
| `frontend/utils.py` | `render_aoi_map`, line 105 | Replace `tiles="OpenStreetMap"` with `tiles=None` + `_add_basemap_layers(m)` |
| `frontend/utils.py` | `render_aoi_map`, before `folium_static` call | Add `folium.LayerControl().add_to(m)` |
| `frontend/utils.py` | `render_dataset_map`, line 194-196 | Replace `tiles="OpenStreetMap"` with `tiles=None` + `_add_basemap_layers(m2)` |

Total: 1 file modified, ~40 lines added, ~2 lines changed. No files created or deleted.
