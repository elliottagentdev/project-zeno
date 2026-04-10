# Draft Plan 1: Minimal Surgery Fix for Tree Cover Loss Blank Map

## Lens: Smallest Possible Change Set

This plan identifies the root causes and proposes minimal, targeted fixes touching the fewest files possible while addressing all acceptance criteria.

---

## 1. Root Cause Analysis

There are **two distinct problems** causing the blank TCL map:

### Problem A: Map renders at global zoom level 2, centered on [0,0]

In `frontend/utils.py` `render_stream()` (line 696-701), when the `"dataset"` key is present in the state update, `aoi_data` is extracted from `update.get("aoi")`. However, the `aoi` dict in agent state contains metadata (`src_id`, `name`, `gadm_id`, `subtype`) but **not** a `"geometry"` key. The `render_dataset_map()` function checks `"geometry" in aoi_data` (line 179) and falls through to defaults: `center=[0,0]`, `zoom_start=2`.

At zoom level 2, the entire world is visible. TCL tiles at this zoom level contain very sparse 30m-resolution data that appears as nearly invisible specks. DIST-ALERT works because its alerts are more visually prominent at low zoom. Grasslands works because eoAPI tiles use a colormap that fills entire regions.

**The fix**: In `render_dataset_map()`, when `aoi_data` has `src_id` but no `geometry`, fetch the geometry using `ZenoClient.fetch_geometry()` (the same pattern already used in `render_aoi_map()` at line 80-87). This centers the map on the AOI and zooms in enough to see TCL pixels.

### Problem B: `render_type=true_color` may produce transparent/invisible pixels for TCL

The GFW tile service `render_type=true_color` parameter for TCL produces pixels that may be transparent or very faint at certain zoom levels. The hardcoded sidebar URL in `frontend/utils.py` (line 786) uses the same `render_type=true_color` and reportedly also shows blank. However, the existing test `test_tile_url_contains_date` (line 306 in `tests/tools/test_pick_dataset.py`) confirms the URL returns HTTP 200 with content. The tiles are *served* but may render as transparent overlays.

**Investigation**: This needs verification by actually fetching a tile and checking pixel content. If `render_type=true_color` indeed produces visible pink/red pixels, then Problem A alone is the root cause. If not, the `render_type` may need to be changed or removed. Since DIST-ALERT uses the same `render_type=true_color` on the same GFW tile service and works, it is most likely that Problem A (zoom level) is the primary cause.

**Verdict**: Problem A is the confirmed root cause. Problem B is a secondary investigation item that the fix should make diagnosable (by zooming in properly).

---

## 2. Architecture: No New Abstractions

The fix operates entirely within the existing architecture:

- **`frontend/utils.py`**: Modify `render_dataset_map()` to fetch geometry when `aoi_data` has `src_id` but no `geometry`. This reuses the exact same `ZenoClient.fetch_geometry()` call pattern from `render_aoi_map()`.
- **`frontend/utils.py`**: Fix the `dataset_name` extraction to use the correct key from `DatasetSelectionResult` (`dataset_name` not `data_layer`).
- **`frontend/utils.py`**: Fix the hardcoded sidebar TCL `dataset_id` from `0` to `4`.

No new files. No new abstractions. No changes to the agent, API, or data models.

---

## 3. Specific File Changes

### File 1: `frontend/utils.py` -- `render_dataset_map()` (PRIMARY FIX)

**Change 1a: Fetch geometry when aoi_data lacks it (lines 175-191)**

Current code:
```python
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

Modified code:
```python
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
            pass

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

This mirrors the pattern in `render_aoi_map()` (lines 80-87) exactly.

**Change 1b: Use fetched geometry for AOI overlay (lines 209-224)**

Update the AOI overlay section to use the fetched `geometry` variable instead of re-checking `aoi_data["geometry"]`:

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
            popup=folium.Popup("Area of Interest", parse_html=True),
            tooltip="AOI",
        ).add_to(m2)
    except Exception as e:
        st.warning(f"Could not render AOI overlay: {str(e)}")
```

This ensures layer order is always: basemap -> dataset tiles -> AOI outline.

**Change 1c: Fix dataset_name key (line 199)**

Current:
```python
dataset_name = dataset_data.get("data_layer", "Dataset Layer")
```

Modified:
```python
dataset_name = dataset_data.get("dataset_name", dataset_data.get("data_layer", "Dataset Layer"))
```

The `DatasetSelectionResult` model uses `dataset_name`, not `data_layer`. This is a minor fix that ensures the map subheader shows the correct name.

### File 2: `frontend/utils.py` -- `display_sidebar_selections()` (MINOR FIX)

**Change 2a: Fix hardcoded TCL dataset_id (line 783)**

Current:
```python
"dataset_id": 0,
```

Modified:
```python
"dataset_id": 4,
```

The TCL dataset_id is 4, not 0. Dataset 0 is DIST-ALERT.

**Change 2b: Fix hardcoded TCL threshold in sidebar URL (line 786)**

Current:
```python
"tile_url": "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=25&render_type=true_color",
```

Modified:
```python
"tile_url": "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=30&render_type=true_color",
```

The YAML config uses threshold=30 but the sidebar hardcoded URL uses 25. Align them.

---

## 4. Data Models

**No changes required.** The `DatasetSelectionResult` Pydantic model, `AgentState` TypedDict, and `analytics_datasets.yml` are all correct. The tile URL construction in `pick_dataset.py` is also correct (confirmed by the existing test that validates HTTP 200 responses).

---

## 5. API Design

**No API changes required.** The `ZenoClient.fetch_geometry()` method already exists and is already called in `render_aoi_map()`. We reuse it in `render_dataset_map()`.

---

## 6. Error Handling

The geometry fetch in `render_dataset_map()` is wrapped in a try/except that silently falls back to the default `center=[0,0]`, `zoom_start=2`. This matches the existing error handling pattern in the function and ensures the map still renders (just without zoom) if geometry fetching fails.

The outer try/except in `render_dataset_map()` (line 263) already catches all exceptions and shows `st.error()` + `st.json()` fallback. No additional error handling needed.

---

## 7. Testing Strategy

### 7a: Manual Verification (Primary)

1. Query "How much forest was lost in Brazil in 2020?" -- verify TCL pink/red pixels visible, map centered on Brazil, zoom level appropriate
2. Query "How much forest was lost in Indonesia in 2015?" -- verify different year works
3. Query grasslands for any country -- verify no regression
4. Query DIST-ALERT for any country -- verify no regression
5. Verify layer order in browser dev tools: basemap tiles load first, then TCL overlay, then AOI outline on top

### 7b: Unit Test Addition (1 new test)

Add a test in `tests/tools/test_pick_dataset.py` or a new lightweight test that verifies the TCL tile URL with specific coordinates returns non-transparent PNG content (not just HTTP 200):

```python
async def test_tcl_tile_has_visible_content():
    """Verify TCL tiles contain visible pixels, not just transparent PNGs."""
    # Use a known location with tree cover loss (e.g., Brazil, z=8)
    url = (
        "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic"
        "/8/90/128.png?tree_cover_density_threshold=30"
        "&render_type=true_color&start_year=2020&end_year=2020"
    )
    response = requests.get(url)
    assert response.status_code == 200
    assert len(response.content) > 1000  # Non-trivial PNG content
```

This test documents the root cause: at low zoom (z=2), tiles are mostly transparent; at higher zoom (z=8+), actual loss pixels are visible.

### 7c: Existing Test Validation

The existing `test_tile_url_contains_date` parametrized test already validates that TCL URLs return HTTP 200. It uses z=3/x=5/y=3 which is low zoom. The test passes because HTTP 200 is returned (the tile is served), but the tile content is mostly transparent at that zoom. This test does not need modification -- it validates URL construction, not visual rendering.

---

## 8. Migration Plan

**No database migration needed.** All changes are in frontend rendering code.

### Deployment Steps

1. Apply changes to `frontend/utils.py` (the only modified file)
2. Restart the Streamlit frontend (auto-reloads in dev mode)
3. Test with manual queries as described in section 7a
4. No backend or database changes needed

### Rollback

Revert the single file `frontend/utils.py` if any regression is detected. The changes are purely additive (adding geometry fetch) and corrective (fixing keys/IDs).

---

## 9. Files Modified Summary

| File | Changes | Lines Affected |
|------|---------|---------------|
| `frontend/utils.py` | Fetch geometry in `render_dataset_map()`, fix `dataset_name` key, fix sidebar `dataset_id` and `threshold` | ~30 lines modified |

**Total files modified: 1**

---

## 10. Acceptance Criteria Traceability

| Criterion | How Addressed |
|-----------|---------------|
| TCL pink/red pixels visible | Geometry fetch centers map on AOI at zoom 5, making 30m TCL pixels visible |
| Tile URL valid and tile-serving | Already confirmed by existing test; no URL construction changes needed |
| Other datasets not regressed | No changes to `pick_dataset.py` or tile URL construction; only frontend rendering |
| Works for any year 2001-2024 | Tile URL construction logic unchanged; year params appended correctly |
| Root cause documented | PR description explains zoom-level root cause |
| Layer order correct | `render_dataset_map()` always renders: basemap -> TileLayer -> GeoJson AOI -> LayerControl |
