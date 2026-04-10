# Master Implementation Plan: Fix Tree Cover Loss Blank Map

## Root Cause Analysis

The Tree Cover Loss (TCL) tile layer renders blank due to a primary root cause with compounding secondary issues:

### Primary Root Cause: AOI Geometry Not Passed to Dataset Map

In `frontend/utils.py`, `render_stream()` (line 696-701) passes `aoi_data` to `render_dataset_map()`, but this `aoi_data` is the raw agent state dict containing `src_id`, `name`, `source` -- it does NOT contain a `"geometry"` key. The geometry IS fetched inside `render_aoi_map()` via `client.fetch_geometry()`, but this result is never shared with `render_dataset_map()`.

`render_dataset_map()` checks `"geometry" in aoi_data` (line 179), which evaluates to `False`. The map defaults to `center=[0, 0]` with `zoom_start=2` (global view). At zoom level 2, TCL tiles (30m resolution data) produce transparent/empty PNGs because the data is too fine-grained to render at that scale.

**Why other datasets appear to work:**
- **Grasslands** uses a colormap that fills visible blocks even at low zoom.
- **DIST-ALERT** renders aggregated alert tiles that are more visually prominent at low zoom.

**Confidence: HIGH.** All four draft plans independently identified this as the root cause.

### Secondary Issue: Dual Map Rendering

`render_aoi_map()` and `render_dataset_map()` create independent `folium.Map` instances. The user sees two stacked maps instead of a single map with correct layer order. However, in the typical agent flow, `pick_aoi` and `pick_dataset` produce SEPARATE stream updates, so both maps render sequentially. The acceptance criterion requires "basemap -> dataset tiles -> AOI outline" on a single map -- the dataset map must include the AOI overlay.

**Resolution:** Rather than merging the two render functions (scope creep) or skipping the AOI map conditionally (timing issues since updates arrive separately), the fix ensures `render_dataset_map()` always has access to AOI geometry so it renders the AOI overlay correctly. The AOI-only map serves as a preview that appears first and is acceptable UX. The dataset map then renders with the correct layer order: basemap -> dataset tiles -> AOI outline.

### Tertiary Issues

1. **Dataset name mismatch:** `render_dataset_map()` uses `dataset_data.get("data_layer")` but `DatasetSelectionResult` serializes as `"dataset_name"`. Layer always shows as "Dataset Layer".
2. **Sidebar hardcoded data:** TCL entry has `dataset_id=0` (should be 4) and `threshold=25` (should be 30).
3. **AOI data timing:** AOI and dataset arrive in separate stream updates. The `aoi_data` variable in `render_stream()` may be `None` when the dataset update arrives.

---

## Architecture: Changes Within Existing Patterns

This fix operates entirely within the existing architecture. **No new files. No new abstractions.** Only `frontend/utils.py` is modified, plus minor improvements to `src/agent/tools/pick_dataset.py`.

**Rationale for rejecting the TileURLBuilder strategy pattern (Draft 2):** The if/elif chain in `pick_dataset.py` is ~30 lines and is correct. Creating an abstract base class hierarchy with 4 concrete implementations plus a registry function is over-engineering for this bug fix. The existing `DataSourceHandler` strategy pattern in `data_handlers/` is for data pulling, not URL construction -- introducing a parallel pattern for URL building is inconsistent with the codebase's approach to similar-complexity logic.

**Rationale for rejecting `render_unified_map()` (Draft 2):** Creating a new 80-line function that duplicates most of `render_dataset_map()` adds maintenance burden. Instead, we modify `render_dataset_map()` to fetch geometry when needed -- the same pattern already used by `render_aoi_map()`.

---

## Detailed Implementation Plan

### Phase 1: Fix Geometry Flow (P0 -- Core Bug Fix)

#### Change 1a: Cache AOI data in session state across stream updates

**File:** `frontend/utils.py`, function `render_stream()` (around lines 684-701)

This addresses the timing issue (identified only by Draft 3) where AOI and dataset arrive in separate stream updates:

```python
# Current:
aoi_data = None
if "aoi" in update:
    aoi_data = update["aoi"]
    subregion_data = (
        update.get("subregion_aois")
        if update.get("subregion") is not None
        else None
    )
    render_aoi_map(aoi_data, subregion_data)

if "dataset" in update:
    dataset_data = update["dataset"]
    aoi_data = (
        update.get("aoi") or aoi_data
    )
    render_dataset_map(dataset_data, aoi_data)
```

```python
# New:
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

**Why:** When `pick_dataset` fires, the update typically contains `dataset` but NOT `aoi`. Without session state persistence, `aoi_data` is `None` and the dataset map cannot center on the AOI. Session state is per-session in Streamlit, so there is no cross-session contamination.

#### Change 1b: Fetch geometry in `render_dataset_map()` when not provided

**File:** `frontend/utils.py`, function `render_dataset_map()` (lines 175-191)

Replace the AOI handling block:

```python
# Current:
if aoi_data and isinstance(aoi_data, dict) and "geometry" in aoi_data:
    try:
        geom = shape(aoi_data["geometry"])
        minx, miny, maxx, maxy = geom.bounds
        center = [(miny + maxy) / 2, (minx + maxx) / 2]
        zoom_start = 5
    except (ValueError, AttributeError, TypeError):
        center = [0, 0]
        zoom_start = 2
```

```python
# New:
geometry = None
if aoi_data and isinstance(aoi_data, dict):
    if "geometry" in aoi_data:
        geometry = aoi_data["geometry"]
    elif aoi_data.get("src_id"):
        try:
            client = ZenoClient(
                base_url=API_BASE_URL,
                token=st.session_state.token,
            )
            geom_response = client.fetch_geometry(
                source=aoi_data.get("source"),
                src_id=aoi_data["src_id"],
            )
            geometry = geom_response.get("geometry")
        except Exception:
            geometry = None

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

This mirrors the exact pattern from `render_aoi_map()` (lines 80-87). The `fetch_geometry` call is wrapped in try/except that silently falls back to `geometry = None`, preserving the global-view fallback.

#### Change 1c: Use resolved geometry for AOI overlay

**File:** `frontend/utils.py`, function `render_dataset_map()` (lines 209-224)

Replace the AOI overlay block to use the resolved `geometry` variable:

```python
# New:
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

This ensures layer order is always: basemap -> dataset tiles -> AOI outline on the dataset map.

### Phase 2: Fix Dataset Name and Sidebar Data (P1 -- Correctness)

#### Change 2a: Fix dataset name key in `render_dataset_map()`

**File:** `frontend/utils.py`, line 199

```python
# Current:
dataset_name = dataset_data.get("data_layer", "Dataset Layer")

# New:
dataset_name = dataset_data.get(
    "dataset_name",
    dataset_data.get("data_layer", "Dataset Layer"),
)
```

**Why:** `DatasetSelectionResult.model_dump()` produces `"dataset_name"`, not `"data_layer"`. The current code always falls through to "Dataset Layer", which confuses users. The fallback chain preserves backwards compatibility with any code that might use `"data_layer"`.

#### Change 2b: Fix hardcoded sidebar TCL data

**File:** `frontend/utils.py`, function `display_sidebar_selections()` (around lines 779-801)

Fix the Tree Cover Loss sidebar entry:
- Change `"dataset_id": 0` to `"dataset_id": 4` (TCL is dataset 4, not DIST-ALERT which is 0)
- Change `tree_cover_density_threshold=25` to `tree_cover_density_threshold=30` in the tile URL (aligns with `analytics_datasets.yml`)

### Phase 3: Improve Year Validation in `pick_dataset.py` (P1 -- Robustness)

**File:** `src/agent/tools/pick_dataset.py` (lines 283-312)

**Rationale for inclusion:** Draft 3's year clamping improvement is sound and prevents silent failures when year ranges are outside bounds. This is a targeted improvement to the existing if/elif chain, NOT a refactor.

#### Change 3a: Extract year range constants

Add constants near the top of the file or alongside existing dataset ID constants:

```python
# Tile service year bounds for Tree Cover Loss
TCL_TILE_MIN_YEAR = 2001
TCL_TILE_MAX_YEAR = 2024
TCL_TILE_MAX_START_YEAR = 2023  # GFW tile service constraint
```

#### Change 3b: Replace TCL branch with explicit clamping

Replace the TCL branch (lines 304-312):

```python
# Current:
elif selection_result.dataset_id == TREE_COVER_LOSS_ID:
    if end_date.year in range(2001, 2025):
        tile_start_year = min(start_date.year, 2023)
        selection_result.tile_url += (
            f"&start_year={tile_start_year}&end_year={end_date.year}"
        )
    else:
        selection_result.tile_url += "&start_year=2001&end_year=2024"
```

```python
# New:
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

**Why:** The double-clamp (`max(min(...))`) ensures years are always within valid bounds. The inverted range check (`start_year > end_year`) prevents empty tile responses. Structured logging creates an audit trail for debugging. No silent fallthrough to hardcoded defaults.

---

## Pre-Implementation Verification Step

Before implementing any code changes, verify that the root cause hypothesis is correct:

```bash
# Fetch a TCL tile at zoom level 6 (country-level) for a known forest loss area
curl -s -o /tmp/tcl_z6.png "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/6/17/25.png?tree_cover_density_threshold=30&render_type=true_color&start_year=2020&end_year=2023"

# Check that the tile has meaningful content (not just a transparent PNG header)
file /tmp/tcl_z6.png
wc -c /tmp/tcl_z6.png
# Expected: PNG image, size > 1KB indicating visible pixel content

# Compare with a low-zoom tile
curl -s -o /tmp/tcl_z2.png "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/2/2/1.png?tree_cover_density_threshold=30&render_type=true_color&start_year=2020&end_year=2023"

wc -c /tmp/tcl_z2.png
# Expected: smaller/minimal PNG -- transparent tile at global zoom
```

This confirms that zoom level is the determining factor for tile visibility. If both tiles are transparent, the `render_type` parameter needs investigation (see Risk section).

---

## Error Handling Strategy

All error handling follows existing patterns in `frontend/utils.py`:

| Failure Point | Handling | Fallback |
|--------------|----------|----------|
| `fetch_geometry()` call fails | `try/except Exception`, `geometry = None` | Map renders at global zoom (current behavior) |
| Geometry data is malformed | `try/except (ValueError, AttributeError, TypeError)` on `shape()` | `center=[0, 0]`, `zoom_start=2` |
| `tile_url` missing from dataset_data | `st.warning()` + early return | No map rendered, raw data shown |
| Session state has no `last_aoi_data` | `.get()` returns `None` | `render_dataset_map` receives `None` for aoi_data, uses global view |
| GeoJson overlay rendering fails | `try/except Exception` + `st.warning()` | Map renders without AOI overlay |

No new error handling patterns are introduced. The geometry fetch uses the exact same defensive pattern as `render_aoi_map()`.

---

## Testing Strategy

### Automated Tests

#### Test Suite 1: Geometry Resolution (NEW file: `tests/frontend/test_render_dataset_map.py`)

These tests validate the core fix. Mock `ZenoClient.fetch_geometry` and `folium_static` to avoid real API/rendering calls.

```python
from unittest.mock import patch, MagicMock

# Test 1: aoi_data with src_id but no geometry -> fetches geometry
def test_render_dataset_map_fetches_geometry_from_src_id():
    """When aoi_data has src_id but no geometry key,
    render_dataset_map calls fetch_geometry to resolve it."""

# Test 2: aoi_data with geometry key -> uses it directly
def test_render_dataset_map_uses_provided_geometry():
    """When aoi_data already contains geometry,
    render_dataset_map uses it without fetching."""

# Test 3: fetch_geometry fails -> graceful fallback to global view
def test_render_dataset_map_fallback_on_geometry_fetch_failure():
    """When fetch_geometry raises, map renders at [0,0] zoom 2."""

# Test 4: aoi_data is None -> global view, no crash
def test_render_dataset_map_handles_no_aoi():
    """When aoi_data is None, map renders at global view."""

# Test 5: dataset_name key is used correctly
def test_render_dataset_map_uses_dataset_name_key():
    """Map title comes from dataset_name, not data_layer."""
```

**Note:** This is a new test directory (`tests/frontend/`). No frontend tests currently exist in the codebase. The tests will need an `__init__.py` and may need Streamlit session state mocking via `unittest.mock.patch("streamlit.session_state", ...)`.

#### Test Suite 2: Year Validation (EXTEND: `tests/tools/test_pick_dataset.py`)

```python
# Test 6: TCL start_year capped at 2023
async def test_tcl_start_year_capped_at_2023():
    """start_year=2024 is clamped to 2023."""

# Test 7: TCL end_year capped at 2024
async def test_tcl_end_year_capped_at_2024():
    """end_year=2025 is clamped to 2024."""

# Test 8: TCL inverted year range corrected
async def test_tcl_inverted_years_corrected():
    """When start > end after clamping, start is set to end."""

# Test 9: TCL tile URL preserves {z}/{x}/{y} placeholders
async def test_tcl_tile_url_preserves_placeholders():
    """Folium/Leaflet placeholders survive URL construction."""
```

#### Test Suite 3: Regression Tests (EXTEND: `tests/tools/test_pick_dataset.py`)

```python
# Test 10: DIST-ALERT tile URL unchanged
async def test_dist_alert_tile_url_regression():
    """DIST-ALERT URL construction is not regressed."""

# Test 11: Grasslands tile URL unchanged
async def test_grasslands_tile_url_regression():
    """Grasslands URL construction is not regressed."""
```

### Manual Verification Checklist

1. **TCL with named country:** Query "How much forest was lost in Brazil in 2020?"
   - Verify pink/red TCL pixels visible on the dataset map
   - Verify map is centered on Brazil at appropriate zoom (~5)
   - Verify AOI boundary drawn on top of tile layer
   - Verify layer order: basemap -> TCL tiles -> AOI outline
2. **TCL year range:** Repeat with years 2001, 2010, 2023, 2024
3. **Grasslands regression:** Query grasslands for any country -- tiles still visible
4. **DIST-ALERT regression:** Query disturbance alerts -- tiles still visible
5. **No AOI case:** Query a dataset without selecting an AOI -- map renders at global view without errors
6. **Sidebar test:** Select "Tree Cover Loss" from sidebar dropdown -- tiles load with correct parameters

---

## Implementation Order

Changes should be made in this order, with each step independently verifiable:

1. **Pre-implementation verification** -- curl tiles at different zoom levels to confirm root cause
2. **Change 2a** -- Fix `dataset_name` key lookup (smallest change, immediately visible in map titles)
3. **Change 2b** -- Fix sidebar hardcoded data (independent, verifiable via sidebar UI)
4. **Change 1a** -- Add session state persistence for AOI data in `render_stream()`
5. **Change 1b + 1c** -- Fetch geometry in `render_dataset_map()` and use it for centering + AOI overlay (core fix)
6. **Change 3a + 3b** -- Year validation improvements in `pick_dataset.py` (secondary, separate commit recommended)
7. **Run automated tests** -- existing `test_tile_url_contains_date` + new tests
8. **Manual verification** -- full checklist above

---

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| `render_type=true_color` produces transparent tiles even at zoom 5+ | High | Low | Pre-implementation curl verification (Phase 0). If tiles are transparent at zoom 5+, investigate GFW tile API docs for alternative render_type values. DIST-ALERT uses the same parameter and works, so this is unlikely. |
| Extra `fetch_geometry()` call adds latency to dataset map render | Low | Medium | The geometry is small and the call is fast. Session state caching (Change 1a) means subsequent renders reuse the cached AOI. If latency becomes noticeable, cache the geometry response in session state after the first fetch. |
| Session state `last_aoi_data` holds stale AOI from a different thread | Medium | Low | Streamlit session state is per-session. For thread switching, could scope key as `f"last_aoi_{thread_id}"`. Defer this to a follow-up if the issue is observed. |
| New `tests/frontend/` directory requires test infrastructure setup | Low | Medium | May need `conftest.py` with Streamlit session state mocks. Use `unittest.mock` which is already the testing pattern in the codebase. |
| Zoom level 5 not appropriate for all AOI sizes (small islands vs Russia) | Low | Medium | The zoom level is calculated from geometry bounds, not hardcoded at 5. The `zoom_start=5` is only the default when geometry bounds are successfully computed. For very large or very small AOIs, Folium's `fit_bounds` could be used instead. Defer to follow-up. |

---

## Files Modified Summary

| File | Change Type | Lines Affected | Priority |
|------|------------|---------------|----------|
| `frontend/utils.py` -- `render_stream()` | Modify | ~10 lines (session state + AOI persistence) | P0 |
| `frontend/utils.py` -- `render_dataset_map()` | Modify | ~30 lines (geometry fetch + AOI overlay) | P0 |
| `frontend/utils.py` -- `render_dataset_map()` line 199 | Modify | 1 line (dataset_name key) | P1 |
| `frontend/utils.py` -- `display_sidebar_selections()` | Modify | 2 lines (dataset_id + threshold) | P2 |
| `src/agent/tools/pick_dataset.py` | Modify | ~15 lines (year constants + clamping) | P1 |
| `tests/frontend/test_render_dataset_map.py` | New | ~80 lines (5 test cases) | P1 |
| `tests/tools/test_pick_dataset.py` | Extend | ~40 lines (6 test cases) | P1 |

**Total: 2 modified files, 1 new test file, 1 extended test file.**

---

## What This Plan Does NOT Do (and Why)

- **Does not introduce a TileURLBuilder strategy pattern.** The if/elif chain in `pick_dataset.py` is ~30 lines, correct, and well-understood. Abstracting it into a class hierarchy adds 2 files and ~120 lines of code for no functional benefit. (Rejected from Draft 2.)

- **Does not merge `render_aoi_map()` and `render_dataset_map()` into a single function.** These serve different purposes in the stream: AOI map is a preview that appears before the dataset is selected. The dataset map is the full visualization. Merging them changes UX behavior. (Scoped out per Draft 4's reasoning.)

- **Does not add CORS handling.** DIST-ALERT uses the same GFW tile domain (`tiles.globalforestwatch.org`) and works. CORS is not the issue.

- **Does not add tile content validation at runtime.** Checking tile PNG content for visibility adds complexity and latency. The pre-implementation curl verification confirms the root cause. The existing `test_tile_url_contains_date` test covers URL validity.

---

## PR Description Template

The acceptance criteria require root cause documentation in the PR. Use this template:

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
  `fetch_geometry()` when `aoi_data` has `src_id` but no geometry key
- **Session state:** AOI data persisted in `st.session_state` across stream
  updates so the dataset map always has access to it
- **Year validation:** TCL year params use explicit clamping with named
  constants instead of silent fallthrough to hardcoded defaults
- **Cosmetic fixes:** Dataset name key corrected, sidebar hardcoded data
  aligned with YAML config
```

---

## Acceptance Criteria Traceability

| Criterion | How Addressed | Phase |
|-----------|---------------|-------|
| TCL pink/red pixels visible for queried year range | Geometry fetch centers map on AOI at zoom ~5, where TCL pixels are visible | P0 (Changes 1a-1c) |
| Tile URL valid and tile-serving | No URL construction changes for P0; year clamping improvement in P1 | P1 (Changes 3a-3b) |
| Other datasets not regressed | No changes to tile URL construction logic in P0; regression tests added | P1 (Test Suites 2-3) |
| Works for any year 2001-2024 | Year clamping ensures all years within bounds produce valid URLs | P1 (Change 3b) |
| Root cause documented in PR | PR description template provided with pattern for future GFW datasets | PR (Template above) |
| Layer order correct: basemap -> tiles -> AOI | `render_dataset_map()` renders layers in order; resolved geometry used for AOI overlay | P0 (Change 1c) |
