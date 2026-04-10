# Master Implementation Plan: Fix Light Basemap Tile Layer

## 1. Root Cause

The `folium.Map(tiles="OpenStreetMap")` call in `frontend/utils.py` relies on Folium's built-in tile provider name mapping. This mapping resolves to an internal URL that is stale or blocked in the transitive folium version pulled by `streamlit_folium==0.25.0`. The map renders with a blank white background because tile requests silently fail. There is no fallback -- `render_aoi_map` has no `LayerControl` at all, and `render_dataset_map` has a `LayerControl` but no alternative basemap `TileLayer` objects.

## 2. Architecture Decision

**Adopted approach: Draft 2's factory function pattern, with Draft 3's robustness analysis and Draft 4's developer documentation.**

All four drafts converge on the same core fix:
- Replace `tiles="OpenStreetMap"` with `tiles=None` in both map functions
- Add explicit basemap `TileLayer` objects using reliable free tile provider URLs
- Add `LayerControl` to `render_aoi_map` (already present in `render_dataset_map`)
- Use a shared helper to deduplicate basemap setup

**Key design choices where drafts diverged:**

### Helper function signature: `_create_base_map()` vs `_add_basemap_layers()`

Drafts 1, 3, and 4 use `_add_basemap_layers(map_obj)` -- a mutating helper that takes an existing map and adds layers. Draft 2 uses `_create_base_map(center, zoom_start)` -- a factory that returns a fully-configured map.

**Decision: Use `_create_base_map(center, zoom_start)` (Draft 2).** This encapsulates the `tiles=None` + basemap setup in a single call. With the mutating helper, every call site must remember to both pass `tiles=None` AND call the helper -- forgetting either step reintroduces the bug. The factory eliminates this class of error. Draft 2 scored 5 on both Implementability and Requirements Coverage, and the evaluator flagged this as a strength to preserve.

### Config structure: separate constants vs list-of-dicts vs list-of-dicts with `default` flag

Draft 1 uses 6 separate constants (CARTO_LIGHT_TILES, CARTO_LIGHT_ATTR, etc.). Drafts 2-4 use a list-of-dicts. Draft 2 adds a `default: True/False` key. Draft 4 uses position-based default via `show=(i == 0)`.

**Decision: Use list-of-dicts with position-based default (Draft 4's `show=(i == 0)` pattern).** The evaluator flagged Draft 1's separate constants as "more surface area for errors" and Draft 2's `default` flag as "redundant with list ordering." The position-based pattern is the most concise: first entry = default, documented in a comment. No extra key to keep in sync.

### Basemap set: Light+Satellite (Draft 3) vs Light+Dark+Satellite (Drafts 1, 2, 4)

**Decision: Include all three (Light, Dark, Satellite).** The evaluator flagged Draft 3's omission of Dark as a weakness. The issue context explicitly mentions "Light/Dark/Satellite," and the marginal cost of a third basemap entry is one dict in a list. The `show=False` setting on non-default basemaps means no additional tile requests on load.

### API form: `folium.TileLayer` vs `folium.raster_layers.TileLayer`

**Decision: Use `folium.raster_layers.TileLayer` to match existing code.** The existing `render_dataset_map` uses `folium.raster_layers.TileLayer` on line 200. The evaluator's gap analysis flagged this inconsistency across drafts. Using the same form as existing code avoids confusion.

## 3. Failure Mode Analysis

Adopted from Draft 3 (scored 5/5 on Risk Identification) with additions from the gap analysis.

### Current failure modes

| ID | Failure Mode | Root Cause |
|----|-------------|-----------|
| F1 | Light basemap renders blank | `tiles="OpenStreetMap"` resolves to stale URL in folium's internal registry |
| F2 | No fallback when default basemap fails | Only one basemap configured, no LayerControl on AOI maps |
| F3 | `render_aoi_map` has no LayerControl | Users cannot switch basemaps on AOI-only maps |
| F4 | Folium version unpinned | Transitive dep of `streamlit_folium`; behavior may vary across environments |
| F5 | Silent tile load failure | Leaflet loads tiles asynchronously; 404/CORS errors produce no visible Streamlit error |

### Proposed fix risks

| ID | Risk | Mitigation |
|----|------|-----------|
| R1 | CartoDB Positron URL changes or goes down | Multiple basemap providers (CartoDB + ESRI); user can switch via LayerControl |
| R2 | ESRI Satellite URL changes | ESRI World Imagery has been stable for years; LayerControl provides fallback to CartoDB |
| R3 | `overlay=False` interacts badly with LayerControl | Verified: `overlay=False` produces radio buttons (mutually exclusive), which is correct for basemaps |
| R4 | `tiles=None` behaves differently across folium versions | Supported in folium >= 0.12. The version resolved by `streamlit_folium==0.25.0` is compatible. Implementer should verify via `uv.lock` before coding. |
| R5 | Adding basemap TileLayers changes z-order of dataset tiles | Basemaps added first (inside factory), dataset tiles added after -- Leaflet renders later layers on top |
| R6 | Three TileLayer objects cause Leaflet to prefetch all providers | Leaflet only fetches tiles for visible layers. `show=False` layers are not loaded until selected via LayerControl. |
| R7 | ESRI World Imagery usage terms for commercial use | WRI is a non-profit research organization. ESRI World Imagery is free for non-commercial and educational use. If commercial use is a concern, OpenTopoMap or Stamen Terrain are alternatives. Flag for product review if needed. |

## 4. Specific File Changes

### 4.1 File: `frontend/utils.py` (only file requiring modification)

#### Change 1: Add basemap configuration constant (after imports, before function definitions)

Insert after the existing constants (around line 24, near `API_BASE_URL`). Include Draft 4's explanatory comment block documenting WHY explicit URLs are used instead of folium built-in names.

```python
# ──────────────────────────────────────────────────────────
# Basemap Tile Providers
# ──────────────────────────────────────────────────────────
# All basemap configurations live here. To add or change a
# basemap, edit this list. The first entry is the default.
# Each dict maps to folium.raster_layers.TileLayer() kwargs.
#
# Why explicit URLs instead of folium built-in names?
# Folium's built-in "OpenStreetMap" shortcut relies on an
# internal URL registry that has proven unreliable. Explicit
# URLs are deterministic and debuggable.
# ──────────────────────────────────────────────────────────
BASEMAP_CONFIGS = [
    {
        "tiles": (
            "https://{s}.basemaps.cartocdn.com"
            "/light_all/{z}/{x}/{y}{r}.png"
        ),
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org'
            '/copyright">OpenStreetMap</a> contributors '
            '&copy; <a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Light",
    },
    {
        "tiles": (
            "https://{s}.basemaps.cartocdn.com"
            "/dark_all/{z}/{x}/{y}{r}.png"
        ),
        "attr": (
            '&copy; <a href="https://www.openstreetmap.org'
            '/copyright">OpenStreetMap</a> contributors '
            '&copy; <a href="https://carto.com/">CARTO</a>'
        ),
        "name": "Dark",
    },
    {
        "tiles": (
            "https://server.arcgisonline.com/ArcGIS/rest"
            "/services/World_Imagery/MapServer"
            "/tile/{z}/{y}/{x}"
        ),
        "attr": (
            "Tiles &copy; Esri &mdash; Source: Esri, "
            "i-cubed, USDA, USGS, AEX, GeoEye, "
            "Getmapping, Aerogrid, IGN, IGP, UPR-EGP, "
            "and the GIS User Community"
        ),
        "name": "Satellite",
    },
]
```

**String splitting:** All strings are broken to stay within the 79-character line length convention (Ruff config). The `{r}` token in CartoDB URLs handles retina/HiDPI tile requests (noted by Draft 3's edge case analysis).

#### Change 2: Add `_create_base_map()` factory function (before `render_aoi_map`)

```python
def _create_base_map(center, zoom_start):
    """Create a folium Map with basemap tile layer options.

    Returns a folium.Map with Light (default), Dark, and
    Satellite basemap layers. Light is shown by default.
    All basemaps are base layers (overlay=False) so
    LayerControl renders them as radio buttons.

    Args:
        center: [lat, lng] for the map center.
        zoom_start: Initial zoom level.

    Returns:
        A folium.Map instance with basemap layers added.
    """
    m = folium.Map(
        location=center,
        zoom_start=zoom_start,
        tiles=None,
    )
    for i, config in enumerate(BASEMAP_CONFIGS):
        folium.raster_layers.TileLayer(
            tiles=config["tiles"],
            attr=config["attr"],
            name=config["name"],
            overlay=False,
            control=True,
            show=(i == 0),
        ).add_to(m)
    return m
```

**Key parameters explained:**
- `tiles=None` -- suppresses Folium's default OpenStreetMap layer. This is the root cause fix.
- `overlay=False` -- marks basemaps as base layers. In LayerControl, base layers render as radio buttons (mutually exclusive). Dataset tiles use `overlay=True` (checkboxes), ensuring they render independently on top.
- `show=(i == 0)` -- only the first basemap (Light/CartoDB Positron) is visible on init. Others are available via LayerControl but Leaflet does not fetch their tiles until selected.
- `folium.raster_layers.TileLayer` -- matches the existing form used in `render_dataset_map` line 200.

#### Change 3: Modify `render_aoi_map()` (line 105)

**Before:**
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

**After:**
```python
m = _create_base_map(center=center, zoom_start=5)
```

Additionally, add `folium.LayerControl().add_to(m)` after all GeoJson overlays are added (after the subregion rendering block, before the `st.subheader` / `folium_static` call, around line 149):

```python
folium.LayerControl().add_to(m)
```

This gives AOI maps the same basemap-switching UI as dataset maps. Currently `render_aoi_map` has no `LayerControl` -- users cannot switch basemaps on AOI-only maps at all (failure mode F3).

#### Change 4: Modify `render_dataset_map()` (lines 194-196)

**Before:**
```python
m2 = folium.Map(
    location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
)
```

**After:**
```python
m2 = _create_base_map(
    center=center, zoom_start=zoom_start
)
```

**No other changes to `render_dataset_map`.** The existing code already:
- Adds dataset tile layer with `overlay=True` (lines 200-206) -- renders above basemaps
- Adds AOI GeoJson after dataset tiles (lines 209-222) -- renders on top of everything
- Adds `folium.LayerControl().add_to(m2)` last (line 227) -- captures all layers

### 4.2 Layer Rendering Order (Verified)

After the changes, the layer add order in each function:

**`render_aoi_map`:**
1. Basemap tile layers (Light shown, Dark, Satellite) -- via `_create_base_map()`
2. AOI GeoJson overlay (gray fill, weight 2) -- existing code, unchanged
3. Subregion GeoJson overlays (red fill) -- existing code, unchanged
4. LayerControl -- NEW

**`render_dataset_map`:**
1. Basemap tile layers (Light shown, Dark, Satellite) -- via `_create_base_map()`
2. Dataset tile layer (`overlay=True`, `control=True`) -- existing code, unchanged
3. AOI GeoJson overlay (blue fill) -- existing code, unchanged
4. LayerControl -- existing code, unchanged

This satisfies the constraint: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top).

### 4.3 What NOT to Change

Adopted from Draft 4 (evaluator flagged this as a strength for preventing scope creep):

- **Dataset tile layer logic** (lines 200-206): `tile_url`, `overlay=True`, `control=True`, `name=dataset_name` are all correct and untouched.
- **AOI GeoJson styling** in both functions: fill colors, opacity, weight are deliberate design choices.
- **`folium_static` vs `st_folium`**: The code has an explicit comment explaining `folium_static` is used because `st_folium` "stalls the UI." Do not switch.
- **`frontend/index.html`**: Separate standalone Leaflet client. Out of scope -- it uses its own OpenStreetMap URL directly in JavaScript and is not part of the Streamlit frontend. Updating it would be a separate issue.
- **Backend files**: No changes to `src/agent/`, `src/api/`, or any backend code. Basemaps are purely a frontend rendering concern.
- **`frontend/requirements.txt` and `pyproject.toml`**: No new dependencies needed. `folium` is already a transitive dependency of `streamlit_folium`.

## 5. Edge Cases

Adopted from Draft 3 (scored 5/5 on Completeness), with resolution of the hedging the evaluator flagged.

### 5.1 `tiles=None` across folium versions

`tiles=None` is supported in folium >= 0.12 and produces a map with no default tile layer. The `streamlit_folium==0.25.0` dependency resolves a compatible folium version. **Implementation pre-check:** before coding, run `grep folium uv.lock` to confirm the resolved folium version is >= 0.12. This is expected to pass but should be verified.

### 5.2 Both basemap providers are down simultaneously

CartoDB and ESRI being down at the same time is an extremely rare scenario. The LayerControl allows the user to try switching between all three options (Light, Dark from CartoDB; Satellite from ESRI). No further mitigation is practical without adding complexity that exceeds the scope of this fix.

### 5.3 `show=True` on multiple basemaps

Only the first basemap (Light) has `show=True` via the `show=(i == 0)` pattern. The `overlay=False` setting ensures LayerControl treats basemaps as radio buttons (mutually exclusive). If a future developer accidentally makes the first two entries have `show=True`, both would load initially but LayerControl would still enforce mutual exclusivity on user interaction. The unit test (Section 6) validates exactly one basemap is shown by default.

### 5.4 Dataset tile layer obscured by basemap

Basemaps are added FIRST (inside `_create_base_map()`), then dataset tiles are added AFTER (in `render_dataset_map`). Leaflet renders layers in add order (later = on top). Additionally, basemaps use `overlay=False` (base layer group) while dataset tiles use `overlay=True` (overlay group). Leaflet always renders overlays above base layers regardless of add order.

### 5.5 Retina/HiDPI displays

The `{r}` token in CartoDB URLs automatically serves @2x retina tiles when the browser reports a high-DPI display. ESRI World Imagery tiles do not support `{r}` but render acceptably on retina displays -- this is standard behavior across the GIS ecosystem.

### 5.6 Empty `BASEMAP_CONFIGS` list

If a developer empties the list, `_create_base_map()` returns a map with `tiles=None` and no basemap layers -- the map background will be blank. The unit test validates the config list is non-empty (see Section 6).

## 6. Testing Strategy

The evaluator's gap analysis flagged that all four drafts treated automated tests as optional. **Tests are a required deliverable in this plan**, not optional. The project has zero frontend tests, but the new basemap configuration and factory function are pure Python logic that can be tested without Streamlit or a browser.

### 6.1 Required: Unit tests for basemap configuration

**File:** `tests/frontend/__init__.py` (new, empty)
**File:** `tests/frontend/test_basemap.py` (new)

```python
"""Tests for basemap configuration and map factory."""

import folium

from frontend.utils import BASEMAP_CONFIGS, _create_base_map


def test_basemap_configs_non_empty():
    """At least one basemap must be configured."""
    assert len(BASEMAP_CONFIGS) > 0


def test_basemap_configs_have_required_keys():
    """Each basemap config has tiles, attr, and name."""
    required_keys = {"tiles", "attr", "name"}
    for config in BASEMAP_CONFIGS:
        assert required_keys.issubset(config.keys()), (
            f"Missing keys in {config.get('name', 'unknown')}"
        )


def test_exactly_one_default_basemap():
    """Only the first basemap should be shown by default."""
    m = _create_base_map(center=[0, 0], zoom_start=2)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(
            child, folium.raster_layers.TileLayer
        )
    ]
    shown = [
        tl for tl in tile_layers if tl.options.get("show")
    ]
    assert len(shown) == 1
    assert shown[0].tile_name == BASEMAP_CONFIGS[0]["name"]


def test_create_base_map_returns_folium_map():
    """_create_base_map returns a folium.Map instance."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    assert isinstance(m, folium.Map)


def test_create_base_map_has_correct_tile_count():
    """Map has one TileLayer per BASEMAP_CONFIGS entry."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(
            child, folium.raster_layers.TileLayer
        )
    ]
    assert len(tile_layers) == len(BASEMAP_CONFIGS)


def test_create_base_map_has_no_default_osm_tiles():
    """Map should not contain default OpenStreetMap tiles."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "tile.openstreetmap.org" not in html


def test_create_base_map_has_expected_providers():
    """Map contains CartoDB and ESRI tile URLs."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "basemaps.cartocdn.com/light_all" in html
    assert "basemaps.cartocdn.com/dark_all" in html
    assert "arcgisonline.com" in html


def test_basemap_layers_are_base_not_overlay():
    """All basemaps must be base layers (overlay=False)."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(
            child, folium.raster_layers.TileLayer
        )
    ]
    for tl in tile_layers:
        assert tl.options.get("overlay") is False, (
            f"{tl.tile_name} should be a base layer"
        )
```

**Why these tests are sufficient:**
- Config validation catches structural errors (missing keys, empty list)
- Factory output tests verify correct tile providers, correct count, no broken OSM default
- `overlay=False` test catches the critical distinction between base layers and overlays
- Default basemap test catches regressions where the wrong basemap shows on init
- All tests require only `folium` (already a transitive dep) -- no Streamlit, no network, no browser

**Note on imports:** The test imports `from frontend.utils import ...`. This requires `frontend/` to be on the Python path. Run tests with `uv run pytest tests/frontend/ -v` from the project root (uv handles path resolution via the pyproject.toml package config).

### 6.2 Required: Manual verification checklist

Since basemap rendering is visual, automated tests supplement but do not replace manual verification:

| # | Test Case | Steps | Expected Result |
|---|-----------|-------|-----------------|
| T1 | Default basemap loads on AOI map | Run query triggering `render_aoi_map` | Light (CartoDB Positron) basemap visible with country borders and labels |
| T2 | Default basemap loads on dataset map | Run query triggering `render_dataset_map` | Light basemap visible under dataset tiles |
| T3 | LayerControl on AOI map | Load AOI-only map | LayerControl widget visible with Light/Dark/Satellite radio buttons |
| T4 | Switch to Dark | Click Dark in LayerControl | Dark basemap renders correctly |
| T5 | Switch to Satellite | Click Satellite in LayerControl | ESRI satellite imagery renders |
| T6 | Switch back to Light | From Satellite, click Light | Light basemap re-renders |
| T7 | Dataset tiles on top | Load dataset map | Dataset tile layer visible on top of basemap |
| T8 | AOI outline on top of everything | Load dataset map with AOI | Blue AOI boundary visible on top of dataset tiles and basemap |
| T9 | Basemap switch preserves dataset | Switch basemap on dataset map | Dataset tiles remain visible after basemap change |
| T10 | No API key required | Clear all env vars, load map | All three basemaps render without API keys |

## 7. Ruff Compliance

All new code must pass the project's pre-commit hooks (Ruff lint + format):

- Line length: 79 characters (E501 ignored but code should comply where feasible)
- Double quotes for all strings
- Import sorting (isort rules)
- No unused imports
- No trailing whitespace
- End of file newline

The `BASEMAP_CONFIGS` constant uses parenthesized string concatenation to keep long URLs within line-length limits. The `_create_base_map` function and test file should be run through `ruff check` and `ruff format` before committing.

## 8. Migration and Rollback

### Migration

**There is no migration.** This change modifies only frontend rendering code. No database changes, no API changes, no configuration file changes, no new dependencies.

### Deployment

The change takes effect on next frontend container rebuild or Streamlit hot-reload (dev mode). No cache invalidation or state migration needed.

### Rollback

**Instant rollback:** Revert the single commit. No state is persisted by this change.

**Partial rollback (swap providers):** If CartoDB becomes unreliable, edit the `BASEMAP_CONFIGS` list at the top of `frontend/utils.py` to swap tile URLs. This is a one-line-per-provider change -- no rendering logic needs to change. This is the key benefit of the configuration-as-data pattern.

## 9. Implementation Pre-checks

Before writing code, the implementer should:

1. **Verify folium version:** Run `grep -A2 'name = "folium"' uv.lock` to confirm the resolved version is >= 0.12 (required for `tiles=None` support).
2. **Verify `folium.raster_layers.TileLayer` accepts `show` kwarg:** Check folium docs or source for the resolved version. If `show` is not supported, fall back to adding the default basemap first without `show` and relying on Leaflet's behavior of showing the last-added base layer (or the first one with no explicit show flag).
3. **Verify ESRI World Imagery terms:** Confirm WRI's use case is compatible with ESRI's terms of service for the World Imagery tile layer.

## 10. Summary of Deliverables

| Item | File | Action |
|------|------|--------|
| Basemap config constant | `frontend/utils.py` | Add `BASEMAP_CONFIGS` list with comment block |
| Map factory function | `frontend/utils.py` | Add `_create_base_map(center, zoom_start)` |
| Fix `render_aoi_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with `_create_base_map()` call; add `LayerControl` |
| Fix `render_dataset_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with `_create_base_map()` call |
| Test package init | `tests/frontend/__init__.py` | New empty file |
| Basemap unit tests | `tests/frontend/test_basemap.py` | 8 tests covering config structure, factory output, tile providers, layer types |

**Total: 1 file modified, 2 files created (tests). ~60 lines added to `frontend/utils.py`, ~80 lines in test file. Zero backend changes. Zero new dependencies.**
