# Final Implementation Specification: Fix Light Basemap Tile Layer

## Issue

The light basemap tile layer fails to render on map initialization in the Streamlit frontend. Users see a blank white background and must switch to Satellite as a workaround. The root cause is `folium.Map(tiles="OpenStreetMap")` in `frontend/utils.py` producing a non-rendering basemap. The fix replaces the built-in tile name with explicit, reliable free tile provider URLs and adds basemap switching to all map views.

---

## 1. Requirements Traceability Matrix

| Req ID | Requirement (from PROMPT.md) | Spec Section | How Addressed |
|--------|------------------------------|--------------|---------------|
| JS1 | Default basemap visible on map load for geographic context | 3.2, 3.3, 3.4 | `_create_base_map()` factory uses CartoDB Positron (Light) as default with `show=(i == 0)` |
| P1 | Functioning basemap visible immediately on any query result | 3.3, 3.4 | Both `render_aoi_map` and `render_dataset_map` replaced to use `_create_base_map()` |
| P2 | AOI boundary and data layers not obscured by basemap | 3.5 | Basemaps use `overlay=False` (base layer group); dataset tiles use `overlay=True`; add order enforced |
| P3 | Users do not need Satellite workaround | 3.2, 3.3 | CartoDB Positron replaces broken OpenStreetMap as default |
| C1 | No paid Mapbox API key -- free tile provider | 3.1 | CartoDB Positron (free, no key), CartoDB Dark (free, no key), ESRI World Imagery (free for non-commercial) |
| C2 | LayerControl for basemap switching remains accessible | 3.3, 3.4 | LayerControl present in both map functions; three basemaps with radio button switching |
| C3 | Must not touch dynamic dataset layer rendering logic | 3.6 | Dataset tile layer code (lines 200-206) is untouched |
| C4 | Layer order: basemap (bottom) -> dataset tiles (middle) -> AOI (top) | 3.5 | Factory adds basemaps first; existing code adds dataset then AOI; Leaflet renders overlays above base layers |
| AC1 | Any query renders visible geographic basemap by default | 3.3, 3.4 | Codebase audit confirms exactly 2 `folium.Map(` call sites -- both are modified |
| AC2 | Light basemap renders country outlines, terrain, labels | 3.1 | CartoDB Positron includes borders, labels, terrain shading |
| AC3 | Satellite imagery continues to work | 3.1 | ESRI World Imagery included in BASEMAP_CONFIGS |
| AC4 | No additional API keys or credentials needed | 3.1 | All three providers are keyless |
| AC5 | AOI boundary renders on top of all layers | 3.5 | GeoJson added after all tile layers in both functions |
| AC6 | Layer order correct for all map renders | 3.5 | Documented and verified for both `render_aoi_map` and `render_dataset_map` |

**Gaps:** None. All requirements are addressed.

---

## 2. Red Team Resolution Log

### Red Team Report 1 (Requirements Coverage)

| # | Finding | Resolution |
|---|---------|------------|
| RT1-2.1 | No verification that only two map-rendering code paths exist | **Resolved.** Grep for `folium.Map(` across the entire codebase confirms exactly 2 call sites in `frontend/utils.py` (lines 105 and 194). No other files create folium maps. |
| RT1-2.2 | Layer ordering has no automated regression guard | **Deferred (LOW).** Adding an integration test for layer order requires instantiating `render_dataset_map` with mock data, which depends on `ZenoClient` and network calls. The factory pattern structurally enforces basemaps-first. Manual test T7/T8 covers this. Follow-up: add integration test when frontend test infrastructure matures. |
| RT1-2.3 | `show` kwarg compatibility not fully resolved | **Resolved.** Folium 0.17.0 (locked in `uv.lock`) supports `show` parameter. Pre-check is removed from spec; `show=(i == 0)` is the definitive approach. |
| RT1-2.4 | `frontend/index.html` may have same bug | **Deferred (LOW).** `index.html` is a standalone Leaflet client, not part of the Streamlit frontend. It uses `tile.openstreetmap.org` directly (not folium). If it is also broken, it is a separate issue. |
| RT1-2.5 | AC2 wording ambiguity ("over the AOI") | **Resolved.** Interpreted as "in the geographic region of the AOI" per C4 constraint (basemap at bottom). |
| RT1-2.6 | Tests rely on internal folium API | **Resolved.** Tests updated to use `tl.show` and `tl.overlay` (direct attributes) instead of `tl.options.get()`. See Section 4. |

### Red Team Report 2 (Ambiguity Analysis)

| # | Finding | Resolution |
|---|---------|------------|
| RT2-1 | Test code uses `tl.options.get("show")` -- wrong attribute access | **Resolved.** Tests corrected to use `tl.show` and `tl.overlay` direct attributes. |
| RT2-2 | BASEMAP_CONFIGS placement ambiguity (line 24 vs line 17) | **Resolved.** Insert after line 16 (end of `API_BASE_URL`), before line 19 (the TODO comment). |
| RT2-3 | LayerControl placement in `render_aoi_map` -- inside or outside try/except | **Resolved.** Place after the except block (line 148), before `st.subheader` (line 149). LayerControl always renders regardless of subregion failures. |
| RT2-4 | Line numbers shift after insertions | **Resolved.** Spec uses before/after code snippets rather than absolute line numbers for the changes. Implementer applies changes top-to-bottom. |
| RT2-5 | `render_dataset_map` zoom_start conditional logic | **Resolved.** Factory accepts `zoom_start` as parameter; caller passes the variable. No change needed. |
| RT2-6 | Test import path -- `frontend/` not a Python package | **Resolved.** Tests use `sys.path` insertion in a `conftest.py` rather than relying on package resolution. See Section 4.2. |
| RT2-7 | Section 9.2 `show` kwarg fallback contradicts Section 2 | **Resolved.** Fallback removed. `show` is confirmed supported in folium 0.17.0. |
| RT2-8 | Root cause claim unverified (OSM URL is valid) | **Acknowledged.** The exact failure mechanism (CSP, network, folium bug) is uncertain. However, replacing built-in tile name resolution with explicit URLs is a robust fix regardless of root cause -- it removes the dependency on folium's internal xyzservices registry. If the issue is environmental (firewall/CSP), the fix still improves the situation by providing multiple providers and a LayerControl for fallback. |
| RT2-9 | String splitting convention new to the file | **Resolved.** Use parenthesized string concatenation per Python style guide (PEP 8). E501 is ignored by Ruff config but keeping lines reasonable aids readability. |
| RT2-10 | Decorative comment block new to the file | **Resolved.** Simplified to a standard block comment without decoration. |
| RT2-11 | Leading underscore on `_create_base_map` new convention | **Kept.** The function is an internal helper not meant to be called from outside `utils.py`. The underscore convention is standard Python. |
| RT2-12 | Docstring style inconsistency (Google-style vs simple) | **Resolved.** Use simple description-only docstring to match existing conventions. |
| RT2-13 | `tests/frontend/__init__.py` diverges from test directory convention | **Resolved.** No `__init__.py` files created in test directories. Use `conftest.py` with `sys.path` instead. |

### Red Team Report 3 (Codebase Validation)

| # | Finding | Resolution |
|---|---------|------------|
| RT3-E1 | Test `tl.options.get("show")` wrong -- use `tl.show` | **Resolved.** Fixed in Section 4. |
| RT3-E2 | Test `tl.options.get("overlay")` wrong -- use `tl.overlay` | **Resolved.** Fixed in Section 4. |
| RT3-E3 | `API_BASE_URL` at line 13, not "around line 24" | **Resolved.** Corrected placement instruction. |
| RT3-W1 | Test imports fail -- `frontend/` not a package | **Resolved.** `conftest.py` adds `frontend/` to `sys.path`. |
| RT3-W2 | `frontend/requirements.txt` outdated vs `pyproject.toml` | **Out of scope.** Not related to this fix. |
| RT3-W3 | `folium_static` LayerControl interactivity | **Verified.** `folium_static` renders full HTML/JS in an iframe. LayerControl is interactive. |

### Red Team Report 4 (Contradictions, Edge Cases, Failure Modes)

| # | Finding | Resolution |
|---|---------|------------|
| RT4-1 | Tests use wrong attribute access (`tl.options.get`) | **Resolved.** See above. |
| RT4-2 | Section 2 vs 9.2 contradiction on `show` kwarg | **Resolved.** Pre-check removed; `show` confirmed supported. |
| RT4-3 | LayerControl must be added last | **Resolved.** Placement specified: after all layers, before `folium_static`. Code comment added noting this constraint. |
| RT4-4 | Malformed `aoi_data` produces map at [0,0] | **Deferred (LOW).** Pre-existing behavior. The fix improves it (visible basemap instead of blank white). Addressing the fallback UX is a separate concern. |
| RT4-5 | ESRI `{y}/{x}` order could be "fixed" by unaware dev | **Resolved.** Inline comment added in BASEMAP_CONFIGS noting ESRI uses `{z}/{y}/{x}` intentionally. |
| RT4-7 | No fallback for complete tile provider unavailability | **Deferred (MEDIUM).** Three providers across two CDNs (CartoDB, ESRI) is sufficient for most deployments. For firewall-restricted environments, `BASEMAP_CONFIGS` can be edited. Adding env-var-based config is out of scope. Severity: MEDIUM. Follow-up: document tile provider customization in deployment docs. |
| RT4-8 | LayerControl dropdown may clip in 400px iframe | **Deferred (LOW).** Three basemap radio buttons plus one dataset checkbox is a small control. Manual testing (T3) will catch clipping. If it occurs, iframe height can be increased. |
| RT4-9 | "Zero new dependencies" vs test import resolution | **Resolved.** No new pip/uv dependencies. The `conftest.py` path manipulation is a test infrastructure change, not a dependency. |
| RT4-10 | `BASEMAP_CONFIGS` is mutable list | **Deferred (LOW).** Using a tuple would be more defensive but is not necessary for a module-level constant. Streamlit's threading model does not mutate module constants. |
| RT4-11 | HTML injection via attribution strings | **Deferred (LOW).** Attribution values are hardcoded constants. If made configurable in the future, sanitization would be needed. |
| RT4-13 | `{r}` retina token docs misleading without `detect_retina=True` | **Resolved.** Removed misleading comment about retina. The `{r}` token resolves to empty string by default, which is correct. Tiles load fine. |
| RT4-6 | ESRI subdomain handling implicit | **No action needed.** Informational only. |
| RT4-12 | Tile layer type check in tests | **No action needed.** Informational only. |

---

## 3. Implementation Plan

### Prerequisites

Before writing any code, verify:
1. Folium version in `uv.lock` is 0.17.0 (already confirmed by red team). Run: `grep -A2 'name = "folium"' uv.lock`
2. No other `folium.Map(` call sites exist beyond `frontend/utils.py` lines 105 and 194 (already confirmed by grep).

### 3.1 Step 1: Add BASEMAP_CONFIGS constant to `frontend/utils.py`

**Location:** After line 16 (end of `API_BASE_URL` definition), before line 19 (the TODO comment).

**Insert this code:**

```python

# Basemap tile providers. The first entry is the default.
# Explicit URLs used instead of folium built-in names because
# folium's internal URL registry has proven unreliable.
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
        # ESRI uses {z}/{y}/{x} order (not {z}/{x}/{y})
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

**Verification:** Constant is a list of 3 dicts, each with `tiles`, `attr`, `name` keys. First entry is Light (CartoDB Positron).

### 3.2 Step 2: Add `_create_base_map()` factory function to `frontend/utils.py`

**Location:** After the `BASEMAP_CONFIGS` constant, before the existing `generate_markdown` function.

**Insert this code:**

```python

def _create_base_map(center, zoom_start):
    """Create a folium Map with Light, Dark, and Satellite basemaps."""
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

**Key parameters:**
- `tiles=None` -- suppresses folium's default OpenStreetMap layer (the root cause fix)
- `overlay=False` -- marks as base layer (radio buttons in LayerControl, mutually exclusive)
- `show=(i == 0)` -- only Light is visible on init; others load on demand
- `folium.raster_layers.TileLayer` -- matches existing usage at line 200

**Verification:** Function returns a `folium.Map` with 3 TileLayer children, no default OSM tiles.

### 3.3 Step 3: Modify `render_aoi_map()` in `frontend/utils.py`

**Change A -- Replace map creation (line 105):**

Before:
```python
        m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

After:
```python
        m = _create_base_map(center=center, zoom_start=5)
```

**Change B -- Add LayerControl (after the subregion try/except block, before `st.subheader`):**

Insert between line 147 (`st.warning(...)`) and line 149 (`st.subheader(...)`):

```python

        # LayerControl must be added after all layers
        folium.LayerControl().add_to(m)

```

**Verification:** AOI maps now have basemap switching UI. LayerControl is outside the subregion try/except so it always renders.

### 3.4 Step 4: Modify `render_dataset_map()` in `frontend/utils.py`

**Change -- Replace map creation (lines 194-196):**

Before:
```python
        m2 = folium.Map(
            location=center, zoom_start=zoom_start, tiles="OpenStreetMap"
        )
```

After:
```python
        m2 = _create_base_map(
            center=center, zoom_start=zoom_start
        )
```

**No other changes to this function.** The existing code already:
- Adds dataset tile layer with `overlay=True` (line 200-206)
- Adds AOI GeoJson after dataset tiles (lines 209-222)
- Adds `folium.LayerControl().add_to(m2)` last (line 227)

**Verification:** Dataset maps use the same basemap factory. Existing layer order preserved.

### 3.5 Layer Rendering Order (Post-Change)

**`render_aoi_map`:**
1. Basemap tile layers (Light shown, Dark hidden, Satellite hidden) -- via `_create_base_map()`
2. AOI GeoJson overlay (gray fill, weight 2) -- unchanged
3. Subregion GeoJson overlays (red fill) -- unchanged
4. LayerControl -- NEW

**`render_dataset_map`:**
1. Basemap tile layers (Light shown, Dark hidden, Satellite hidden) -- via `_create_base_map()`
2. Dataset tile layer (`overlay=True`, `control=True`) -- unchanged
3. AOI GeoJson overlay (blue fill) -- unchanged
4. LayerControl -- unchanged

Leaflet always renders overlays (`overlay=True`) above base layers (`overlay=False`). Within each group, later-added layers render on top. This guarantees: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top).

### 3.6 What NOT to Change

- **Dataset tile layer logic** (lines 200-206): `tile_url`, `overlay=True`, `control=True`, `name=dataset_name` are correct and untouched.
- **AOI GeoJson styling** in both functions: fill colors, opacity, weight are design choices.
- **`folium_static` vs `st_folium`**: Code comment explains `folium_static` is used because `st_folium` stalls the UI. Do not switch.
- **`frontend/index.html`**: Standalone Leaflet client, out of scope.
- **Backend files**: No changes to `src/agent/`, `src/api/`, or any backend code.
- **`pyproject.toml` and `frontend/requirements.txt`**: No new dependencies.

### 3.7 Implementation Order and Dependencies

| Step | Depends On | File | Action |
|------|-----------|------|--------|
| 1 | None | `frontend/utils.py` | Add `BASEMAP_CONFIGS` constant |
| 2 | Step 1 | `frontend/utils.py` | Add `_create_base_map()` function |
| 3 | Step 2 | `frontend/utils.py` | Modify `render_aoi_map()` |
| 4 | Step 2 | `frontend/utils.py` | Modify `render_dataset_map()` |
| 5 | Steps 1-2 | `tests/frontend/conftest.py` | Create test conftest with path setup |
| 6 | Step 5 | `tests/frontend/test_basemap.py` | Create unit tests |

Steps 3 and 4 are independent and can be done in either order. Steps 5 and 6 can be done after all code changes.

---

## 4. Testing Strategy

### 4.1 Test Infrastructure Setup

The `frontend/` directory is NOT a Python package (no `__init__.py`, not in `pyproject.toml` packages). Tests need path manipulation.

**File: `tests/frontend/conftest.py` (NEW)**

```python
import sys
from pathlib import Path

# Add frontend/ to sys.path so tests can import from it
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent.parent / "frontend")
)
```

This allows `from utils import BASEMAP_CONFIGS, _create_base_map` in test files (using bare module name, matching how frontend code imports its own modules).

### 4.2 Unit Tests

**File: `tests/frontend/test_basemap.py` (NEW)**

```python
"""Tests for basemap configuration and map factory."""

import folium

from utils import BASEMAP_CONFIGS, _create_base_map


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
    shown = [tl for tl in tile_layers if tl.show]
    assert len(shown) == 1
    assert shown[0].tile_name == BASEMAP_CONFIGS[0]["name"]


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
        assert tl.overlay is False, (
            f"{tl.tile_name} should be a base layer"
        )
```

**Key corrections from red team findings:**
- `tl.show` instead of `tl.options.get("show")` (RT2-1, RT3-E1, RT4-1)
- `tl.overlay` instead of `tl.options.get("overlay")` (RT3-E2, RT4-1)
- `from utils import ...` instead of `from frontend.utils import ...` (RT2-6, RT3-W1)
- No `__init__.py` in test directory (RT2-13)

**Run command:** `uv run pytest tests/frontend/ -v`

**Note on internal API usage:** Tests access `m._children`, `tl.show`, `tl.tile_name`, and `tl.overlay`. These are folium implementation details that could change in future versions. The `_repr_html_()` based tests (`test_create_base_map_has_no_default_osm_tiles`, `test_create_base_map_has_expected_providers`) are more stable alternatives that validate the same behavior.

### 4.3 Manual Verification Checklist

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

---

## 5. Risk Register

| ID | Risk | Severity | Likelihood | Mitigation |
|----|------|----------|-----------|------------|
| R1 | CartoDB Positron URL changes or goes down | MEDIUM | LOW | Multiple providers (CartoDB + ESRI); user can switch via LayerControl |
| R2 | ESRI World Imagery URL changes | LOW | LOW | Stable for years; CartoDB provides fallback via LayerControl |
| R3 | Root cause is CSP/network, not folium tile resolution | MEDIUM | MEDIUM | Fix still improves situation: multiple providers, explicit URLs are debuggable, LayerControl provides manual fallback. If all three providers are blocked, deployers can edit `BASEMAP_CONFIGS` for internal tile servers. |
| R4 | `tiles=None` behavior changes in future folium versions | LOW | LOW | Covered by `test_create_base_map_has_no_default_osm_tiles` test |
| R5 | ESRI World Imagery terms for commercial use | LOW | LOW | WRI is a non-profit. ESRI World Imagery is free for non-commercial/educational use. If concern arises, replace with OpenTopoMap. |
| R6 | Tests break on folium upgrade (internal API changes) | MEDIUM | MEDIUM | HTML-based tests (`_repr_html_()`) are stable fallbacks. Attribute-based tests document current API and will fail loudly on upgrade, prompting review. |
| R7 | Firewall-restricted deployments block all tile CDNs | MEDIUM | LOW | `BASEMAP_CONFIGS` is a module-level constant -- deployers can edit it for internal tile servers. Document in deployment notes. |

---

## 6. Deliverables Summary

| Item | File | Action |
|------|------|--------|
| Basemap config constant | `frontend/utils.py` | Add `BASEMAP_CONFIGS` list after `API_BASE_URL` |
| Map factory function | `frontend/utils.py` | Add `_create_base_map(center, zoom_start)` |
| Fix `render_aoi_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with factory call; add `LayerControl` |
| Fix `render_dataset_map` | `frontend/utils.py` | Replace `tiles="OpenStreetMap"` with factory call |
| Test conftest | `tests/frontend/conftest.py` | NEW -- adds `frontend/` to `sys.path` |
| Basemap unit tests | `tests/frontend/test_basemap.py` | NEW -- 8 tests covering config, factory, providers, layer types |

**Total: 1 file modified (`frontend/utils.py`), 2 files created (tests). Approximately 60 lines added to `frontend/utils.py`, 90 lines in test files. Zero backend changes. Zero new dependencies.**

### Rollback

Revert the single commit. No persistent state is affected by this change. For partial rollback (swap tile providers), edit `BASEMAP_CONFIGS` entries only.
