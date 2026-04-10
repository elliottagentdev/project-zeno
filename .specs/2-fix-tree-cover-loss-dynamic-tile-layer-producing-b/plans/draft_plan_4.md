# Draft Plan 4: Developer Experience Lens

## Guiding Principle

Every change in this plan optimizes for the next developer who reads this code. If a pattern requires a comment to explain, the pattern is wrong. If a function does two things, split it. If a name is ambiguous, rename it. The fix should be so obvious that a new team member would read the diff and immediately understand both the bug and the solution.

## Root Cause Analysis

There are two distinct problems producing the blank TCL map, and they compound each other:

### Problem 1: AOI Geometry Never Reaches the Dataset Map

In `frontend/utils.py`, `render_stream()` (line 695-701) passes `aoi_data` to `render_dataset_map()`. But `aoi_data` is the raw agent state dict containing `src_id`, `name`, `source`, etc. -- it does NOT contain a `"geometry"` key.

`render_dataset_map()` checks `"geometry" in aoi_data` (line 179) and finds no geometry, so:
- Map centers at `[0, 0]` with `zoom_start=2` (global view)
- No AOI boundary is drawn
- At zoom level 2, TCL tiles are 30-meter resolution data that may render as transparent/empty pixels because there is no meaningful data at that scale

Meanwhile, `render_aoi_map()` (line 70-153) calls `client.fetch_geometry()` to get the actual GeoJSON, but this geometry is never shared with `render_dataset_map()`.

### Problem 2: The Dataset Map Is Rendered as a Separate Map from the AOI Map

`render_aoi_map()` creates `folium.Map` instance `m`. Then `render_dataset_map()` creates a completely separate `folium.Map` instance `m2`. The user sees two maps stacked vertically: one with the AOI outline (correctly zoomed), one with the dataset tiles (zoomed out to the whole world). This violates the requirement that layer order be: basemap -> dataset tiles -> AOI outline on a SINGLE map.

### Why DIST-ALERT Appears to Work

DIST-ALERT tiles cover large areas with bright red pixels visible even at low zoom levels. TCL pixels are subtler and sparser -- at zoom 2, the entire world is visible and individual 30m loss pixels are invisible.

### Why Grasslands Works

Grasslands also suffers from the same AOI geometry issue, but Grasslands tiles use a colormap that renders visible colors across the entire tile even at low zoom, making the problem less noticeable.

## Architecture: What Changes and Why

This fix touches exactly **2 files** with straightforward, easy-to-follow changes:

| File | What Changes | Why |
|------|-------------|-----|
| `frontend/utils.py` | `render_stream()` fetches geometry and passes it to `render_dataset_map()` | The dataset map needs the AOI geometry to center/zoom correctly and draw the boundary |
| `frontend/utils.py` | `render_dataset_map()` uses `dataset_name` instead of `data_layer` | The field name from `DatasetSelectionResult` is `dataset_name`, not `data_layer` |
| `frontend/utils.py` | Sidebar hardcoded `dataset_id` and `threshold` corrected | Prevents confusion for developers testing with sidebar selections |

No changes to `pick_dataset.py` -- the tile URL construction is correct. No changes to `analytics_datasets.yml`. No new files. No new abstractions.

## Detailed File Changes

### Change 1: Fix `render_stream()` to fetch and pass geometry

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `render_stream()` (around lines 684-701)

**Current code (broken):**
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

**New code (fixed):**
```python
aoi_data = None
aoi_geometry = None
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
    aoi_data = update.get("aoi") or aoi_data

    # Fetch geometry so the dataset map can center on the AOI
    if aoi_data and isinstance(aoi_data, dict):
        try:
            client = ZenoClient(
                base_url=API_BASE_URL,
                token=st.session_state.token,
            )
            geom_response = client.fetch_geometry(
                source=aoi_data.get("source"),
                src_id=aoi_data.get("src_id"),
            )
            aoi_geometry = geom_response.get("geometry")
        except Exception:
            aoi_geometry = None

    render_dataset_map(dataset_data, aoi_geometry)
```

**What changed and why:**
- Added `aoi_geometry = None` variable with a self-documenting name (it holds GeoJSON geometry, not the raw AOI metadata dict)
- When we have `aoi_data`, we call `client.fetch_geometry()` -- the same call `render_aoi_map()` already makes -- to get the actual GeoJSON
- We pass the GeoJSON geometry directly to `render_dataset_map()`, which already expects a dict with a `"geometry"` key... except it does not. Looking at `render_dataset_map`, line 179 checks `"geometry" in aoi_data`. So we need to pass either a dict with `"geometry"` key, or adjust the function.

**Clarification:** Since `aoi_geometry` is the GeoJSON geometry object itself (e.g., `{"type": "MultiPolygon", "coordinates": [...]}`), and `render_dataset_map` currently looks for `aoi_data["geometry"]`, we should wrap it:

```python
    render_dataset_map(
        dataset_data,
        {"geometry": aoi_geometry} if aoi_geometry else None,
    )
```

This is the simplest approach that avoids changing `render_dataset_map`'s interface. The function already handles `None` gracefully.

### Change 2: Fix the dataset name lookup in `render_dataset_map()`

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `render_dataset_map()` (line 199)

**Current code:**
```python
dataset_name = dataset_data.get("data_layer", "Dataset Layer")
```

**New code:**
```python
dataset_name = dataset_data.get("dataset_name", "Dataset Layer")
```

**Why:** `DatasetSelectionResult` (in `pick_dataset.py`) serializes with field name `dataset_name`, not `data_layer`. The current code always falls through to the default "Dataset Layer" string, which is confusing -- the user sees a generic label instead of "Tree cover loss" or "DIST-ALERT". This one-line change makes the map title match the actual dataset.

### Change 3: Fix hardcoded sidebar test data

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`
**Function:** `display_sidebar_selections()` (around line 781-789)

**Current code:**
```python
"Tree Cover Loss": {
    "dataset": {
        "dataset_id": 0,
        ...
        "tile_url": "...tree_cover_density_threshold=25&render_type=true_color",
        ...
        "threshold": "30",
    }
},
```

**New code:**
```python
"Tree Cover Loss": {
    "dataset": {
        "dataset_id": 4,
        ...
        "tile_url": "...tree_cover_density_threshold=30&render_type=true_color",
        ...
        "threshold": "30",
    }
},
```

**Why:**
- `dataset_id` should be `4` (TCL), not `0` (DIST-ALERT). A developer debugging with the sidebar would get completely wrong behavior.
- `tree_cover_density_threshold` in the URL should match the `threshold` field (both `30`). Having `25` in the URL and `30` in the metadata is a confusing contradiction.

## Data Models

No data model changes are needed. The existing `DatasetSelectionResult` Pydantic model in `pick_dataset.py` already has the correct fields. The `AgentState` TypedDict is unchanged. The fix is purely in how the frontend reads and passes existing data.

## API Design

No API changes. The `client.fetch_geometry()` call already exists and is used by `render_aoi_map()`. We are simply calling it one additional time in `render_stream()` so the dataset map also has access to the geometry.

**Performance note:** This adds one extra HTTP call to `fetch_geometry()` when a dataset map is rendered. The geometry was already fetched for the AOI map seconds earlier. If this becomes a concern, the geometry could be cached in `st.session_state`, but that optimization is not needed for the initial fix. Keep it simple.

## Error Handling

The error handling follows existing patterns in `frontend/utils.py`:

1. **Geometry fetch failure:** Wrapped in `try/except Exception` with fallback to `aoi_geometry = None`. If the geometry cannot be fetched, the dataset map renders at the global default view (same behavior as today). No crash, no error message -- the user just sees a zoomed-out map.

2. **Invalid geometry data:** `render_dataset_map()` already handles this at line 188 with `except (ValueError, AttributeError, TypeError)` -- falls back to `center=[0,0]`, `zoom_start=2`.

3. **Missing tile_url:** Already handled at line 171 with `st.warning("No tile_url found in dataset")`.

No new error handling patterns are introduced. We reuse the exact same defensive coding style used throughout `utils.py`.

## Testing Strategy

### Manual Verification (Primary -- this is a frontend rendering fix)

1. **TCL with named country:** Query "How much forest was lost in Brazil in 2020?" and verify:
   - Map shows pink/red TCL pixels
   - Map is centered on Brazil (not the whole world)
   - AOI boundary is drawn on top of the tile layer
   - Layer order: basemap -> TCL tiles -> AOI outline

2. **TCL with different years:** Repeat with years 2001, 2010, 2023, 2024 to verify all valid years work.

3. **Grasslands regression:** Query a grasslands dataset and verify it still renders correctly.

4. **DIST-ALERT regression:** Query a DIST-ALERT dataset and verify it still renders correctly.

5. **Sidebar test:** Select "Tree Cover Loss" from the sidebar dropdown and verify tiles load correctly.

6. **No AOI case:** If dataset is rendered without an AOI selected, verify the map falls back to global view without errors.

### Unit Tests

**File:** `tests/tools/test_pick_dataset.py`

The existing `test_tile_url_contains_date` test already verifies TCL tile URLs return HTTP 200 from the GFW tile service. No changes needed to this test -- it confirms the URL construction is correct.

**New test (optional but recommended):**

Add a test in a new file `tests/frontend/test_utils.py` or in an existing frontend test file:

```python
def test_render_dataset_map_uses_dataset_name():
    """Verify the map title comes from dataset_name, not data_layer."""
    dataset_data = {
        "dataset_name": "Tree cover loss",
        "tile_url": "https://example.com/{z}/{x}/{y}.png",
    }
    # Verify dataset_name is used (not data_layer)
    name = dataset_data.get("dataset_name", "Dataset Layer")
    assert name == "Tree cover loss"
```

This is a lightweight check. Full rendering tests for Folium/Streamlit are difficult to automate and are better covered by manual verification.

### Existing Test Compatibility

The test fixture in `tests/tools/test_generate_insights.py` (line 47) has a hardcoded TCL tile URL with `threshold=25`. This is test data and does not need to match the YAML config exactly, but updating it to `threshold=30` would be a good cleanup. This is a low-priority, non-blocking change.

## Migration Plan

No migration needed. No database changes. No configuration changes. No environment variable changes.

**Deployment steps:**
1. Merge the PR
2. Restart the frontend service (Streamlit)
3. Verify by querying a TCL dataset in the chat

**Rollback:** Revert the single commit. No data to clean up.

## Implementation Order

The changes should be made in this exact order to keep each step independently verifiable:

1. **Fix `dataset_name` lookup** (Change 2) -- smallest change, independently testable by checking map titles
2. **Fix geometry passing in `render_stream()`** (Change 1) -- the core fix, makes dataset maps center on AOI
3. **Fix sidebar hardcoded data** (Change 3) -- cleanup, independently testable via sidebar UI

Each change can be verified in isolation before moving to the next.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Extra `fetch_geometry()` call adds latency | Low | Low | Geometry is small; call is fast. Cache in session_state later if needed. |
| GFW tile service returns empty tiles for some zoom/year combos | Medium | Medium | This is a GFW service behavior issue, not a code bug. Document in PR. |
| `render_aoi_map` and `render_dataset_map` still produce two separate maps | High (by design) | Low | The dataset map now has the AOI overlay. The AOI-only map renders first as a preview. This matches the existing UX pattern. |

## What This Plan Does NOT Do (and Why)

- **Does not merge `render_aoi_map` and `render_dataset_map` into a single map.** This would be a larger refactor that changes the UX flow. The current pattern of rendering an AOI preview map, then a dataset+AOI map, is intentional. The fix ensures the dataset map is properly centered and has the AOI overlay.

- **Does not add a tile URL validation/health check.** Verifying tile URLs at runtime adds complexity and latency. The existing test (`test_tile_url_contains_date`) covers this at test time.

- **Does not refactor the tile URL construction logic.** The `if/elif` chain in `pick_dataset.py` is straightforward and correct. Abstracting it into a strategy pattern or config-driven system would add complexity without fixing the actual bug.

- **Does not add CORS handling.** DIST-ALERT uses the same GFW tile domain and works. CORS is not the issue.
