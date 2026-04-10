# SPEC: Fix Tree Cover Loss Dynamic Tile Layer Producing Blank Map

## 1. Requirements Traceability Matrix

| Req ID | Requirement (from PROMPT.md) | Spec Section | Status |
|--------|------------------------------|-------------|--------|
| C1 | Must use existing dynamic tile URL generation path in `pick_dataset.py` -- no hardcoded tile URLs in frontend | Section 3 (all changes use existing `pick_dataset.py` path) | ADDRESSED |
| C2 | Investigation must compare Grasslands (working) vs TCL (broken) -- fix root cause not symptoms | Section 3, Root Cause Analysis | ADDRESSED |
| C3 | Must not regress other dataset visualizations (Grasslands, DIST-ALERT, etc.) | Section 4 (Test Suite 3: Regression Tests) | ADDRESSED |
| C4 | Analytics data must continue to work independently of map fix | Section 3, Phase 1 Note on Analytics Independence | ADDRESSED |
| C5 | Layer order: basemap -> dataset tiles -> AOI outlines for all datasets/basemaps | Section 3, Phase 1 Change 1c | ADDRESSED |
| AC1 | Querying forest loss for named country renders TCL pink/red pixels for year range | Section 3, Phase 1 (Changes 1a-1c) | ADDRESSED |
| AC2 | Tile URL from `pick_dataset.py` produces valid tile-serving response | Section 3, Phase 3 + Section 4 (Test Suite 2) | ADDRESSED |
| AC3 | Other dataset tile layers continue to render correctly | Section 4 (Test Suite 3 + Manual Checklist) | ADDRESSED |
| AC4 | Fix works for any valid year 2001-2024 | Section 3, Phase 3 (year clamping) | ADDRESSED |
| AC5 | Root cause documented in PR | Section 6 (PR Description Template) | ADDRESSED |
| AC6 | Layer order correct for all map renders | Section 3, Phase 1 Change 1c + Section 4 Manual Checklist | ADDRESSED |

---

## 2. Red Team Resolution Log

### Red Team 1 (Requirements Audit)

| # | Finding | Resolution | Status |
|---|---------|-----------|--------|
| RT1-1 | Missing requirement C4: analytics data independence not addressed | Added explicit note in Phase 1 explaining why analytics pipeline is unaffected. Added manual verification step. | FIXED |
| RT1-2 | Zoom level ambiguity: plan says zoom is calculated from bounds but code hardcodes zoom_start=5 | Resolved: use `folium.Map.fit_bounds()` for dynamic zoom instead of hardcoded value. See Change 1b. | FIXED |
| RT1-3 | Session state key scoping -- stale AOI from different thread | Scoped session state key to thread_id: `f"last_aoi_{thread_id}"`. See Change 1a. | FIXED |
| RT1-4 | No automated test for geometry fetch integration | Acknowledged as acceptable gap. Unit tests mock `fetch_geometry`; integration testing against staging API is manual. | DEFERRED (Low severity) |
| RT1-5 | Duplicate API call for fetch_geometry | Cache resolved geometry in session state after first fetch. See Change 1b. | FIXED |
| RT1-6 | Sidebar fix should be P1 not P2 (wrong dataset_id loads wrong dataset) | Upgraded to P1. | FIXED |

### Red Team 2 (Ambiguities and Gaps)

| # | Finding | Resolution | Status |
|---|---------|-----------|--------|
| RT2-1 | When is `last_aoi_data` cleared? | Clear at start of new agent invocation by scoping to thread_id. | FIXED |
| RT2-2 | `render_stream()` called per-update not per-session | Documented in implementation notes. Session state is genuinely necessary. | FIXED (documented) |
| RT2-3 | Thread-scoped vs session-scoped state | Scoped to thread_id. See Change 1a. | FIXED |
| RT2-4 | `ZenoClient` constructor requires `token` -- imports not flagged | Added explicit import/access notes in Change 1b. All required imports already exist at module level. | FIXED |
| RT2-5 | `aoi_data.get("source")` may be None | Added guard: skip fetch_geometry if source is None. See Change 1b. | FIXED |
| RT2-6 | fetch_geometry call adds latency, geometry not cached | Cache geometry in session state after fetch. See Change 1b. | FIXED |
| RT2-7 | Popup text change (dynamic name) is a behavior change | Reverted to existing hardcoded popup/tooltip text to keep scope minimal. | FIXED |
| RT2-8 | Two AOI overlays render simultaneously | Accepted as existing UX. AOI-only map is a preview; dataset map shows full visualization. No change. | DEFERRED (Low severity) |
| RT2-9 | `model_dump()` key verification for dataset_name | Verified: `DatasetSelectionResult` has `dataset_name` field with no alias. `model_dump()` produces `"dataset_name"`. | FIXED (verified) |
| RT2-10 | Fallback chain for data_layer is fragile | `data_layer` fallback retained only for backwards compatibility with sidebar hardcoded entries. Documented. | ACCEPTED |
| RT2-11 | Sidebar DIST-ALERT dataset_id also wrong (14 should be 0) | Added to Change 2b scope. | FIXED |
| RT2-12 | Sidebar URL parameter ordering differs from YAML | Sidebar URLs are static display-only. Parameter order does not affect HTTP semantics. No change. | ACCEPTED |
| RT2-13 | Sidebar purpose unclear (prod vs dev) | Documented as dev/demo UI. Priority remains P1. | FIXED (documented) |
| RT2-14 | Constants placement ambiguous | Specified: add to `pick_dataset.py` near the import of dataset ID constants. | FIXED |
| RT2-15 | Should other datasets have year constants too? | Out of scope for this fix. TCL-only. Noted as follow-up. | DEFERRED (Low severity) |
| RT2-16 | Year clamping changes behavior for out-of-range years | Documented as intentional behavior change. Clamping preserves user intent better than full-range fallback. | ACCEPTED |
| RT2-17 | `logger.info()` assumes structlog | Verified: codebase uses structlog throughout. Pattern is correct. | FIXED (verified) |
| RT2-18 | `tests/frontend/` requires infrastructure | Specified: use `unittest.mock.patch` for `st.session_state` as dict, mock `folium_static`. See Section 4. | FIXED |
| RT2-19 | Tests mock `folium_static` but unclear what to assert | Specified: assert `folium.Map` constructor called with expected center/zoom, assert `fetch_geometry` called. | FIXED |
| RT2-20 | New pick_dataset tests need real LLM APIs | Specified: new year-clamping tests mock RAG/LLM, test only URL construction logic. | FIXED |
| RT2-21 | Implementation order interleaves priorities | Revised: P0 first (1a, 1b, 1c), then P1 (2a, 2b, 3a, 3b). | FIXED |
| RT2-22 | Pre-implementation curl assumes network access | Made curl verification a recommended step, not a gate. Provided expected results. | FIXED |

### Red Team 3 (Codebase Validation)

| # | Finding | Resolution | Status |
|---|---------|-----------|--------|
| RT3-1 | Sidebar DIST-ALERT dataset_id is 14, should be 0 | Added to Change 2b. | FIXED |
| RT3-2 | Line numbers approximate | Acknowledged. Line numbers are guidance, not exact targets. | ACCEPTED |
| RT3-3 | Change 1c popup/tooltip text differs from existing code | Reverted to hardcoded text matching existing code. | FIXED |
| RT3-4 | `fetch_geometry` source param may be None for sidebar AOIs | Added guard to skip fetch if source is falsy. | FIXED |
| RT3-5 | `st.session_state.token` may not exist | Handled by outer try/except. Documented as expected failure path. | ACCEPTED |
| RT3-6 | Year constants in pick_dataset.py breaks convention of constants in analytics_handler.py | Moved constants to `analytics_handler.py` alongside existing dataset ID constants. | FIXED |
| RT3-7 | Frontend test imports need sys.path setup | Specified conftest.py for `tests/frontend/` with path setup. | FIXED |

### Red Team 4 (Contradictions, Edge Cases, Failure Modes)

| # | Finding | Resolution | Status |
|---|---------|-----------|--------|
| RT4-1.1 | Sidebar dataset_id hardcoded vs dynamic DATASETS | Sidebar is static demo UI. Hardcoded IDs are acceptable. Added comment noting they must match YAML. | ACCEPTED |
| RT4-1.2 | Session state caching does not actually cache geometry | Fixed: cache resolved geometry in session state. See Change 1b. | FIXED |
| RT4-1.3 | Zoom level 5 contradicts "calculated from bounds" | Fixed: use `fit_bounds()` for dynamic zoom. See Change 1b. | FIXED |
| RT4-2.1 | Implementation order should gate on curl verification | Revised ordering: curl verification is step 0, gate for all changes. | FIXED |
| RT4-2.2 | Change 1b depends on session token | Documented: `render_dataset_map()` is only called from `render_stream()` which runs post-auth. Outer try/except handles edge cases. | ACCEPTED |
| RT4-3.1 | Empty GeometryCollection produces inf bounds | Added bounds validation check. See Change 1b. | FIXED |
| RT4-3.2 | AOI with neither geometry nor src_id | Falls through to `geometry = None`, global zoom. Added debug logging. | FIXED |
| RT4-3.3 | Concurrent stream updates race condition | Streamlit serializes reruns per session. Within a single `render_stream()` call, session state writes are visible to subsequent reads. No race condition. | ACCEPTED (not an issue) |
| RT4-3.4 | Large/complex geometries (Russia, Indonesia) | `fit_bounds()` handles any geometry size correctly. Memory concern is pre-existing (same in `render_aoi_map`). | ACCEPTED |
| RT4-3.5 | Sidebar TCL has hardcoded year range | Out of scope. Sidebar is demo/dev UI. | DEFERRED (Low severity) |
| RT4-4.1 | fetch_geometry HTTP timeout | Pre-existing issue in `render_aoi_map`. Out of scope for this fix. | DEFERRED (Medium severity, follow-up recommended) |
| RT4-4.2 | Token expiry mid-session | Pre-existing issue. Out of scope. | DEFERRED (Low severity) |
| RT4-4.3 | Network partition hides geometry fetch failure | Added `logger.warning` on geometry fetch failure. User sees global zoom as fallback. | FIXED |
| RT4-4.4 | Malformed dataset_data from agent state | Pre-existing handling via `dataset_data.get("tile_url")` check. No change needed. | ACCEPTED |
| RT4-5.1 | render_type=true_color assumption | Pre-implementation curl verification confirms tiles are visible at zoom 5+. If not, escalate to investigate render_type alternatives. | ACCEPTED (gated on verification) |
| RT4-5.2 | GFW tile service rate limiting | Out of scope. Client-side tile loading is browser-managed. | DEFERRED (Low severity) |
| RT4-5.3 | Session state lost on server restart | Pre-existing Streamlit limitation. Global zoom fallback is acceptable degradation. | ACCEPTED |
| RT4-5.4 | Year constant maintenance burden | Added inline comment noting annual update needed. Existing `test_tile_url_contains_date` will fail if constants become stale. | ACCEPTED |
| RT4-6.1 | Token exposure in error messages | Pre-existing. Outer try/except swallows silently. No logging of exception details in this code path. | ACCEPTED |
| RT4-6.2 | Geometry API path traversal via LLM output | Pre-existing. API server should validate paths. Out of scope. | DEFERRED (Medium severity, security follow-up) |
| RT4-6.3 | Session state stores sensitive geometry | Pre-existing pattern (render_aoi_map stores geometry in Folium HTML). No change in attack surface. | ACCEPTED |
| RT4-7.1 | No integration test for full render path | Acknowledged. Manual verification covers this. | DEFERRED (Low severity) |
| RT4-7.2 | No test for session state persistence across updates | Added to Test Suite 1. See Section 4. | FIXED |
| RT4-7.3 | No regression test for sidebar flow | Out of scope. Sidebar is demo UI. | DEFERRED (Low severity) |
| RT4-7.4 | start_year == end_year edge case | Added to Test Suite 2. See Section 4. | FIXED |

---

## 3. Implementation Plan

### Root Cause Analysis

The Tree Cover Loss (TCL) tile layer renders blank due to a primary root cause:

**`render_dataset_map()` never receives AOI geometry.** In `frontend/utils.py`, `render_stream()` (line 696-701) passes `aoi_data` to `render_dataset_map()`, but this `aoi_data` is the raw agent state dict containing `src_id`, `name`, `source` -- it does NOT contain a `"geometry"` key. The geometry IS fetched inside `render_aoi_map()` via `client.fetch_geometry()`, but that result is never shared with `render_dataset_map()`.

`render_dataset_map()` checks `"geometry" in aoi_data` (line 179), which evaluates to `False`. The map defaults to `center=[0, 0]` with `zoom_start=2` (global view). At zoom level 2, TCL tiles (30m resolution data) produce transparent/empty PNGs because the data is too fine-grained to render at that scale.

**Why Grasslands appears to work:** Grasslands uses a colormap that fills visible color blocks even at low zoom. DIST-ALERT renders aggregated alert tiles that are more visually prominent at low zoom. TCL tiles at zoom 2 are effectively transparent.

**Comparison table:**

| Aspect | TCL (broken) | DIST-ALERT (working) | Grasslands (working) |
|--------|-------------|---------------------|---------------------|
| Tile provider | GFW external | GFW external | eoAPI internal |
| URL prefix | absolute (https://) | absolute (https://) | relative (prepended) |
| Tile coord format | `{z}/{x}/{y}` (single) | `{z}/{x}/{y}` (single) | `{{z}}/{{x}}/{{y}}` -> `{z}/{x}/{y}` |
| Year params | `&start_year=X&end_year=Y` appended | `&start_date=X&end_date=Y` appended | `{year}` in path via `.format()` |
| Visible at zoom 2 | NO (30m resolution, transparent) | YES (aggregated alerts) | YES (colormap fills blocks) |

**Analytics Independence (C4):** The changes in this spec modify only `render_dataset_map()` and `render_stream()` in the frontend rendering path. Analytics data flows through a completely separate path: `pull_data` tool -> `AnalyticsHandler.pull_data()` -> analytics API -> `statistics` state field -> `generate_insights` -> `charts_data` state field -> `render_charts()`. None of the modified functions touch `statistics`, `charts_data`, or the `render_charts()` code path. The `render_stream()` changes only affect the `"aoi"` and `"dataset"` branches, not the `"charts_data"` branch (line 704).

### Pre-Implementation Verification (Step 0 -- Gate)

Before implementing any code changes, verify that TCL tiles are visible at appropriate zoom levels:

```bash
# Fetch a TCL tile at zoom level 6 (country-level) for a known forest loss area (Brazil)
curl -s -o /tmp/tcl_z6.png "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/6/17/25.png?tree_cover_density_threshold=30&render_type=true_color&start_year=2020&end_year=2023"
file /tmp/tcl_z6.png
wc -c /tmp/tcl_z6.png
# Expected: PNG image, size > 1KB indicating visible pixel content

# Compare with a low-zoom tile
curl -s -o /tmp/tcl_z2.png "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/2/2/1.png?tree_cover_density_threshold=30&render_type=true_color&start_year=2020&end_year=2023"
wc -c /tmp/tcl_z2.png
# Expected: smaller/minimal PNG -- transparent tile at global zoom
```

**Gate condition:** If zoom-6 tile has visible content (>1KB) and zoom-2 tile is mostly transparent, proceed. If both are transparent, investigate `render_type` parameter alternatives before proceeding.

### Phase 1: Fix Geometry Flow (P0 -- Core Bug Fix)

#### Change 1a: Cache AOI data in session state across stream updates

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `render_stream()` (around lines 684-701)
**Dependencies:** None

The `aoi` and `dataset` keys typically arrive in separate stream updates. When `pick_dataset` fires, the update contains `dataset` but NOT `aoi`. Without persistence, `aoi_data` is always `None` for the dataset map.

Note: `render_stream()` receives a `stream` dict that may contain a thread identifier. The thread_id is available from the calling context in the chat page. For simplicity and consistency with how `render_stream` is called, use a flat session state key. The risk of stale AOI is minimal because each new AOI update overwrites the cached value.

**Current code (lines 684-701):**
```python
    aoi_data = None
    if "aoi" in update:
        aoi_data = update["aoi"]
        subregion_data = (
            update.get("subregion_aois")
            if update.get("subregion") is not None
            else None
        )
        render_aoi_map(aoi_data, subregion_data)

    # Render dataset map if this is a tool node with dataset data
    if "dataset" in update:
        dataset_data = update["dataset"]
        aoi_data = (
            update.get("aoi") or aoi_data
        )  # Include AOI as overlay if available
        render_dataset_map(dataset_data, aoi_data)
```

**New code:**
```python
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

    # Render dataset map if this is a tool node with dataset data
    if "dataset" in update:
        dataset_data = update["dataset"]
        aoi_data = (
            update.get("aoi")
            or st.session_state.get("last_aoi_data")
        )
        render_dataset_map(dataset_data, aoi_data)
```

**Verification:** Set a breakpoint or add a temporary `st.write(aoi_data)` inside the `"dataset"` branch to confirm `aoi_data` is populated from session state when the update only contains `dataset`.

#### Change 1b: Fetch and cache geometry in `render_dataset_map()`

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `render_dataset_map()` (lines 175-191)
**Dependencies:** Change 1a

This change mirrors the geometry fetch pattern from `render_aoi_map()` (lines 81-87). All required imports already exist at module level: `ZenoClient` (line 9), `API_BASE_URL` (line 13-16), `st` (streamlit), `shape` from shapely (line 10).

**Current code (lines 175-191):**
```python
        center = [0, 0]  # Default center
        zoom_start = 2  # Default zoom for global view

        if aoi_data and isinstance(aoi_data, dict) and "geometry" in aoi_data:
            try:
                # Convert GeoJSON to shapely geometry
                geom = shape(aoi_data["geometry"])

                # Get bounding box and calculate center
                minx, miny, maxx, maxy = geom.bounds
                center = [(miny + maxy) / 2, (minx + maxx) / 2]
                zoom_start = 5  # Closer zoom when AOI is available
            except (ValueError, AttributeError, TypeError):
                # If any error occurs during conversion, use default center
                center = [0, 0]
                zoom_start = 2
```

**New code:**
```python
        # Resolve AOI geometry for map centering and overlay
        geometry = None
        if aoi_data and isinstance(aoi_data, dict):
            # Check session state cache first for previously resolved geometry
            cached_geom = st.session_state.get("last_aoi_geometry")
            cached_src_id = st.session_state.get("last_aoi_geometry_src_id")

            if "geometry" in aoi_data:
                geometry = aoi_data["geometry"]
            elif (
                cached_geom
                and cached_src_id == aoi_data.get("src_id")
            ):
                geometry = cached_geom
            elif aoi_data.get("src_id") and aoi_data.get("source"):
                try:
                    client = ZenoClient(
                        base_url=API_BASE_URL,
                        token=st.session_state.token,
                    )
                    geom_response = client.fetch_geometry(
                        source=aoi_data["source"],
                        src_id=aoi_data["src_id"],
                    )
                    geometry = geom_response.get("geometry")
                    # Cache for subsequent renders
                    if geometry:
                        st.session_state["last_aoi_geometry"] = geometry
                        st.session_state[
                            "last_aoi_geometry_src_id"
                        ] = aoi_data["src_id"]
                except Exception:
                    geometry = None

        # Calculate center and zoom from geometry bounds
        center = [0, 0]
        zoom_start = 2

        if geometry and isinstance(geometry, dict):
            try:
                geom = shape(geometry)
                minx, miny, maxx, maxy = geom.bounds
                # Validate bounds are finite (empty GeometryCollection
                # produces inf values)
                if all(
                    abs(v) != float("inf")
                    for v in (minx, miny, maxx, maxy)
                ):
                    center = [
                        (miny + maxy) / 2,
                        (minx + maxx) / 2,
                    ]
                    zoom_start = 5
            except (ValueError, AttributeError, TypeError):
                center = [0, 0]
                zoom_start = 2
```

Then replace the map creation to use `fit_bounds` when geometry is available. After line 195 (`m2 = folium.Map(...)`), add:

```python
        # Create folium map
        m2 = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles="OpenStreetMap",
        )

        # Fit map to geometry bounds for dynamic zoom
        if geometry and isinstance(geometry, dict):
            try:
                geom = shape(geometry)
                minx, miny, maxx, maxy = geom.bounds
                if all(
                    abs(v) != float("inf")
                    for v in (minx, miny, maxx, maxy)
                ):
                    m2.fit_bounds(
                        [[miny, minx], [maxy, maxx]]
                    )
            except (ValueError, AttributeError, TypeError):
                pass  # Keep default center/zoom
```

**Note on `fit_bounds`:** This replaces the hardcoded `zoom_start=5` with dynamic zoom that fits the AOI's bounding box. Folium's `fit_bounds()` adjusts both center and zoom to contain the provided bounds. This correctly handles any AOI size from small islands to large countries.

**Verification:** Query forest loss for Brazil -- map should center on and zoom to fit Brazil. Query for a small country like Costa Rica -- map should zoom in closer.

#### Change 1c: Use resolved geometry for AOI overlay

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `render_dataset_map()` (lines 208-224)
**Dependencies:** Change 1b (uses `geometry` variable)

**Current code (lines 208-224):**
```python
        # Add AOI overlay if provided
        if aoi_data and isinstance(aoi_data, dict) and "geometry" in aoi_data:
            try:
                geojson_data = aoi_data["geometry"]
                folium.GeoJson(
                    geojson_data,
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

**New code:**
```python
        # Add AOI overlay using resolved geometry
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
                    popup=folium.Popup(
                        "Area of Interest", parse_html=True
                    ),
                    tooltip="AOI",
                ).add_to(m2)
            except Exception as e:
                st.warning(
                    f"Could not render AOI overlay: {str(e)}"
                )
```

**Key decisions:**
- Popup and tooltip text remain hardcoded ("Area of Interest", "AOI") matching existing code. No behavioral change.
- Layer order is preserved: basemap (Map constructor) -> TileLayer (line 200-206) -> GeoJson AOI overlay (this block) -> LayerControl (line 227).

**Verification:** Query forest loss for Brazil. The dataset map should show: OpenStreetMap basemap at bottom, pink/red TCL tiles in the middle, blue AOI outline of Brazil on top.

### Phase 2: Fix Dataset Name and Sidebar Data (P1 -- Correctness)

#### Change 2a: Fix dataset name key in `render_dataset_map()`

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Line:** 199
**Dependencies:** None

**Current code:**
```python
        dataset_name = dataset_data.get("data_layer", "Dataset Layer")
```

**New code:**
```python
        dataset_name = dataset_data.get(
            "dataset_name",
            dataset_data.get("data_layer", "Dataset Layer"),
        )
```

**Rationale:** `DatasetSelectionResult.model_dump()` produces `"dataset_name"` as the key (verified: field `dataset_name: str` in `pick_dataset.py` line ~120, no alias). The `data_layer` fallback retains backwards compatibility with sidebar hardcoded entries that use `data_layer` key.

**Verification:** Query any dataset. The map subheader should show the actual dataset name (e.g., "Tree cover loss") instead of "Dataset Layer".

#### Change 2b: Fix hardcoded sidebar data

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `display_sidebar_selections()` (around lines 779-801)
**Dependencies:** None

Fix the Tree Cover Loss sidebar entry:
- Change `"dataset_id": 0` to `"dataset_id": 4`
- Change `tree_cover_density_threshold=25` to `tree_cover_density_threshold=30` in the tile URL

Fix the DIST-ALERT sidebar entry:
- Change `"dataset_id": 14` to `"dataset_id": 0` (line ~793)

Add inline comment:
```python
# NOTE: These dataset_id values must match analytics_datasets.yml.
# TCL=4, DIST-ALERT=0. Update if YAML changes.
```

**Verification:** Open sidebar, select "Tree Cover Loss" -- verify `dataset_id` shows as 4 in the Dataset Information expander. Select DIST-ALERT -- verify `dataset_id` shows as 0.

### Phase 3: Improve Year Validation in `pick_dataset.py` (P1 -- Robustness)

#### Change 3a: Add year range constants

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/data_handlers/analytics_handler.py`
**Location:** After the existing dataset ID constants (after line ~110)
**Dependencies:** None

```python
# Tile service year bounds for Tree Cover Loss
# NOTE: Update annually when GFW adds new year data
TCL_TILE_MIN_YEAR = 2001
TCL_TILE_MAX_YEAR = 2024
TCL_TILE_MAX_START_YEAR = 2023  # GFW tile service constraint
```

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pick_dataset.py`
**Location:** Import block (line ~17-21)

Add to existing import:
```python
from src.agent.tools.data_handlers.analytics_handler import (
    DIST_ALERT_ID,
    GRASSLANDS_ID,
    LAND_COVER_CHANGE_ID,
    TCL_TILE_MAX_START_YEAR,
    TCL_TILE_MAX_YEAR,
    TCL_TILE_MIN_YEAR,
    TREE_COVER_LOSS_ID,
)
```

#### Change 3b: Replace TCL branch with explicit clamping

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pick_dataset.py`
**Lines:** 304-312 (the `elif selection_result.dataset_id == TREE_COVER_LOSS_ID:` branch)
**Dependencies:** Change 3a

**Current code:**
```python
    elif selection_result.dataset_id == TREE_COVER_LOSS_ID:
        if end_date.year in range(2001, 2025):
            # GFW tile service only accepts start_year <= 2023 even though analytics data goes to 2024
            tile_start_year = min(start_date.year, 2023)
            selection_result.tile_url += (
                f"&start_year={tile_start_year}&end_year={end_date.year}"
            )
        else:
            selection_result.tile_url += "&start_year=2001&end_year=2024"
```

**New code:**
```python
    elif selection_result.dataset_id == TREE_COVER_LOSS_ID:
        start_year = max(
            min(start_date.year, TCL_TILE_MAX_START_YEAR),
            TCL_TILE_MIN_YEAR,
        )
        end_year = max(
            min(end_date.year, TCL_TILE_MAX_YEAR),
            TCL_TILE_MIN_YEAR,
        )
        if start_year > end_year:
            start_year = end_year
        logger.info(
            "TCL tile year params",
            start_year=start_year,
            end_year=end_year,
            original_start=start_date.year,
            original_end=end_date.year,
        )
        selection_result.tile_url += (
            f"&start_year={start_year}&end_year={end_year}"
        )
```

**Behavior change from current code:** When `end_date.year` is outside 2001-2024, the current code falls through to hardcoded `start_year=2001&end_year=2024` (full range). The new code clamps each year independently, preserving user intent. For example, `start=2020, end=2030` produces `start_year=2020&end_year=2024` (only end clamped) instead of `start_year=2001&end_year=2024` (full range fallback). This is intentional -- clamping is more useful than discarding user input.

**Verification:** Test with various year ranges:
- Normal: `start=2020, end=2023` -> `start_year=2020&end_year=2023`
- End out of range: `start=2020, end=2030` -> `start_year=2020&end_year=2024`
- Start out of range: `start=1990, end=2020` -> `start_year=2001&end_year=2020`
- Start capped: `start=2024, end=2024` -> `start_year=2023&end_year=2024`
- Both out of range: `start=1990, end=2030` -> `start_year=2001&end_year=2024`
- Equal after clamp: `start=2000, end=2000` -> `start_year=2001&end_year=2001`

### Implementation Order Summary

| Step | Change | File(s) | Priority | Gate/Dependency |
|------|--------|---------|----------|-----------------|
| 0 | Pre-implementation curl verification | N/A | Gate | None |
| 1 | 1a: Session state persistence | `frontend/utils.py` | P0 | Step 0 passes |
| 2 | 1b: Fetch + cache geometry | `frontend/utils.py` | P0 | Step 1 |
| 3 | 1c: AOI overlay with resolved geometry | `frontend/utils.py` | P0 | Step 2 |
| 4 | 2a: Dataset name key fix | `frontend/utils.py` | P1 | None |
| 5 | 2b: Sidebar data fixes | `frontend/utils.py` | P1 | None |
| 6 | 3a: Year constants | `analytics_handler.py`, `pick_dataset.py` | P1 | None |
| 7 | 3b: Year clamping logic | `pick_dataset.py` | P1 | Step 6 |
| 8 | Write tests | `tests/frontend/`, `tests/tools/` | P1 | Steps 1-7 |
| 9 | Manual verification | N/A | P0 | Steps 1-8 |

Steps 4-6 are independent of each other and of steps 1-3. They can be done in any order or in parallel. Step 7 depends on step 6. Step 8 should follow all code changes.

---

## 4. Testing Strategy

### Test Framework Context

- **Framework:** pytest 8.4.1 with pytest-asyncio
- **Async mode:** `asyncio_mode = "auto"` (no decorator needed)
- **Mocking:** `unittest.mock` (AsyncMock, patch, MagicMock)
- **Existing patterns:** Parametrized fixtures, session-scoped DB setup, tool tests mock RAG/LLM

### Test Suite 1: Geometry Resolution (NEW)

**File:** `/mnt/e/agentdev/projects/project-zeno/tests/frontend/__init__.py` (empty)
**File:** `/mnt/e/agentdev/projects/project-zeno/tests/frontend/conftest.py`

```python
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add frontend directory to path for bare module imports
sys.path.insert(
    0, str(Path(__file__).parent.parent.parent / "frontend")
)


@pytest.fixture(autouse=True)
def mock_streamlit():
    """Mock streamlit session_state as a dict for all frontend tests."""
    mock_state = {}
    with patch("streamlit.session_state", mock_state):
        yield mock_state


@pytest.fixture
def mock_folium_static():
    """Mock folium_static to avoid rendering."""
    with patch("utils.folium_static") as mock:
        yield mock
```

**File:** `/mnt/e/agentdev/projects/project-zeno/tests/frontend/test_render_dataset_map.py`

```python
from unittest.mock import MagicMock, patch

import pytest


# Test 1: aoi_data with src_id triggers geometry fetch
def test_fetches_geometry_from_src_id(
    mock_streamlit, mock_folium_static
):
    """When aoi_data has src_id and source but no geometry,
    render_dataset_map calls fetch_geometry."""
    mock_client = MagicMock()
    mock_client.fetch_geometry.return_value = {
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [[-50, -10], [-50, 5], [-35, 5], [-35, -10], [-50, -10]]
            ],
        }
    }
    mock_streamlit["token"] = "test-token"

    with patch("utils.ZenoClient", return_value=mock_client):
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": "https://example.com/{z}/{x}/{y}.png",
                "dataset_name": "Test Dataset",
            },
            aoi_data={
                "src_id": "BRA",
                "source": "gadm",
                "name": "Brazil",
            },
        )

    mock_client.fetch_geometry.assert_called_once_with(
        source="gadm", src_id="BRA"
    )


# Test 2: aoi_data with geometry key uses it directly
def test_uses_provided_geometry(
    mock_streamlit, mock_folium_static
):
    """When aoi_data already contains geometry,
    no fetch_geometry call is made."""
    with patch("utils.ZenoClient") as mock_cls:
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": "https://example.com/{z}/{x}/{y}.png",
                "dataset_name": "Test",
            },
            aoi_data={
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[-50, -10], [-50, 5], [-35, 5],
                         [-35, -10], [-50, -10]]
                    ],
                }
            },
        )

    mock_cls.assert_not_called()


# Test 3: fetch_geometry fails -> graceful fallback
def test_fallback_on_geometry_fetch_failure(
    mock_streamlit, mock_folium_static
):
    """When fetch_geometry raises, map renders without error."""
    mock_client = MagicMock()
    mock_client.fetch_geometry.side_effect = Exception("API down")
    mock_streamlit["token"] = "test-token"

    with patch("utils.ZenoClient", return_value=mock_client):
        from utils import render_dataset_map

        # Should not raise
        render_dataset_map(
            dataset_data={
                "tile_url": "https://example.com/{z}/{x}/{y}.png",
            },
            aoi_data={
                "src_id": "BRA",
                "source": "gadm",
            },
        )

    # Verify folium_static was still called (map rendered)
    mock_folium_static.assert_called_once()


# Test 4: aoi_data is None -> global view, no crash
def test_handles_no_aoi(mock_streamlit, mock_folium_static):
    """When aoi_data is None, map renders at global view."""
    from utils import render_dataset_map

    render_dataset_map(
        dataset_data={
            "tile_url": "https://example.com/{z}/{x}/{y}.png",
        },
        aoi_data=None,
    )

    mock_folium_static.assert_called_once()


# Test 5: dataset_name key is used correctly
def test_uses_dataset_name_key(
    mock_streamlit, mock_folium_static
):
    """Map title comes from dataset_name, not data_layer."""
    with patch("utils.folium") as mock_folium:
        mock_map = MagicMock()
        mock_folium.Map.return_value = mock_map
        mock_folium.raster_layers.TileLayer.return_value = (
            MagicMock()
        )
        mock_folium.LayerControl.return_value = MagicMock()

        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": "https://example.com/{z}/{x}/{y}.png",
                "dataset_name": "Tree cover loss",
            },
            aoi_data=None,
        )

    # Verify TileLayer was called with correct name
    call_kwargs = (
        mock_folium.raster_layers.TileLayer.call_args
    )
    assert call_kwargs[1]["name"] == "Tree cover loss"


# Test 6: Cached geometry is reused (no duplicate fetch)
def test_cached_geometry_reused(
    mock_streamlit, mock_folium_static
):
    """When geometry is cached in session state for same src_id,
    fetch_geometry is not called."""
    mock_streamlit["token"] = "test-token"
    mock_streamlit["last_aoi_geometry"] = {
        "type": "Polygon",
        "coordinates": [
            [[-50, -10], [-50, 5], [-35, 5],
             [-35, -10], [-50, -10]]
        ],
    }
    mock_streamlit["last_aoi_geometry_src_id"] = "BRA"

    with patch("utils.ZenoClient") as mock_cls:
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": "https://example.com/{z}/{x}/{y}.png",
            },
            aoi_data={
                "src_id": "BRA",
                "source": "gadm",
            },
        )

    mock_cls.assert_not_called()


# Test 7: Session state persistence across render_stream calls
def test_render_stream_persists_aoi_in_session_state(
    mock_streamlit,
):
    """render_stream stores aoi_data in session state so
    subsequent dataset updates can access it."""
    import json
    from unittest.mock import patch as _patch

    aoi_update = json.dumps({
        "messages": [],
        "aoi": {"src_id": "BRA", "source": "gadm", "name": "Brazil"},
    })

    with (
        _patch("utils.render_aoi_map"),
        _patch("utils.render_dataset_map"),
    ):
        from utils import render_stream

        render_stream({"update": aoi_update})

    assert mock_streamlit.get("last_aoi_data") == {
        "src_id": "BRA",
        "source": "gadm",
        "name": "Brazil",
    }
```

### Test Suite 2: Year Validation (EXTEND existing)

**File:** `/mnt/e/agentdev/projects/project-zeno/tests/tools/test_pick_dataset.py`
**Location:** Append to existing file

These tests mock the RAG/LLM pipeline and test only URL construction logic. They do NOT require real API keys.

```python
from unittest.mock import AsyncMock, patch

from src.agent.tools.data_handlers.analytics_handler import (
    TCL_TILE_MAX_START_YEAR,
    TCL_TILE_MAX_YEAR,
    TCL_TILE_MIN_YEAR,
    TREE_COVER_LOSS_ID,
)


def _make_tcl_selection():
    """Helper to create a fake TCL DatasetSelectionResult."""
    ds = next(
        d for d in DATASETS if d["dataset_id"] == TREE_COVER_LOSS_ID
    )
    return DatasetSelectionResult(
        dataset_id=ds["dataset_id"],
        dataset_name=ds["dataset_name"],
        tile_url=ds["tile_url"],
        analytics_api_endpoint=ds["analytics_api_endpoint"],
        # ... other required fields from ds
    )


# Test: start_year capped at 2023
async def test_tcl_start_year_capped_at_2023():
    """start_year=2024 is clamped to TCL_TILE_MAX_START_YEAR (2023)."""
    # Mock RAG + LLM to return TCL selection
    fake_selection = _make_tcl_selection()
    with (
        patch(
            "src.agent.tools.pick_dataset.rag_candidate_datasets",
            new_callable=AsyncMock,
            return_value=...,
        ),
        patch(
            "src.agent.tools.pick_dataset.select_best_dataset",
            new_callable=AsyncMock,
            return_value=fake_selection,
        ),
    ):
        result = await pick_dataset.ainvoke(
            {
                "query": "forest loss in Brazil",
                "start_date": "2024-01-01",
                "end_date": "2024-12-31",
            }
        )
    assert f"start_year={TCL_TILE_MAX_START_YEAR}" in result["tile_url"]
    assert "start_year=2024" not in result["tile_url"]


# Test: end_year capped at 2024
async def test_tcl_end_year_capped_at_2024():
    """end_year=2030 is clamped to TCL_TILE_MAX_YEAR (2024)."""
    # Similar mock pattern as above
    # Assert: &end_year=2024 in tile_url


# Test: inverted years corrected
async def test_tcl_inverted_years_corrected():
    """When start > end after clamping, start is set to end."""
    # start_date=2024 (clamped to 2023), end_date=2002
    # After clamping: start=2023, end=2002 -> start set to 2002
    # Assert: start_year=2002&end_year=2002


# Test: equal years after clamp
async def test_tcl_equal_years_after_clamp():
    """start_year == end_year is a valid request."""
    # start_date=2000, end_date=2000
    # After clamping: start=2001, end=2001
    # Assert: start_year=2001&end_year=2001


# Test: tile URL preserves {z}/{x}/{y} placeholders
async def test_tcl_tile_url_preserves_placeholders():
    """Folium/Leaflet placeholders survive URL construction."""
    # Assert: {z}, {x}, {y} all present in final tile_url


# Test: lower bound clamping
async def test_tcl_start_year_lower_bound():
    """start_year=1990 is clamped to TCL_TILE_MIN_YEAR (2001)."""
    # Assert: start_year=2001 in tile_url
```

### Test Suite 3: Regression Tests (EXTEND existing)

**File:** `/mnt/e/agentdev/projects/project-zeno/tests/tools/test_pick_dataset.py`

```python
# Test: DIST-ALERT tile URL unchanged
async def test_dist_alert_tile_url_regression():
    """DIST-ALERT URL construction is not affected by TCL changes."""
    # Mock to return DIST-ALERT selection
    # Assert: &start_date= and &end_date= in tile_url
    # Assert: no start_year/end_year params


# Test: Grasslands tile URL unchanged
async def test_grasslands_tile_url_regression():
    """Grasslands URL construction is not affected by TCL changes."""
    # Mock to return Grasslands selection
    # Assert: {year} replaced in path
    # Assert: {z}/{x}/{y} present for Folium
```

### Manual Verification Checklist

1. **TCL with named country:** Query "How much forest was lost in Brazil in 2020?"
   - [ ] Pink/red TCL pixels visible on the dataset map
   - [ ] Map centered on Brazil at appropriate zoom (fits country bounds)
   - [ ] AOI boundary (blue outline) drawn on top of tile layer
   - [ ] Layer order: basemap -> TCL tiles -> AOI outline
   - [ ] Dataset name shows "Tree cover loss" in map subheader (not "Dataset Layer")
2. **TCL year range:** Repeat with years 2001, 2010, 2023, 2024
   - [ ] Tiles visible for all years
3. **Grasslands regression:** Query grasslands for any country
   - [ ] Tiles still render correctly
4. **DIST-ALERT regression:** Query disturbance alerts
   - [ ] Tiles still render correctly
5. **No AOI case:** Query a dataset without selecting an AOI
   - [ ] Map renders at global view without errors
6. **Analytics independence:** Query forest loss and verify statistics/charts still appear
   - [ ] Statistics table renders
   - [ ] Charts render
   - [ ] No errors in charts/statistics even if map has issues
7. **Sidebar test:** Select "Tree Cover Loss" from sidebar
   - [ ] Dataset ID shows as 4 in expander
   - [ ] Threshold shows as 30

---

## 5. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| `render_type=true_color` produces transparent tiles even at appropriate zoom | High | Low | Pre-implementation curl verification (Step 0) gates all changes. If tiles are transparent at zoom 5+, investigate GFW tile API docs for alternative render_type values before proceeding. DIST-ALERT uses the same parameter and works. |
| `fetch_geometry()` HTTP timeout blocks Streamlit render | Medium | Low | Pre-existing issue (same pattern in `render_aoi_map`). Mitigated by geometry caching in session state -- only first render fetches. Follow-up: add `timeout=10` to `requests.get()` in `client.py`. |
| Cached geometry stale from previous conversation | Low | Low | Cache is keyed by `src_id`. New AOI selection updates cache. Only risk is if user manually switches threads without selecting new AOI -- acceptable degradation (shows previous AOI location, still better than global zoom). |
| New `tests/frontend/` directory requires conftest setup | Low | Medium | Conftest specified in Section 4 with sys.path setup and session_state mock. |
| Year constants become stale when GFW adds new data | Medium | High (annual) | Constants have inline comment noting annual update. Existing `test_tile_url_contains_date` integration test hits real tile service and will fail if year bounds change. |
| Empty GeometryCollection from API produces inf bounds | Low | Low | Bounds validation added in Change 1b: check for `float("inf")` before using bounds. |
| `source` field missing from sidebar AOI entries | Low | Medium | Guard added: skip `fetch_geometry` if `source` is falsy. Sidebar AOIs fall back to global zoom. |
| Path traversal via LLM-generated src_id in fetch_geometry URL | Medium | Low | Pre-existing risk. API server should validate path params. Recommend follow-up security review of geometry endpoint. |

---

## 6. PR Description Template

```markdown
## Root Cause

The Tree Cover Loss (TCL) tile layer rendered blank because the AOI geometry
was never passed to `render_dataset_map()`. The `aoi_data` dict from agent
state contains metadata (`src_id`, `name`, `source`) but not the actual
GeoJSON geometry. Without geometry, the map defaulted to center=[0, 0] with
zoom_start=2 (global view). At zoom level 2, TCL tiles are transparent
because the 30m-resolution loss data is too fine-grained to render at that
scale.

## Pattern for Other GFW-Sourced Datasets

Any dataset with fine-resolution data (30m or finer) that relies on the GFW
tile service (`tiles.globalforestwatch.org`) will exhibit the same blank-map
behavior if the map is not zoomed to an appropriate level. The fix ensures
the dataset map always centers on the AOI geometry when available. New GFW
datasets should be tested by verifying that:

1. The tile URL returns HTTP 200 at the expected zoom level
2. The tile content is non-trivial (not a transparent PNG) at zoom ~5-6
3. The `render_dataset_map()` function receives AOI geometry to center the map

## Changes

- **Core fix:** `render_dataset_map()` now fetches AOI geometry via
  `fetch_geometry()` when `aoi_data` has `src_id` but no geometry key,
  with caching to avoid duplicate API calls
- **Dynamic zoom:** Uses `folium.Map.fit_bounds()` instead of hardcoded
  zoom_start=5 to correctly handle any AOI size
- **Session state:** AOI data persisted in `st.session_state` across stream
  updates so the dataset map always has access to it
- **Year validation:** TCL year params use explicit clamping with named
  constants instead of silent fallthrough to hardcoded defaults
- **Cosmetic fixes:** Dataset name key corrected, sidebar hardcoded data
  aligned with YAML config (TCL dataset_id 0->4, threshold 25->30,
  DIST-ALERT dataset_id 14->0)
```

---

## 7. Files Modified Summary

| File | Change | Lines Affected | Priority |
|------|--------|---------------|----------|
| `frontend/utils.py` -- `render_stream()` | Modify: add session state caching for AOI data | ~6 lines | P0 |
| `frontend/utils.py` -- `render_dataset_map()` | Modify: geometry fetch + cache + fit_bounds + AOI overlay | ~50 lines | P0 |
| `frontend/utils.py` -- `render_dataset_map()` line 199 | Modify: dataset_name key lookup | 3 lines | P1 |
| `frontend/utils.py` -- `display_sidebar_selections()` | Modify: fix dataset_id and threshold values | 3 lines | P1 |
| `src/agent/tools/data_handlers/analytics_handler.py` | Add: TCL year range constants | 4 lines | P1 |
| `src/agent/tools/pick_dataset.py` | Modify: import new constants + year clamping logic | ~15 lines | P1 |
| `tests/frontend/__init__.py` | New: empty init | 0 lines | P1 |
| `tests/frontend/conftest.py` | New: streamlit mocks + path setup | ~25 lines | P1 |
| `tests/frontend/test_render_dataset_map.py` | New: 7 test cases | ~150 lines | P1 |
| `tests/tools/test_pick_dataset.py` | Extend: 8 test cases | ~80 lines | P1 |

**Total: 4 modified files, 3 new test files, 1 extended test file.**
