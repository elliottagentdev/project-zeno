# Draft Plan 3: Robustness-First Implementation

## Lens: Failure Modes, Error Handling, Validation, and Recovery

---

## 1. Failure Mode Analysis

Before designing the fix, we must enumerate every way the current code fails and every way the proposed fix could fail.

### 1.1 Current Failure Modes

| # | Failure Mode | Root Cause | Impact |
|---|-------------|-----------|--------|
| F1 | Light basemap renders blank | `tiles="OpenStreetMap"` relies on Folium's built-in tile provider mapping, which may resolve to a stale or blocked URL in the installed folium version | User sees no geographic context; must manually switch to Satellite |
| F2 | No fallback when default basemap fails | Only one basemap is configured; if it fails, there is no automatic recovery | Complete loss of spatial orientation |
| F3 | `render_aoi_map` has no LayerControl | Users cannot switch basemaps on AOI-only maps at all | No workaround available for AOI maps |
| F4 | Folium version unpinned | `folium` is a transitive dependency of `streamlit_folium==0.25.0`; different environments may resolve different folium versions with different built-in tile provider behavior | Non-reproducible rendering across environments |
| F5 | Silent tile load failure | Folium/Leaflet loads tiles asynchronously; a 404 or CORS error on tile URLs produces no visible error in the Streamlit UI | User sees blank tiles with no explanation |

### 1.2 Proposed Fix Failure Modes (What Could Go Wrong With Our Fix)

| # | Risk | Mitigation |
|---|------|-----------|
| R1 | CartoDB Positron tile URL changes or goes down | Use multiple basemap providers so user can switch; document fallback URLs |
| R2 | ESRI Satellite tile URL changes | Same as above; ESRI World Imagery has been stable for years |
| R3 | Attribution strings become incorrect | Define attribution as named constants; easy to update in one place |
| R4 | `overlay=False` on basemap TileLayers interacts badly with `LayerControl` | Test that only one basemap is active at a time (radio button behavior in LayerControl) |
| R5 | Adding basemap TileLayers changes z-order of dataset tiles | Verify layer add order: basemaps first, then dataset tiles, then GeoJson overlays |
| R6 | `render_aoi_map` gaining LayerControl breaks existing UI expectations | LayerControl is additive; it only shows if multiple layers exist. Adding it is safe. |
| R7 | Ruff linting fails on new code | All new code must comply with line-length 79, double quotes, import sorting |

---

## 2. Architecture: Defensive Basemap Layer Configuration

### 2.1 Design Principle

Define basemap tile layers as **explicit URL-based TileLayer objects** rather than relying on Folium's built-in tile name shortcuts. This eliminates dependency on Folium's internal tile provider registry, which is the root cause of the current failure.

### 2.2 Constants Definition

Add a module-level constants block in `frontend/utils.py` (after existing imports, before function definitions) defining basemap configurations:

```python
# Basemap tile layer configurations
# Using explicit URLs to avoid dependency on folium's built-in tile registry
BASEMAP_CONFIGS = [
    {
        "name": "Light",
        "tiles": "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org/copyright">'
            "OpenStreetMap</a> contributors &copy; "
            '<a href="https://carto.com/attributions">CARTO</a>'
        ),
        "overlay": False,
        "control": True,
        "show": True,  # Default visible basemap
    },
    {
        "name": "Satellite",
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}"
        ),
        "attr": (
            "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, "
            "USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, "
            "UXL, and the GIS User Community"
        ),
        "overlay": False,
        "control": True,
        "show": False,
    },
]
```

### 2.3 Helper Function: `_add_basemap_layers(map_obj)`

Create a private helper to add basemap layers to any folium Map object. This ensures consistent basemap setup across both `render_aoi_map` and `render_dataset_map`, eliminating duplication and reducing the chance of divergent behavior.

```python
def _add_basemap_layers(map_obj):
    """Add basemap tile layers to a folium map.

    Adds Light (CartoDB Positron) and Satellite (ESRI) basemaps.
    Light is shown by default. Both are base layers (overlay=False)
    so LayerControl renders them as radio buttons.
    """
    for config in BASEMAP_CONFIGS:
        folium.raster_layers.TileLayer(
            tiles=config["tiles"],
            attr=config["attr"],
            name=config["name"],
            overlay=config["overlay"],
            control=config["control"],
            show=config.get("show", False),
        ).add_to(map_obj)
```

### 2.4 Map Construction Pattern (Both Functions)

Replace `folium.Map(location=center, zoom_start=N, tiles="OpenStreetMap")` with:

```python
m = folium.Map(location=center, zoom_start=N, tiles=None)
_add_basemap_layers(m)
```

Setting `tiles=None` prevents Folium from adding its default OpenStreetMap layer. We then add our own explicit basemap layers via the helper.

---

## 3. Specific File Changes

### 3.1 File: `frontend/utils.py`

This is the **only file requiring modification**. No backend, API, database, or migration changes are needed.

#### Change 1: Add basemap constants (after imports, before function definitions)

**Location:** After the existing import block (around line 20-30), before `render_aoi_map`.

Add the `BASEMAP_CONFIGS` list and `_add_basemap_layers()` helper as defined in Section 2.2 and 2.3 above.

#### Change 2: Modify `render_aoi_map()` (line 105)

**Before:**
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

**After:**
```python
m = folium.Map(location=center, zoom_start=5, tiles=None)
_add_basemap_layers(m)
```

Additionally, add `folium.LayerControl().add_to(m)` **after** all GeoJson overlays are added (after the subregion loop, before `folium_static`). This gives AOI maps the same basemap-switching capability as dataset maps.

**Insert location:** Between the subregion rendering block (ending around line 147) and `st.subheader("...")` (line 150):

```python
# Add layer control for basemap switching
folium.LayerControl().add_to(m)
```

#### Change 3: Modify `render_dataset_map()` (lines 194-195)

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

The existing `folium.LayerControl().add_to(m2)` on line 227 remains unchanged. The dataset tile layer (lines 200-206) and AOI overlay (lines 209-223) also remain unchanged.

### 3.2 Layer Ordering Verification

After the changes, the layer add order in each function is:

**`render_aoi_map`:**
1. `folium.Map(tiles=None)` -- empty base
2. `_add_basemap_layers(m)` -- Light (shown) + Satellite basemaps
3. AOI GeoJson overlay (lines 108-119)
4. Subregion GeoJson overlays (lines 122-145)
5. `folium.LayerControl().add_to(m)` -- NEW

**`render_dataset_map`:**
1. `folium.Map(tiles=None)` -- empty base
2. `_add_basemap_layers(m2)` -- Light (shown) + Satellite basemaps
3. Dataset TileLayer with `overlay=True` (lines 200-206) -- UNCHANGED
4. AOI GeoJson overlay (lines 209-223) -- UNCHANGED
5. `folium.LayerControl().add_to(m2)` (line 227) -- UNCHANGED

This ordering guarantees: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top), satisfying the constraint in the acceptance criteria.

### 3.3 What We Do NOT Change

- **Dataset tile layer logic** (lines 200-206): The `tile_url`, `overlay=True`, `control=True`, and `name=dataset_name` remain untouched.
- **AOI overlay logic** in both functions: GeoJson styling, popup, tooltip unchanged.
- **Center/zoom calculation logic**: Unchanged.
- **`folium_static()` calls**: Unchanged.
- **Backend code**: No changes to `src/agent/`, `src/api/`, or any other backend files.
- **`frontend/index.html`**: The standalone Leaflet client is a separate system and out of scope.

---

## 4. Edge Cases and Validation

### 4.1 Edge Case: `tiles=None` Behavior Across Folium Versions

**Risk:** Different folium versions may handle `tiles=None` differently.

**Validation:** In folium >= 0.12, `tiles=None` is explicitly supported and produces a map with no default tile layer. The `streamlit_folium==0.25.0` dependency pulls a compatible folium version. However, we should verify this works by checking the folium version in `uv.lock`.

**Fallback:** If `tiles=None` is not supported in the resolved folium version, an alternative is `tiles=""` (empty string), which also suppresses the default layer in most versions. As a last resort, we could pass `tiles="OpenStreetMap"` and accept the duplicate layer (the explicit CartoDB layer would still render on top).

### 4.2 Edge Case: Both Basemap Tile Providers Are Down

**Impact:** User sees a blank map background.

**Mitigation:** This is a rare scenario (both CartoDB and ESRI down simultaneously). The LayerControl allows the user to try switching between them. No further mitigation is practical without adding complexity.

### 4.3 Edge Case: `show=True` on Multiple Basemaps

**Risk:** If multiple basemaps have `show=True`, multiple tile layers load simultaneously, wasting bandwidth.

**Validation:** Only the Light basemap has `show=True`. The `overlay=False` setting ensures LayerControl treats them as radio buttons (mutually exclusive).

### 4.4 Edge Case: Dataset Tile Layer Obscured by Basemap

**Risk:** If basemap layers are added after the dataset layer, they could render on top.

**Validation:** Our implementation adds basemaps FIRST (via `_add_basemap_layers` called immediately after map creation), then dataset tiles, then AOI overlays. Folium/Leaflet renders layers in add order (later = on top), so this is correct.

### 4.5 Edge Case: Retina/HiDPI Displays

The `{r}` token in the CartoDB URL handles retina tiles. ESRI tiles do not support `{r}` but render acceptably on retina displays.

---

## 5. Testing Strategy

### 5.1 Reality Check: No Existing Frontend Tests

The project has **zero frontend tests** (confirmed in `conventions.md`). The `tests/` directory covers only backend API, agent, CLI, and tools. Adding a comprehensive test suite for the frontend is out of scope for this fix.

### 5.2 Recommended Manual Testing Protocol

Since the fix is purely visual (tile rendering), manual testing is the primary validation method:

| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| T1 | Default basemap loads on AOI map | Run a query that triggers `render_aoi_map` | Light (CartoDB Positron) basemap visible with country borders and labels |
| T2 | Default basemap loads on dataset map | Run a query that triggers `render_dataset_map` | Light basemap visible under dataset tiles |
| T3 | Satellite switching works | Click Satellite in LayerControl | Map switches to ESRI satellite imagery |
| T4 | Light switching works (from Satellite) | Switch to Satellite, then back to Light | Light basemap re-renders correctly |
| T5 | Dataset tiles render on top of basemap | Load a dataset map | Dataset tile layer visible on top of basemap |
| T6 | AOI outline renders on top of everything | Load a dataset map with AOI | Blue AOI boundary visible on top of dataset tiles and basemap |
| T7 | LayerControl available on AOI map | Load an AOI-only map | LayerControl widget visible with Light/Satellite radio buttons |
| T8 | No API key needed | Clear all env vars, load map | Basemap still renders (no Mapbox/API key required) |

### 5.3 Optional: Unit Test for Basemap Configuration

If we want minimal automated coverage, we can add a simple unit test that verifies the basemap configuration is well-formed without requiring a running Streamlit instance:

**File:** `tests/frontend/__init__.py` (new, empty)
**File:** `tests/frontend/test_utils.py` (new)

```python
"""Tests for frontend basemap configuration."""

import folium

from frontend.utils import BASEMAP_CONFIGS, _add_basemap_layers


def test_basemap_configs_are_valid():
    """Each basemap config has required keys."""
    required_keys = {"name", "tiles", "attr", "overlay", "control"}
    for config in BASEMAP_CONFIGS:
        assert required_keys.issubset(config.keys()), (
            f"Missing keys in {config.get('name', 'unknown')}"
        )
        assert config["overlay"] is False, (
            f"{config['name']} must be a base layer"
        )


def test_exactly_one_default_basemap():
    """Exactly one basemap should be shown by default."""
    shown = [c for c in BASEMAP_CONFIGS if c.get("show")]
    assert len(shown) == 1, (
        f"Expected 1 default basemap, got {len(shown)}"
    )


def test_add_basemap_layers_adds_to_map():
    """Basemap layers are added to a folium map object."""
    m = folium.Map(location=[0, 0], zoom_start=2, tiles=None)
    _add_basemap_layers(m)
    # Verify tile layers were added (folium stores children)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.raster_layers.TileLayer)
    ]
    assert len(tile_layers) == len(BASEMAP_CONFIGS)
```

These tests are lightweight, require no Streamlit runtime, and validate that the configuration is structurally correct.

### 5.4 Smoke Test via Makefile

The project has `make frontend` which runs `uv run streamlit run frontend/app.py --server.port=8501`. After applying the fix, run this and manually verify maps render correctly.

---

## 6. Migration and Rollback Plan

### 6.1 Migration

**There is no migration.** This change modifies only frontend rendering code. No database changes, no API changes, no configuration file changes.

### 6.2 Rollback

**Instant rollback:** Revert the single commit. The change is entirely in `frontend/utils.py` (and optionally the new test file). No state is persisted by this change.

### 6.3 Deployment

No special deployment steps. The change takes effect on next frontend container rebuild or hot-reload (Streamlit watches for file changes in dev mode).

---

## 7. Ruff Compliance Checklist

All new code must comply with the project's Ruff configuration:

- [ ] Line length: 79 chars (E501 ignored but aim for compliance)
- [ ] Double quotes for all strings
- [ ] Import sorting (isort rules)
- [ ] No unused imports
- [ ] No trailing whitespace

The `BASEMAP_CONFIGS` constant uses parenthesized string concatenation to keep long URLs within line-length limits. The `_add_basemap_layers` function is compact and should not trigger any linting issues.

---

## 8. Summary of Deliverables

| Item | File | Action |
|------|------|--------|
| Basemap constants | `frontend/utils.py` | Add `BASEMAP_CONFIGS` constant after imports |
| Basemap helper | `frontend/utils.py` | Add `_add_basemap_layers()` function |
| Fix `render_aoi_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with `tiles=None` + helper; add LayerControl |
| Fix `render_dataset_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with `tiles=None` + helper |
| Unit tests (optional) | `tests/frontend/test_utils.py` | Validate basemap config structure |

**Total lines changed:** ~50 lines added, ~2 lines modified in `frontend/utils.py`.
**Risk level:** Low. Single-file change, no backend impact, instant rollback.
