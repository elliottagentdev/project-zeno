# Draft Plan 3: Robustness-First Implementation Plan

## Lens: Failure Modes, Error Handling, Validation, and Testing Strategy

---

## 1. Failure Mode Analysis

Before proposing any changes, we must catalog every failure mode that could produce "blank map (no pink pixels)" for Tree Cover Loss (TCL). Each failure mode gets explicit detection, handling, and test coverage.

### Failure Mode 1: AOI Geometry Not Passed to Dataset Map (ROOT CAUSE - HIGH CONFIDENCE)

**What goes wrong:** In `render_stream()` (frontend/utils.py, line 696-701), when the `"dataset"` key is in the update, `aoi_data` is set from `update.get("aoi")`. However, the `aoi` dict from agent state contains metadata fields (`src_id`, `name`, `source`) but NOT the `"geometry"` key. The geometry is only fetched inside `render_aoi_map()` via `client.fetch_geometry()` (line 84-87), but this fetched geometry is never passed back to `render_dataset_map()`.

**Impact:** `render_dataset_map()` checks `"geometry" in aoi_data` (line 179) which evaluates to `False`. The map defaults to `center=[0, 0]` with `zoom_start=2` -- a global view at zoom level 2. At this zoom, TCL pixels (30m resolution data) are invisible or not served by the GFW tile service. Grasslands works at zoom 2 because it uses a colormap that renders visible blocks at low zoom. DIST-ALERT may also appear to work because disturbance alerts are aggregated differently.

**Detection:** Log when `aoi_data` is passed to `render_dataset_map` without a geometry key.
**Handling:** Fetch geometry in `render_dataset_map` the same way `render_aoi_map` does.
**Recovery:** Fall back to global view with a warning badge if geometry fetch fails.

### Failure Mode 2: GFW Tile Service Returns Empty/Transparent Tiles at Low Zoom

**What goes wrong:** Even if the URL is valid, the GFW tile service for `umd_tree_cover_loss` may return transparent PNGs at zoom levels below ~4-5 because the 30m resolution data is too fine to render at continental/global scale.

**Impact:** Map shows blank overlay even though the tile URL is technically correct.
**Detection:** Not detectable client-side without inspecting tile response content.
**Handling:** Ensure zoom level is appropriate when AOI is available (zoom 5+ for country-level).
**Mitigation:** This is solved by fixing Failure Mode 1 (proper AOI centering/zoom).

### Failure Mode 3: Tile URL Parameter Validation Gaps

**What goes wrong:** The year range validation in `pick_dataset.py` (line 305) uses `range(2001, 2025)` which excludes 2025. If `end_date.year` is 2025 or beyond, it falls through to the else branch with hardcoded `start_year=2001&end_year=2024`. Future data availability changes could silently break.

**Impact:** Incorrect year params could produce empty tiles or stale data.
**Detection:** Log a warning when falling through to default year range.
**Handling:** Validate and clamp years explicitly with clear bounds constants.

### Failure Mode 4: Dataset Name Mismatch in Frontend

**What goes wrong:** `render_dataset_map()` uses `dataset_data.get("data_layer", "Dataset Layer")` (line 199) but `DatasetSelectionResult` serializes as `dataset_name`, not `data_layer`. The layer always shows "Dataset Layer" as the name.

**Impact:** Cosmetic only -- wrong label in layer control and subheader.
**Detection:** Unit test comparing expected vs actual layer name.
**Handling:** Use `dataset_name` key with fallback to `data_layer` for backwards compatibility.

### Failure Mode 5: Sidebar Hardcoded Data Inconsistency

**What goes wrong:** The sidebar in `frontend/utils.py` (lines 779-801) has hardcoded TCL data with `dataset_id=0` (should be 4) and `tree_cover_density_threshold=25` (should be 30).

**Impact:** Sidebar quick-access renders with wrong parameters.
**Detection:** Test that validates sidebar dataset IDs against `analytics_datasets.yml`.

### Failure Mode 6: Two Separate Map Instances

**What goes wrong:** `render_stream()` creates two independent `folium.Map` objects -- one in `render_aoi_map()` and another in `render_dataset_map()`. These are separate HTML iframes, not layers on the same map.

**Impact:** Violates the acceptance criterion that layer order must be "basemap -> dataset tiles -> AOI outline" on a single map. User sees TWO maps instead of one integrated view.

---

## 2. Architecture: Proposed Changes

### Change Strategy: Fix the geometry flow, then consolidate maps

The primary fix addresses Failure Mode 1 (geometry not passed) and Failure Mode 6 (two separate maps). Secondary fixes address validation gaps and naming issues.

### File Change Map

| File | Change Type | Priority |
|------|------------|----------|
| `frontend/utils.py` - `render_dataset_map()` | Major refactor: fetch geometry when not provided | P0 |
| `frontend/utils.py` - `render_stream()` | Major refactor: pass geometry to dataset map OR consolidate into single map | P0 |
| `src/agent/tools/pick_dataset.py` | Minor: add year validation constants, improve logging | P1 |
| `frontend/utils.py` - sidebar hardcoded data | Minor: fix dataset_id and threshold | P2 |
| `tests/tools/test_pick_dataset.py` | Add: tile URL validation tests | P1 |
| `tests/frontend/test_render_dataset_map.py` (NEW) | Add: frontend rendering tests | P1 |

---

## 3. Detailed Implementation Plan

### Phase 1: Fix Geometry Flow in `render_dataset_map()` (P0)

**File: `frontend/utils.py`, function `render_dataset_map()` (lines 160-265)**

**Change 1a: Fetch geometry when `aoi_data` lacks it**

Modify the AOI handling block (lines 175-191) to fetch geometry from the API when `aoi_data` has `src_id` but no `geometry`:

```python
def render_dataset_map(dataset_data, aoi_data=None):
    try:
        tile_url = dataset_data.get("tile_url")
        if not tile_url:
            st.warning("No tile_url found in dataset")
            return

        # Resolve AOI geometry if aoi_data has src_id but no geometry
        geometry = None
        if aoi_data and isinstance(aoi_data, dict):
            if "geometry" in aoi_data:
                geometry = aoi_data["geometry"]
            elif "src_id" in aoi_data:
                try:
                    client = ZenoClient(
                        base_url=API_BASE_URL,
                        token=st.session_state.token,
                    )
                    geom_response = client.fetch_geometry(
                        source=aoi_data.get("source"),
                        src_id=aoi_data.get("src_id"),
                    )
                    geometry = geom_response.get("geometry")
                except Exception:
                    geometry = None

        # Calculate center from geometry
        center = [0, 0]
        zoom_start = 2
        if geometry and isinstance(geometry, dict):
            try:
                geom = shape(geometry)
                minx, miny, maxx, maxy = geom.bounds
                center = [(miny + maxy) / 2, (minx + maxx) / 2]
                zoom_start = 5
            except (ValueError, AttributeError, TypeError):
                center = [0, 0]
                zoom_start = 2
```

**Error handling rationale:** The `fetch_geometry` call is wrapped in its own try/except that catches any exception and falls back to `geometry = None`. This ensures the map still renders (at global zoom) even if the geometry service is down. The existing fallback to `center=[0, 0], zoom_start=2` is preserved as a last resort.

**Change 1b: Use resolved geometry for AOI overlay**

Replace the AOI overlay block (lines 209-224) to use the already-resolved `geometry` variable:

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
                    popup=folium.Popup(
                        aoi_data.get("name", "Area of Interest"),
                        parse_html=True,
                    ),
                    tooltip=aoi_data.get("name", "AOI"),
                ).add_to(m2)
            except Exception as e:
                st.warning(f"Could not render AOI overlay: {str(e)}")
```

**Change 1c: Fix dataset name key**

Replace line 199:
```python
# Before:
dataset_name = dataset_data.get("data_layer", "Dataset Layer")
# After:
dataset_name = dataset_data.get(
    "dataset_name",
    dataset_data.get("data_layer", "Dataset Layer"),
)
```

This is backwards-compatible: tries `dataset_name` first (from `DatasetSelectionResult.model_dump()`), falls back to `data_layer`, then to "Dataset Layer".

### Phase 2: Eliminate Duplicate Map Rendering (P0)

**File: `frontend/utils.py`, function `render_stream()` (lines 648-720)**

**Problem:** When both `aoi` and `dataset` are in the same state update, TWO maps are rendered: one from `render_aoi_map()` and one from `render_dataset_map()`. This violates the acceptance criterion requiring a single map with layering: basemap -> dataset tiles -> AOI outline.

**Change 2a: Skip standalone AOI map when dataset is also present**

Modify the `render_stream()` function (around lines 686-701):

```python
    aoi_data = None
    if "aoi" in update:
        aoi_data = update["aoi"]
        subregion_data = (
            update.get("subregion_aois")
            if update.get("subregion") is not None
            else None
        )
        # Only render standalone AOI map if no dataset is present
        # in this update. If dataset is present, the AOI will be
        # rendered as an overlay on the dataset map instead.
        if "dataset" not in update:
            render_aoi_map(aoi_data, subregion_data)

    if "dataset" in update:
        dataset_data = update["dataset"]
        aoi_data = (
            update.get("aoi") or aoi_data
        )
        render_dataset_map(dataset_data, aoi_data)
```

**Risk analysis:** In the typical agent flow, `pick_aoi` runs first (producing an `aoi` update), then `pick_dataset` runs separately (producing a `dataset` update). These are usually SEPARATE state updates, so both maps would still render individually. However, the change ensures that IF they arrive in the same update, only one map is shown.

**Important edge case:** When `pick_dataset` fires, the update typically contains `dataset` but may NOT contain `aoi`. The `aoi_data` from the previous `pick_aoi` update is NOT available in the current update context. This means `render_dataset_map` often receives `aoi_data=None`.

**Change 2b: Persist AOI data across stream updates using session state**

To ensure the dataset map always has access to AOI geometry, store it in Streamlit session state:

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
        if "dataset" not in update:
            render_aoi_map(aoi_data, subregion_data)

    if "dataset" in update:
        dataset_data = update["dataset"]
        aoi_data = (
            update.get("aoi")
            or st.session_state.get("last_aoi_data")
        )
        render_dataset_map(dataset_data, aoi_data)
```

**Error handling:** `st.session_state.get("last_aoi_data")` returns `None` if no AOI was ever set. `render_dataset_map` already handles `aoi_data=None` gracefully by defaulting to global view.

**Rollback strategy:** If session state persistence causes issues (e.g., stale AOI from a previous conversation), add a thread-scoped key: `st.session_state[f"aoi_{thread_id}"]`.

### Phase 3: Improve Year Validation in `pick_dataset.py` (P1)

**File: `src/agent/tools/pick_dataset.py` (lines 283-312)**

**Change 3a: Extract year range constants**

Add constants near the top of the file (or in `analytics_handler.py` alongside existing constants):

```python
# Tile service year bounds for Tree Cover Loss
TCL_TILE_MIN_YEAR = 2001
TCL_TILE_MAX_YEAR = 2024
TCL_TILE_MAX_START_YEAR = 2023  # GFW tile service constraint
```

**Change 3b: Improve validation with explicit clamping and logging**

Replace the TCL branch (lines 304-312):

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

**Error handling rationale:**
- `max(min(...))` double-clamp ensures years are always within valid bounds -- no silent fallthrough to hardcoded defaults.
- `start_year > end_year` check prevents inverted ranges that would produce empty tiles.
- Structured logging via `logger.info()` creates an audit trail for debugging tile issues.
- No exception is raised because invalid year ranges are recoverable by clamping.

### Phase 4: Fix Sidebar Hardcoded Data (P2)

**File: `frontend/utils.py` (lines 779-801)**

**Change 4a:** Fix the Tree Cover Loss sidebar entry:

```python
"Tree Cover Loss": {
    "dataset": {
        "dataset_id": 4,  # Was incorrectly 0
        "source": "GFW",
        "dataset_name": "Tree cover loss",
        "tile_url": "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=30&render_type=true_color",
        "context_layer": "Primary forest",
        "threshold": "30",  # Was incorrectly "25"
    }
},
```

---

## 4. Testing Strategy

Testing is organized by failure mode to ensure every identified risk has explicit coverage.

### Test Suite 1: Geometry Resolution in `render_dataset_map` (NEW)

**File: `tests/frontend/test_render_dataset_map.py` (NEW)**

These tests validate that `render_dataset_map` correctly resolves geometry from different `aoi_data` shapes.

```python
# Test 1: aoi_data with geometry key -> uses it directly
async def test_render_dataset_map_with_geometry():
    """Map centers on AOI when geometry is provided directly."""

# Test 2: aoi_data with src_id but no geometry -> fetches it
async def test_render_dataset_map_fetches_geometry():
    """Map fetches and centers on AOI when only src_id is provided."""

# Test 3: aoi_data with src_id, fetch fails -> graceful fallback
async def test_render_dataset_map_geometry_fetch_failure():
    """Map renders at global view when geometry fetch fails."""

# Test 4: aoi_data is None -> global view, no crash
async def test_render_dataset_map_no_aoi():
    """Map renders at global view when no AOI is provided."""

# Test 5: aoi_data with invalid geometry -> graceful fallback
async def test_render_dataset_map_invalid_geometry():
    """Map renders at global view when geometry is malformed."""
```

**Mocking strategy:** Mock `ZenoClient.fetch_geometry` and `st.session_state` to avoid real API calls. Mock `folium_static` to capture the rendered map object for assertion.

### Test Suite 2: Tile URL Construction Validation

**File: `tests/tools/test_pick_dataset.py` (EXTEND)**

```python
# Test 6: TCL year clamping - future year
async def test_tcl_tile_url_future_year_clamped():
    """end_year beyond 2024 is clamped to 2024."""

# Test 7: TCL year clamping - start_year > end_year
async def test_tcl_tile_url_inverted_years():
    """start_year > end_year is corrected."""

# Test 8: TCL year clamping - start_year at boundary
async def test_tcl_tile_url_start_year_capped_at_2023():
    """start_year is capped at 2023 per GFW tile service constraint."""

# Test 9: TCL tile URL format - contains required params
async def test_tcl_tile_url_has_required_params():
    """Generated URL includes start_year, end_year, threshold, render_type."""

# Test 10: TCL tile URL - {z}/{x}/{y} placeholders survive
async def test_tcl_tile_url_preserves_placeholders():
    """URL retains {z}/{x}/{y} for Folium/Leaflet substitution."""
```

### Test Suite 3: Regression Tests for Other Datasets

**File: `tests/tools/test_pick_dataset.py` (EXTEND)**

```python
# Test 11: DIST-ALERT tile URL still works
async def test_dist_alert_tile_url_unchanged():
    """DIST-ALERT URL construction is not regressed."""

# Test 12: Grasslands tile URL still works
async def test_grasslands_tile_url_unchanged():
    """Grasslands URL construction is not regressed."""

# Test 13: Land Cover Change tile URL still works
async def test_land_cover_change_tile_url_unchanged():
    """Land Cover Change URL construction is not regressed."""
```

### Test Suite 4: Integration Smoke Test

**File: `tests/tools/test_pick_dataset.py` (EXTEND the existing `test_tile_url_contains_date`)**

The existing test already fetches real tiles. Ensure it covers TCL specifically:

```python
# Test 14: TCL tile URL returns HTTP 200 from GFW tile service
async def test_tcl_tile_url_returns_200():
    """Real HTTP request to GFW tile service returns 200 for TCL."""
    # Use zoom=6, x=17, y=25 (somewhere with known forest loss)
    tile_url = (
        "https://tiles.globalforestwatch.org/umd_tree_cover_loss/"
        "latest/dynamic/{z}/{x}/{y}.png"
        "?tree_cover_density_threshold=30"
        "&render_type=true_color"
        "&start_year=2020&end_year=2023"
    )
    url = tile_url.format(z=6, x=17, y=25)
    response = requests.get(url)
    assert response.status_code == 200
    assert response.headers.get("content-type", "").startswith("image/")
```

### Test Suite 5: render_stream Integration

**File: `tests/frontend/test_render_stream.py` (NEW)**

```python
# Test 15: dataset update without aoi uses session state aoi
async def test_render_stream_uses_session_aoi():
    """When dataset update has no aoi, session state aoi is used."""

# Test 16: dataset + aoi in same update renders single map
async def test_render_stream_single_map_when_both():
    """When both aoi and dataset in update, only dataset map renders."""
```

---

## 5. Migration Plan

### Rollout Strategy

This fix is purely frontend + agent-side with no database changes. No migration needed.

**Step 1: Deploy backend changes (pick_dataset.py)**
- Year validation improvements are backwards-compatible.
- No API contract changes.
- Existing tile URLs remain valid.

**Step 2: Deploy frontend changes (utils.py)**
- Geometry fetch in `render_dataset_map` is additive.
- Session state persistence is new but has safe defaults.
- Sidebar fixes are cosmetic.

**Step 3: Verify via existing integration test**
- Run `test_tile_url_contains_date` to confirm all tile URLs return HTTP 200.
- Manually test TCL query in Streamlit frontend.

### Rollback Plan

If the fix causes regressions:
1. **Frontend geometry fetch fails consistently:** Revert Change 1a. The fallback to `center=[0, 0]` is the current behavior.
2. **Session state causes stale AOI:** Remove Change 2b. The map will render without AOI overlay, which is the current behavior for dataset maps.
3. **Year clamping produces wrong tiles:** Revert Change 3b to the original if/else logic. The hardcoded defaults are conservative.

---

## 6. Edge Cases and Defensive Measures

### Edge Case 1: Concurrent Streamlit Sessions
Session state is per-session in Streamlit, so `last_aoi_data` is scoped correctly. No cross-session contamination.

### Edge Case 2: AOI Source Service Down
`render_dataset_map` wraps the `fetch_geometry` call in try/except. If the geometry service is down, the map renders at global zoom. A `st.warning` badge could optionally notify the user.

### Edge Case 3: Very Large AOI Geometry
For large countries (Russia, Canada), the fetched geometry could be large. Folium handles GeoJSON natively and Streamlit serializes the full map HTML. No special handling needed, but monitor for performance if users report slow map loads.

### Edge Case 4: Thread Switch Mid-Conversation
When a user switches threads, `st.session_state["last_aoi_data"]` may hold an AOI from a different thread. Mitigation: key the session state by thread ID:
```python
aoi_key = f"last_aoi_{update.get('thread_id', 'default')}"
st.session_state[aoi_key] = aoi_data
```

### Edge Case 5: `render_type=true_color` Semantics
The investigation should verify whether `render_type=true_color` is the correct render type for TCL. The GFW tile service documentation should be checked. If `true_color` means "natural color RGB" rather than "loss-colored overlay", the tiles would be transparent where no loss occurred and near-invisible where loss is present. Alternative values to test: `date_conf`, `encoded`. However, DIST-ALERT uses the same `render_type=true_color` and works, so this is lower probability.

---

## 7. Summary of Root Cause and Fix

**Primary root cause:** AOI geometry is not passed to `render_dataset_map()`. The `aoi_data` dict from agent state contains `src_id`/`name`/`source` but not `geometry`. Without geometry, the map defaults to zoom level 2 at coordinates [0, 0], where TCL pixels are not visible due to the 30m resolution of the underlying data.

**Fix:** Make `render_dataset_map()` resolve geometry from `src_id` (same pattern as `render_aoi_map()`), persist AOI data across stream updates via session state, and ensure proper map centering/zoom when AOI is available.

**Secondary improvements:** Improve year range validation with explicit clamping and logging, fix dataset name key mismatch, fix sidebar hardcoded inconsistencies, and add comprehensive test coverage for all failure modes.
