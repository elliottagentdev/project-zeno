# Red Team Report 4: Contradictions, Edge Cases, and Failure Modes

## 1. Internal Contradictions

### 1.1 Sidebar dataset_id Contradiction with Actual Constants

The plan states in Change 2b: "Change `dataset_id: 0` to `dataset_id: 4` (TCL is dataset 4, not DIST-ALERT which is 0)." However, the actual codebase derives `DIST_ALERT_ID` and `TREE_COVER_LOSS_ID` dynamically from `DATASETS` via list comprehension at runtime (`analytics_handler.py` lines 85-110). The plan hardcodes `dataset_id: 4` without verifying that this is the actual runtime value. If the `analytics_datasets.yml` changes or datasets are reordered, the sidebar hardcoded value will silently diverge again. The plan also claims DIST-ALERT is dataset 0, but the sidebar already has DIST-ALERT with `dataset_id: 14` (line 793), contradicting the plan's own claim about what dataset_id 0 represents.

### 1.2 Session State Caching Does Not Actually Prevent Duplicate fetch_geometry Calls

The plan claims in the Risk Register: "Session state caching (Change 1a) means subsequent renders reuse the cached AOI." This is misleading. Change 1a caches `aoi_data` (the metadata dict with `src_id`, `name`, `source`) in session state -- NOT the fetched geometry. Change 1b then calls `fetch_geometry()` every time `render_dataset_map()` is called with `aoi_data` lacking a `"geometry"` key. Since Change 1a never adds the geometry to the cached `aoi_data`, every dataset map render triggers a new HTTP call to `fetch_geometry()`. The plan acknowledges the duplicate call risk but claims caching mitigates it, when the proposed caching does not actually cache the geometry result.

### 1.3 Zoom Level 5 Claim vs. Bounds-Based Calculation

The plan says under Risk: "The zoom level is calculated from geometry bounds, not hardcoded at 5." But looking at the actual proposed code in Change 1b, `zoom_start = 5` IS hardcoded as the value used when geometry bounds are successfully computed. There is no bounds-to-zoom calculation. Russia at zoom 5 would show a tiny fraction of the country. A small island at zoom 5 might show mostly ocean. The plan contradicts itself on whether zoom is dynamic or hardcoded.

## 2. Ordering Dependencies That Break

### 2.1 Implementation Order Mismatch with Dependency Chain

The plan recommends implementing Change 2a (dataset name key) before Change 1a (session state). However, the pre-implementation verification (step 1) uses `curl` to confirm the root cause. If the curl test fails (tiles are transparent even at zoom 5+), the entire plan's premise collapses, but the plan has already listed Changes 2a and 2b as steps 2-3 to implement before the verification is confirmed. The ordering should strictly gate all subsequent changes on the curl verification result.

### 2.2 Change 1b Depends on Streamlit Session State Token

Change 1b creates a `ZenoClient` with `st.session_state.token`. If `render_dataset_map()` is called in a context where `st.session_state.token` is not yet set (e.g., during initial page load, or in a test runner without proper session setup), this will throw an `AttributeError` on `st.session_state.token` or a `ValueError` from `fetch_geometry()` ("Token is required to fetch geometry"). The existing `render_aoi_map()` has the same vulnerability, but that function is only called from `render_stream()` which runs after authentication. The plan does not verify that `render_dataset_map()` is always called post-authentication.

## 3. Unhandled Edge Cases

### 3.1 Geometry API Returns Non-GeoJSON or Unexpected Structure

The plan assumes `client.fetch_geometry()` returns `{"geometry": <valid-geojson>}`. But `fetch_geometry` in `client.py` simply returns `response.json()`. If the API returns `{"geometry": null}`, `{"geometry": "invalid"}`, or a structure without a `"geometry"` key, the code sets `geometry = None` (good). But if the API returns `{"geometry": {"type": "GeometryCollection", "geometries": []}}` -- a valid but empty geometry -- `shape()` will succeed, `geom.bounds` will return `(inf, inf, -inf, -inf)`, and the center calculation will produce `(inf, inf)`. Folium will silently fail or produce a broken map.

### 3.2 AOI Data with Neither geometry nor src_id

The plan handles two cases: `aoi_data` has `"geometry"` key, or `aoi_data` has `"src_id"`. But what if `aoi_data` is `{"name": "Test Area", "source": "custom"}` with no `src_id` and no `geometry`? The code falls through to `geometry = None`, which is correct. But the plan does not document this as an expected path, and there is no logging to help debug why the map is showing a global view when a user expects it to be centered.

### 3.3 Concurrent Stream Updates and Session State Race

Streamlit reruns the entire script on each interaction. If two stream updates arrive in rapid succession (e.g., AOI and dataset nearly simultaneously), the session state write in Change 1a (`st.session_state["last_aoi_data"] = aoi_data`) and read in the same function could exhibit a race condition. Streamlit's execution model serializes reruns per session, but if `render_stream()` is called in a loop processing multiple updates within a single script run, the `st.session_state` write from an earlier iteration may not be visible in a later iteration of the same run, depending on when Streamlit flushes state.

### 3.4 Large or Complex Geometries

For countries like Russia, Indonesia (archipelago with thousands of islands), or France (with overseas territories), the geometry returned by `fetch_geometry()` can be several megabytes. The plan does not consider:
- Memory pressure from storing large geometries in session state
- Rendering latency for `folium.GeoJson` with complex multipolygons
- The `shape()` call on a very complex geometry being slow
- The bounds of France including French Guiana, Reunion, etc., producing a bounding box that spans the entire globe -- making zoom 5 useless

### 3.5 Sidebar TCL Tile URL Has Hardcoded Year Parameters

The sidebar `DATASET_OPTIONS` for TCL hardcodes `start_year=2001&end_year=2024`. When a user selects TCL from the sidebar dropdown, they get a fixed year range regardless of any date range they may have selected. The plan fixes `dataset_id` and `threshold` but does not address the fact that the sidebar bypass completely ignores the year range selector, making it functionally different from the agent-driven flow.

## 4. Error Paths Not Covered

### 4.1 fetch_geometry HTTP Timeout

`client.fetch_geometry()` uses `requests.get()` without a `timeout` parameter. If the geometry API is slow or unresponsive, the call will block indefinitely (default requests behavior). The `try/except Exception` in Change 1b will not catch this -- it will simply hang the Streamlit render thread. The existing `render_aoi_map()` has the same bug, but the plan explicitly adds a new call site without fixing the timeout issue. In production, a slow geometry API means the dataset map never renders and the user sees an infinite spinner.

### 4.2 Token Expiry Mid-Session

The plan uses `st.session_state.token` to authenticate the `fetch_geometry` call. If the token expires between the AOI map render and the dataset map render (possible in long-running sessions), the geometry fetch will return a 401, which `fetch_geometry` converts to a generic `Exception`. The plan catches this and falls back to global zoom, but there is no mechanism to refresh the token or inform the user that re-authentication is needed. The user sees a global-zoom map with no explanation.

### 4.3 Network Partition Between Frontend and API

If the network between the Streamlit frontend and the Zeno API goes down after the AOI map renders but before the dataset map renders, `fetch_geometry` will throw a `requests.ConnectionError`. The plan catches this as `Exception`, but the resulting user experience is a dataset map at global zoom with no indication that the geometry fetch failed. The `st.warning` is only shown for the GeoJson overlay failure, not for the geometry fetch failure.

### 4.4 Malformed dataset_data from Agent State

The plan assumes `dataset_data` is always a well-formed dict from `DatasetSelectionResult.model_dump()`. But `render_stream()` takes `update["dataset"]` directly from `json.loads(stream["update"])`. If the agent produces malformed output (missing `tile_url`, wrong types), the `dataset_data.get("tile_url")` check catches missing URLs. But if `tile_url` is present but malformed (e.g., missing `{z}/{x}/{y}` placeholders, or containing unescaped characters), Folium will silently fail to load tiles. The plan has no validation of tile URL format.

## 5. Production Assumptions That May Fail

### 5.1 render_type=true_color Assumption

The plan's entire root cause hypothesis rests on the assumption that TCL tiles at zoom 5+ contain visible pixels. The pre-implementation curl verification is supposed to confirm this, but it is listed as a "pre-implementation" step rather than a gate. If tiles at zoom 5 are also transparent (e.g., because `render_type=true_color` requires specific query parameters, or the tile service has changed its behavior), the fix will center the map on the AOI but still show a blank overlay. The plan says "if both tiles are transparent, the `render_type` parameter needs investigation" but provides no alternative plan. This is a single point of failure for the entire fix.

### 5.2 GFW Tile Service Availability and Rate Limiting

The plan adds `fetch_geometry` calls to the rendering path but does not consider that the GFW tile service (`tiles.globalforestwatch.org`) may rate-limit or block requests. Each map render triggers tile requests for all visible tiles at the current zoom level. At zoom 5 for a large country, this could be 20-50 tile requests. If the tile service throttles or blocks the Streamlit server's IP (especially in shared hosting environments), all TCL maps will appear blank. The plan has no error handling for tile loading failures -- these happen client-side in the browser and are invisible to the Python backend.

### 5.3 Streamlit Session State Across Deployment Restarts

The plan stores `last_aoi_data` in `st.session_state`. Streamlit session state does not survive server restarts or deployment updates. If the server is restarted between the AOI selection and the dataset selection (possible during a rolling deployment), `st.session_state.get("last_aoi_data")` returns `None`, and the dataset map falls back to global zoom. This is a transient issue but could confuse users during deployments.

### 5.4 Year Constant Maintenance Burden

Change 3a introduces `TCL_TILE_MAX_YEAR = 2024` and `TCL_TILE_MAX_START_YEAR = 2023` as constants. These values are tied to the GFW tile service's data availability, which changes annually. When GFW adds 2025 data, someone must remember to update these constants. The plan creates a maintenance burden without any mechanism to detect when the constants are stale (e.g., no health check, no automated test against the live tile service). The existing code had the same problem with magic numbers, but promoting them to named constants makes them look more authoritative and therefore less likely to be questioned when they become outdated.

## 6. Security Concerns

### 6.1 Token Exposure in Error Messages

`fetch_geometry` in `client.py` raises `Exception(f"Request failed with status code {response.status_code}: {response.text}")`. If the API returns an error response that includes the request headers (some API frameworks do this in debug mode), the auth token could be included in the exception message. The plan's `try/except Exception` in Change 1b silently swallows this, but if future refactoring adds logging of the exception, the token could be written to logs.

### 6.2 Geometry API Path Traversal

`fetch_geometry` constructs the URL as `f"{self.base_url}/api/geometry/{source}/{src_id}"`. The `source` and `src_id` values come from the agent state, which is derived from LLM output. If the LLM produces a malicious `src_id` containing path traversal characters (e.g., `../../admin/users`), the URL would become `{base_url}/api/geometry/{source}/../../admin/users`. While most web frameworks normalize paths, this depends on the API server's routing implementation. The plan does not sanitize these inputs.

### 6.3 Session State Stores Potentially Sensitive Geometry Data

The plan stores AOI data (which may include geometry for sensitive locations like military installations or indigenous territories selected via the agent) in Streamlit session state. Streamlit session state is stored in-memory on the server and is accessible to any code running in the same session. If another component or a debug endpoint exposes session state, geometry data could be leaked. This is a pre-existing concern but the plan expands the attack surface by adding `last_aoi_data` to session state.

## 7. Testing Gaps

### 7.1 No Integration Test for the Full Render Path

The test plan mocks `ZenoClient.fetch_geometry` and `folium_static`. This means the actual HTTP call to the geometry API, the actual Folium rendering, and the actual tile loading are never tested together. The root cause is a rendering/zoom issue, but the tests only verify that the mocked functions are called with expected arguments. A tile URL that returns 200 but produces transparent PNGs would pass all proposed tests.

### 7.2 No Test for Session State Persistence Across Stream Updates

Test Suite 1 tests `render_dataset_map()` in isolation. No test verifies that `render_stream()` correctly persists `aoi_data` to session state and that a subsequent call to `render_stream()` with a `dataset` update (but no `aoi` update) correctly retrieves the cached AOI data. This is the exact scenario that Change 1a is designed to fix, but it has no automated test.

### 7.3 No Regression Test for Sidebar Flow

The sidebar `DATASET_OPTIONS` bypasses the agent entirely and passes hardcoded data directly to the rendering path. No test verifies that sidebar-selected datasets render correctly. The plan fixes sidebar hardcoded values but adds no test to prevent future regressions.

### 7.4 No Test for Year Clamping with start_year > end_year After Clamping

The plan mentions Test 8 (`test_tcl_inverted_years_corrected`) but the test description says "When start > end after clamping, start is set to end." This only tests one direction of the inversion. What about `start_date.year = 2000` (clamped to 2001) and `end_date.year = 2000` (clamped to 2001)? Both clamp to the same value -- is `start_year == end_year` a valid request to the GFW tile API? The plan does not verify this edge case with the actual tile service.
