# Red Team Report: Master Plan Ambiguities and Gaps

## Phase 1: Fix Geometry Flow (P0 -- Core Bug Fix)

### Change 1a: Session State Caching -- Stale State and Lifecycle Ambiguity

**Ambiguity 1: When is `last_aoi_data` cleared?**
The plan says to store `st.session_state["last_aoi_data"]` when an AOI arrives, but never specifies when or if it should be cleared. If a user starts a new query without selecting an AOI (e.g., querying a dataset globally), the stale AOI from the previous query will be used. Two developers would handle this differently:
- Developer A: Clear `last_aoi_data` at the start of each new chat message.
- Developer B: Never clear it, relying on the user to always pick an AOI.
The plan does not address this, and the risk register mentions it only as "defer to follow-up."

**Ambiguity 2: `render_stream()` is called per-update, not per-session.**
The plan's "Current" code block for `render_stream()` (lines 684-701) shows `aoi_data = None` at the top. But in the actual code at line 685, `aoi_data = None` is set inside the function body -- meaning each call to `render_stream()` already resets `aoi_data`. The plan correctly identifies the need for session state, but does not clarify whether `render_stream()` is called once per full response or once per streaming chunk. In the actual code, it is called once per streaming update dict. A developer unfamiliar with the Streamlit streaming pattern might not realize that `aoi_data = None` at line 685 means the local variable is always reset, making session state genuinely necessary.

**Ambiguity 3: Thread-scoped vs session-scoped state.**
The plan uses a flat key `"last_aoi_data"`. But Streamlit session state is per-browser-tab. If the app supports multiple threads (conversations) in one tab, the AOI from thread A could leak into thread B's dataset map. The risk register mentions scoping by thread_id but defers it. A developer implementing this might or might not add thread scoping, creating divergent implementations.

### Change 1b: Fetch Geometry in `render_dataset_map()` -- Missing Details

**Ambiguity 4: `ZenoClient` constructor requires `token` from `st.session_state.token`.**
The plan's code sample constructs `ZenoClient(base_url=API_BASE_URL, token=st.session_state.token)` inside `render_dataset_map()`. However, `render_dataset_map()` currently does NOT import or reference `st.session_state`, `API_BASE_URL`, or `ZenoClient`. These are used in `render_aoi_map()` and `render_stream()`, but the plan does not mention adding the necessary imports or ensuring `st.session_state.token` exists at that point. The imports are already at the top of utils.py (`from client import ZenoClient`, `import streamlit as st`), but `API_BASE_URL` is a module-level variable. A developer would need to verify all these are accessible -- the plan does not flag this as a consideration.

**Ambiguity 5: `aoi_data.get("source")` may be None.**
The plan calls `client.fetch_geometry(source=aoi_data.get("source"), src_id=aoi_data["src_id"])`. The `fetch_geometry` method signature is `def fetch_geometry(self, source: str, src_id: str)` -- it expects `source` as a string, not None. If `aoi_data` lacks a `"source"` key, this will construct a URL like `/api/geometry/None/{src_id}` which will 404 or error. The plan wraps this in try/except, so it will silently fail, but the plan does not acknowledge this specific failure mode or whether `source` is always present in the AOI dict.

**Ambiguity 6: The `fetch_geometry()` call adds network latency to every dataset map render.**
The plan acknowledges this in the risk register but does not specify whether the fetched geometry should be cached. The plan says "Session state caching (Change 1a) means subsequent renders reuse the cached AOI" -- but Change 1a caches `aoi_data` (the dict with `src_id`), NOT the geometry. So every call to `render_dataset_map()` with a src_id-only aoi_data will re-fetch geometry from the API. A developer might or might not cache the geometry in session state after fetching it. The plan does not specify.

### Change 1c: AOI Overlay Using Resolved Geometry

**Ambiguity 7: The plan's new GeoJson code uses `aoi_data.get("name", "Area of Interest")` for the popup.**
But the current code at line 220 uses hardcoded `"Area of Interest"` and `"AOI"` strings. The plan introduces `aoi_data.get("name", ...)` which is a behavior change. If `aoi_data["name"]` contains HTML or special characters, it could break the Popup's `parse_html=True`. The plan does not address input sanitization.

**Ambiguity 8: Two AOI overlays may render simultaneously.**
The plan states "The AOI-only map serves as a preview that appears first and is acceptable UX." But when both `aoi` and `dataset` arrive in the same update (which the plan acknowledges can happen when `update.get("aoi")` is checked), the user sees: (1) AOI-only map from `render_aoi_map()`, then (2) dataset map with AOI overlay from `render_dataset_map()`. This is two maps both showing the AOI. The plan explicitly accepts this but does not discuss whether this is confusing to users or if the first map should be suppressed.

## Phase 2: Fix Dataset Name and Sidebar Data (P1)

### Change 2a: Dataset Name Key

**Ambiguity 9: The plan says to change line 199 but does not verify `DatasetSelectionResult.model_dump()` output.**
The plan assumes `model_dump()` produces `"dataset_name"` as a key. While the Pydantic model has `dataset_name: str = Field(...)`, the `model_dump()` output depends on whether `by_alias` is used and whether there are aliases defined. The plan does not verify the actual serialized key name by checking the model definition. Looking at the code, `DatasetSelectionResult` inherits from `DatasetOption`. The plan should verify that no alias is set on this field. This is likely correct but unverified.

**Ambiguity 10: The fallback chain `dataset_data.get("dataset_name", dataset_data.get("data_layer", "Dataset Layer"))` is fragile.**
If a future developer adds a `data_layer` field to `DatasetSelectionResult`, the fallback will silently pick it up. The plan does not explain WHY `data_layer` might ever be present -- is it from a different code path? An older version of the model? The plan should state whether `data_layer` is a legacy key or if it is used by non-agent code paths (e.g., the sidebar).

### Change 2b: Fix Sidebar Hardcoded Data

**Ambiguity 11: The plan says to change `dataset_id: 0` to `dataset_id: 4` and `threshold=25` to `threshold=30`.**
But the sidebar also has DIST-ALERT with `dataset_id: 14`. The YAML shows DIST-ALERT as `dataset_id: 0`. Is the sidebar's DIST-ALERT entry also wrong? The plan only flags the TCL entry but does not audit the DIST-ALERT sidebar entry. Looking at the actual sidebar code: DIST-ALERT has `dataset_id: 14` but YAML shows `dataset_id: 0` for DIST-ALERT. This is a bug the plan misses entirely.

**Ambiguity 12: The sidebar tile URL for TCL has query parameter ordering that differs from the YAML.**
The sidebar URL is: `...{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=25&render_type=true_color`
The YAML URL is: `...{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color`
The sidebar URL has `start_year` and `end_year` BEFORE the threshold, while the YAML-based URL would have them appended AFTER. The plan says to fix the threshold from 25 to 30 but does not specify whether to also restructure the query parameter order to match what `pick_dataset.py` would produce. Two developers would produce different URLs.

**Ambiguity 13: The sidebar is test/debug UI -- does it even matter?**
The plan lists this as P2 priority, but does not clarify whether the sidebar is used in production or only for development. If it is dev-only, the wrong dataset_id and threshold are cosmetic issues. The plan should state the sidebar's role so a developer can prioritize correctly.

## Phase 3: Year Validation in `pick_dataset.py` (P1)

### Change 3a: Constants Placement

**Ambiguity 14: "Add constants near the top of the file or alongside existing dataset ID constants."**
The plan is ambiguous about WHERE to put the constants. The dataset ID constants are in `analytics_handler.py`, not in `pick_dataset.py`. The plan says to add year constants to `pick_dataset.py`, but a developer might reasonably put them in `analytics_handler.py` next to the other dataset constants. The plan should specify the exact file and location.

**Ambiguity 15: The year constants are TCL-specific. Should other datasets have similar constants?**
DIST-ALERT and Grasslands also have implicit year bounds (Grasslands uses `range(2000, 2023)` which silently clips). The plan only adds constants for TCL. A developer might ask: should we also extract `GRASSLANDS_MIN_YEAR = 2000` and `GRASSLANDS_MAX_YEAR = 2022`? The plan does not address whether this is in scope.

### Change 3b: Year Clamping Logic

**Ambiguity 16: The plan changes the behavior of out-of-range years.**
Currently, if `end_date.year` is outside `range(2001, 2025)`, the code falls through to hardcoded defaults: `start_year=2001&end_year=2024`. The plan's new logic clamps ANY year to bounds, so `end_date.year=2030` becomes `end_year=2024` and `start_date.year=1990` becomes `start_year=2001`. This is subtly different: the current fallthrough sets BOTH to full range, while the new clamping preserves the other year. For example, with `start_date=2020, end_date=2030`:
- Current: `start_year=2001&end_year=2024` (full range fallback)
- New: `start_year=2020&end_year=2024` (only end clamped)
This is a behavior change that may or may not be desired. The plan does not explicitly acknowledge this difference.

**Ambiguity 17: The `logger.info()` call uses structured logging kwargs.**
The plan shows `logger.info("TCL tile year params", start_year=start_year, ...)`. This assumes structlog-style keyword argument logging. If the logger is a standard Python logger, this would fail. The codebase uses structlog, so this is likely correct, but the plan should confirm by referencing the import pattern.

## Testing Strategy Ambiguities

**Ambiguity 18: New test directory `tests/frontend/` requires infrastructure that does not exist.**
The plan acknowledges this ("may need conftest.py with Streamlit session state mocks") but does not specify what the conftest should contain. Streamlit's `session_state` is notoriously hard to mock -- it is a `SessionState` object, not a plain dict. A developer would need to either:
- Use `unittest.mock.patch` on `streamlit.session_state` (fragile, may not work)
- Use `streamlit.testing.v1.AppTest` (Streamlit's experimental testing framework)
- Import and initialize a real Streamlit runtime (heavy)
The plan does not specify which approach, and two developers would choose differently.

**Ambiguity 19: Tests mock `folium_static` but the plan does not specify what to assert.**
Test 1 says "render_dataset_map calls fetch_geometry to resolve it" but does not specify how to verify the map was centered correctly. You cannot inspect a `folium.Map` object's center easily after creation (it is embedded in HTML). The test would need to either:
- Assert `fetch_geometry` was called with correct args (verifies the call, not the result)
- Parse the Folium HTML output (brittle)
- Mock `folium.Map` and assert constructor args (feasible but not specified)

**Ambiguity 20: Test Suite 2 extends `tests/tools/test_pick_dataset.py` but those tests call real LLM APIs.**
The existing `test_tile_url_contains_date` test calls `pick_dataset.ainvoke()` which triggers RAG retrieval and LLM calls. The plan's new tests (Tests 6-9) would also need real API keys. The plan does not specify whether the new tests should mock the LLM or use real APIs. The CI workflow note says tool tests "require real Google API key" -- but the plan does not flag this as a constraint for the new tests.

## Implementation Order Ambiguities

**Ambiguity 21: The plan says "Change 2a" should come first (dataset_name key fix) for immediate visibility.**
But Change 2a has zero effect on the blank map bug. A developer focused on the P0 fix might skip straight to Changes 1a-1c. The plan's ordering is reasonable but could confuse a developer who expects the implementation order to match priority order (P0 first, then P1, then P2). The plan lists the order as: 2a, 2b, 1a, 1b+1c, 3a+3b -- which interleaves priorities.

**Ambiguity 22: "Pre-implementation verification" assumes curl access to GFW tile service.**
The plan says to curl tiles at different zoom levels. This assumes the developer has outbound network access to `tiles.globalforestwatch.org`. In a sandboxed CI or restricted corporate environment, this may not work. The plan does not provide a fallback if the pre-verification step fails due to network restrictions.

## Missing Considerations

**Gap 1: The plan does not address `TREE_COVER_LOSS_BY_DRIVER_ID` (dataset_id=8).**
The `pick_dataset.py` code at line 96 has a branch for `TREE_COVER_LOSS_BY_DRIVER_ID` but the plan's year clamping only targets `TREE_COVER_LOSS_ID` (dataset_id=4). Does dataset_id=8 also use the GFW tile service? Does it have the same year bounds? The plan does not audit this related dataset.

**Gap 2: The plan does not address `zoom_start=5` as potentially too low or too high.**
The plan hardcodes `zoom_start = 5` when geometry is resolved. For a small city AOI, zoom 5 would be too far out. For Russia, zoom 5 might be too close. The existing code in `render_aoi_map()` also uses a fixed calculation based on bounds but the plan does not verify whether `render_dataset_map()` should use the same zoom calculation or just hardcode 5. The risk register mentions `fit_bounds` as a follow-up but does not explain why `zoom_start=5` was chosen over computing from geometry bounds.

**Gap 3: The plan does not address what happens when `aoi_data` has a `"geometry"` key AND a `"src_id"` key.**
Change 1b checks `"geometry" in aoi_data` first, then falls through to `src_id`. But what if a future code path provides both? Should the pre-existing geometry take precedence? The plan's if/elif structure implies yes, but does not explicitly state this design decision.

**Gap 4: The plan does not address the `style_function` lambda parameter.**
The current AOI overlay code (line 214) uses `lambda feature: {...}`. The plan's replacement also uses `lambda feature: {...}`. But `folium.GeoJson` passes a GeoJSON Feature dict to the style function. If the geometry is a raw Geometry (not a Feature), this lambda receives the geometry dict, not a Feature. The `feature` parameter would be the geometry itself. This might work in Folium (it wraps bare geometries into Features internally), but the plan does not verify this assumption.

**Gap 5: Error handling for `st.session_state.token` not being set.**
The plan's Change 1b creates a `ZenoClient` using `st.session_state.token`. If the user is not authenticated (token not in session state), this would raise a `KeyError`. The outer try/except catches it, but the plan does not explicitly note this as a handled failure case, which could confuse a developer debugging auth-related issues.
