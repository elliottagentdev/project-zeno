# Red Team Audit: Requirements Coverage Analysis

## Auditor: Requirements Auditor (Red Team Agent 1)
## Target: `master_plan.md`
## Source: `PROMPT.md`

---

## 1. Requirements Coverage Matrix

| # | Requirement | Addressed? | Location in Plan | Testable? | Gaps/Ambiguities |
|---|-------------|-----------|-----------------|-----------|-----------------|
| JS1 | **Job Story:** Default basemap visible on map load for geographic context | Yes | Section 2 ("Replace `tiles="OpenStreetMap"` with `tiles=None`... Add explicit basemap TileLayer objects"), Section 4.2 ("Light shown" via `show=(i==0)`), Section 4.3 Change 3 (`_create_base_map` replaces broken call) | Yes -- Manual test T1/T2, Unit test `test_create_base_map_has_expected_providers` | No gap. The factory function with `show=(i==0)` ensures Light loads by default. |
| P1 | **Promise:** Functioning basemap visible immediately when any query result renders | Yes | Section 4.3 Change 3 (render_aoi_map) and Section 4.4 Change 4 (render_dataset_map) both use `_create_base_map()` | Partially -- Manual tests T1/T2 cover it, but no automated integration test verifies actual rendering | **Gap:** No automated test confirms the basemap actually renders visually. Unit tests only verify TileLayer objects exist in the map's children, not that tiles load. This is acknowledged in Section 6.2 but the manual tests are not enforceable in CI. |
| P2 | **Promise:** AOI boundary and data layers render on top of basemap and are not obscured | Yes | Section 4.2 ("Layer Rendering Order (Verified)") documents exact add order and explains Leaflet z-order behavior; Section 5.4 explains overlay vs base layer rendering | Partially -- Manual tests T7/T8 cover it; unit test `test_basemap_layers_are_base_not_overlay` verifies `overlay=False` | **Gap:** No automated test verifies the dataset tile layer is added AFTER basemaps. The plan relies on code review and manual testing to enforce add order. A test asserting children order in the map object would close this gap. |
| P3 | **Promise:** Users do not need to switch to Satellite as a workaround | Yes | Entire plan centers on replacing broken OSM tiles with working CartoDB tiles as default | Yes -- Manual test T1 directly validates this | No gap. |
| C1 | **Constraint:** No paid Mapbox API key -- use reliable free tile provider | Yes | Section 4.1 Change 1: uses CartoDB Positron (free, no key), CartoDB Dark (free, no key), ESRI World Imagery (free for non-commercial); Section 3 Risk R7 discusses ESRI terms | Yes -- Manual test T10 ("No API key required"), unit test `test_create_base_map_has_expected_providers` checks URLs | **Ambiguity:** Risk R7 notes ESRI World Imagery is "free for non-commercial and educational use" and suggests flagging for product review. The plan does not resolve whether WRI's use case definitively falls under non-commercial. If it does not, ESRI tiles would violate this constraint. However, the plan does provide alternatives (OpenTopoMap, Stamen Terrain) as fallbacks. |
| C2 | **Constraint:** Existing LayerControl UI for basemap switching (Light/Dark/Satellite) must remain user-accessible | Yes | Section 4.1 Change 2: all three basemaps added with `control=True`; Section 4.3 Change 3: adds `LayerControl` to `render_aoi_map`; Section 4.4 Change 4: existing `LayerControl` in `render_dataset_map` unchanged | Yes -- Manual tests T3-T6 cover switching; unit test `test_create_base_map_has_correct_tile_count` verifies 3 layers | **Minor gap:** The plan IMPROVES on the current state by adding LayerControl to `render_aoi_map` (which currently lacks it). The PROMPT.md says "should continue to be user-accessible" implying it already works. The plan correctly identifies this as failure mode F3 but does not call out that this is a scope expansion beyond the stated constraint. Not a problem, but worth noting. |
| C3 | **Constraint:** Must not touch dynamic dataset layer rendering logic | Yes | Section 4.3 "What NOT to Change": explicitly lists "Dataset tile layer logic (lines 200-206)" as untouched; Section 4.4 Change 4 only modifies the `folium.Map()` constructor call | Yes -- Code diff is scoped; unit tests do not import or test dataset logic | No gap. The plan is explicit about this boundary. |
| C4 | **Constraint:** Layer order: basemap (bottom) -> dataset tiles (middle) -> AOI outlines (top) | Yes | Section 4.2 "Layer Rendering Order (Verified)" documents exact order for both functions; Section 5.4 explains Leaflet z-order mechanics | Partially -- Manual tests T7/T8 cover visual verification | **Gap:** Same as P2. No automated test enforces layer ordering. The plan relies on the factory pattern (basemaps added first inside `_create_base_map`) and existing code structure (dataset tiles added after). A future refactor could break this invariant silently. |
| AC1 | Any query renders visible geographic basemap by default | Yes | Changes 3 and 4 ensure both `render_aoi_map` and `render_dataset_map` use `_create_base_map()` | Yes -- Manual T1/T2 | **Ambiguity:** "Any query" -- the plan modifies `render_aoi_map` and `render_dataset_map`. Are there other code paths that render maps? The plan does not audit whether other map-rendering functions exist in the codebase. If a third rendering path exists, it would not be fixed. |
| AC2 | Light basemap renders country outlines, terrain, and labels over the AOI | Yes | CartoDB Positron is the chosen Light provider (Section 4.1 Change 1), which includes country borders, labels, and terrain shading | Yes -- Manual T1 | **Ambiguity in AC wording:** "over the AOI" is ambiguous -- does it mean "above/on top of the AOI polygon" or "in the area of the AOI"? CartoDB Positron renders geographic features across the whole viewport. The plan interprets this as "visible in the map viewport where the AOI is displayed," which is reasonable. However, if the AC literally means the basemap should render ON TOP of the AOI polygon, that contradicts C4 (basemap at bottom). The plan correctly puts basemap at bottom. |
| AC3 | Satellite imagery option continues to work as it does now | Yes | ESRI World Imagery included in `BASEMAP_CONFIGS` (Section 4.1 Change 1); available via LayerControl | Yes -- Manual T5; unit test `test_create_base_map_has_expected_providers` checks for arcgisonline.com | No gap. |
| AC4 | No additional API keys or credentials needed | Yes | Section 4.1 uses only free, keyless tile providers; Risk R7 discusses terms | Yes -- Manual T10 | No gap. CartoDB and ESRI World Imagery do not require API keys. |
| AC5 | AOI boundary/polygon renders on top of all other layers | Yes | Section 4.2 documents AOI GeoJson added after basemaps and dataset tiles in both functions | Yes -- Manual T8 | Same gap as C4/P2: no automated enforcement of layer order. |
| AC6 | Layer order correct for all map renders | Yes | Section 4.2 documents order for both functions; Section 5.4 explains Leaflet mechanics | Partially | Same gap as C4/P2. |

---

## 2. Critical Findings

### 2.1 HIGH: No verification that only two map-rendering code paths exist

The plan modifies `render_aoi_map` and `render_dataset_map` in `frontend/utils.py`. AC1 says "any query renders a visible geographic basemap." The plan does not document a codebase audit confirming these are the ONLY two functions that create `folium.Map` objects. If there is a third map-rendering path (e.g., in another file, or a different function in utils.py), it would still use the broken `tiles="OpenStreetMap"` pattern.

**Recommendation:** The plan should include a grep for `folium.Map(` across the entire codebase and explicitly confirm that only two call sites exist.

### 2.2 MEDIUM: Layer ordering has no automated regression guard

The plan correctly identifies and documents the required layer order (basemap -> dataset -> AOI). However, the only verification is manual testing (T7, T8) and code review. The unit tests verify that basemaps are base layers (`overlay=False`) but do not verify that basemaps are added before dataset tiles in the map's children list.

A developer refactoring `render_dataset_map` could accidentally add dataset tiles before calling `_create_base_map()` (e.g., by restructuring the function), breaking the z-order invariant with no test failure.

**Recommendation:** Add a test that creates a map via `render_dataset_map` (or a mock equivalent) and asserts the order of children types.

### 2.3 MEDIUM: `show` kwarg compatibility not fully resolved

Section 9 "Implementation Pre-checks" item 2 says to "verify `folium.raster_layers.TileLayer` accepts `show` kwarg" and provides a fallback if it doesn't. However, the unit test `test_exactly_one_default_basemap` explicitly checks `tl.options.get("show")`, which would fail if the fallback path were taken. The plan provides two incompatible paths (use `show` kwarg vs. don't use it) without resolving which one applies.

**Recommendation:** Resolve this before implementation. Check the folium version in `uv.lock` now (during planning) rather than deferring to implementation time. If `show` is not supported, the tests need to be rewritten.

### 2.4 LOW: `frontend/index.html` explicitly out of scope but may have same bug

Section 4.3 "What NOT to Change" notes that `frontend/index.html` is a "separate standalone Leaflet client" that "uses its own OpenStreetMap URL directly in JavaScript." If that URL is also broken, users accessing the HTML client would hit the same issue. The plan explicitly defers this to a separate issue, which is reasonable scope management, but the PROMPT.md does not restrict the fix to the Streamlit frontend only.

**Recommendation:** Confirm whether `index.html` is affected and if so, file a follow-up issue.

### 2.5 LOW: AC2 wording ambiguity ("over the AOI")

AC2 says "Light basemap renders country outlines, terrain, and labels over the AOI." The phrase "over the AOI" could mean:
- (a) "in the geographic region of the AOI" (the plan's interpretation)
- (b) "visually on top of the AOI polygon layer"

Interpretation (b) would contradict C4 (basemap at bottom). The plan correctly uses interpretation (a), but a developer reading AC2 in isolation might be confused. This is a PROMPT.md issue, not a plan issue.

### 2.6 LOW: Test relies on internal folium API (`m._children`, `tl.options`, `tl.tile_name`)

The unit tests in Section 6.1 access `m._children`, `tl.options.get("show")`, and `tl.tile_name`. These are internal folium attributes (prefixed with `_` or undocumented). A folium version upgrade could change these internals and break the tests without any actual regression in behavior.

**Recommendation:** Document this fragility in a code comment. Consider adding `m._repr_html_()` based tests as a more stable alternative (the plan already uses this pattern in `test_create_base_map_has_no_default_osm_tiles`).

---

## 3. Completeness Assessment

### What the plan covers well:
- Root cause analysis is thorough and well-sourced
- Architecture decision rationale is clearly documented with tradeoff analysis
- Failure mode analysis (Section 3) is comprehensive
- Exact code changes with before/after diffs
- Edge cases are well-considered (retina displays, empty config, provider outages)
- "What NOT to Change" section prevents scope creep
- Rollback strategy is clear and simple
- Testing strategy includes both unit and manual tests

### What is missing or weak:
1. **Codebase audit for all `folium.Map(` call sites** -- critical for AC1 ("any query")
2. **Automated layer order verification** -- the most important invariant has no automated test
3. **Pre-check resolution** -- Section 9 defers critical compatibility checks to implementation time; these should be resolved during planning when possible
4. **Dark basemap justification vs. requirement** -- The PROMPT.md mentions "Light/Dark/Satellite" in the Context section but the actual constraints and acceptance criteria only mention Light and Satellite. Adding Dark is reasonable but technically exceeds the stated requirements. This is fine but should be acknowledged.

### Overall Coverage Score: **8.5/10**

The plan thoroughly addresses all stated requirements. The gaps identified are primarily around automated regression testing for layer ordering and a missing codebase-wide audit for additional map rendering paths. These are addressable without architectural changes to the plan.
