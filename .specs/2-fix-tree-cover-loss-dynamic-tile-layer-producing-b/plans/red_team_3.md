# Codebase Validation Report: Master Plan Factual Accuracy

## Methodology

Every factual claim in the master plan was verified against the actual codebase at `/mnt/e/agentdev/projects/project-zeno/`. File paths, line numbers, function signatures, data structures, and behavioral descriptions were cross-referenced with source code.

---

## VERIFIED CORRECT

### Root Cause Analysis

1. **AOI geometry not passed to dataset map** -- CONFIRMED. `render_stream()` at line 698-700 passes `update.get("aoi") or aoi_data` to `render_dataset_map()`. The `aoi` dict from agent state (set at `pick_aoi.py` line 554) contains `src_id`, `name`, `source`, `subtype` -- NO `geometry` key. `render_dataset_map()` checks `"geometry" in aoi_data` at line 179, which is indeed `False`. Map defaults to `center=[0,0]`, `zoom_start=2`.

2. **`render_aoi_map()` fetches geometry but does not share it** -- CONFIRMED. Lines 81-87 of `utils.py` show `client.fetch_geometry(source=..., src_id=...)` call. The result is used only within `render_aoi_map()` scope.

3. **Dual map rendering** -- CONFIRMED. `render_aoi_map()` creates `m` (line 105), `render_dataset_map()` creates `m2` (line 194). These are independent `folium.Map` instances rendered separately via `folium_static()`.

4. **Dataset name mismatch** -- CONFIRMED. Line 199: `dataset_data.get("data_layer", "Dataset Layer")`. `DatasetSelectionResult` (pick_dataset.py line 114-145) has field `dataset_name`, not `data_layer`. The `model_dump()` output will have `"dataset_name"` key. The map title always falls through to "Dataset Layer".

5. **Sidebar hardcoded data issues** -- CONFIRMED. Line 783: `"dataset_id": 0` (should be 4 per YAML line 580). Line 786: URL contains `tree_cover_density_threshold=25` while YAML line 588 has `threshold=30`.

### Code Structure Claims

6. **`render_dataset_map()` function signature** -- CONFIRMED. Line 160: `def render_dataset_map(dataset_data, aoi_data=None)`.

7. **`render_stream()` location and structure** -- CONFIRMED. Function starts at line 648. AOI handling at lines 685-693, dataset handling at lines 696-701. The plan's "around lines 684-701" is accurate.

8. **`DatasetSelectionResult` model** -- CONFIRMED. Lines 114-145 of `pick_dataset.py`. Inherits from `DatasetOption`, has `tile_url`, `dataset_name`, `analytics_api_endpoint`, etc.

9. **TCL tile URL construction** -- CONFIRMED. Lines 304-312 of `pick_dataset.py` match the plan's "Current" code block exactly.

10. **Dataset ID constants are dynamically derived** -- CONFIRMED. `analytics_handler.py` lines 85-110: constants like `DIST_ALERT_ID`, `TREE_COVER_LOSS_ID` are derived from YAML via list comprehension, not hardcoded integers.

11. **`ZenoClient.fetch_geometry()` signature** -- CONFIRMED. `client.py` line 107: `def fetch_geometry(self, source: str, src_id: str)`.

12. **TCL tile URL in YAML** -- CONFIRMED. Line 588 of `analytics_datasets.yml`: `https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color`.

13. **No existing `tests/frontend/` directory** -- CONFIRMED. Directory does not exist.

14. **`tests/tools/test_pick_dataset.py` exists** -- CONFIRMED at `/mnt/e/agentdev/projects/project-zeno/tests/tools/test_pick_dataset.py`.

15. **Import of `ZenoClient` and `API_BASE_URL` in utils.py** -- CONFIRMED. Line 9: `from client import ZenoClient`, lines 13-16: `API_BASE_URL` defined.

16. **Existing `shape` import** -- CONFIRMED. Line 10: `from shapely.geometry import shape`.

---

## FACTUAL ERRORS

### Error 1: Sidebar DIST-ALERT dataset_id Incorrectly Described

**Plan claims (line 205):** "Change `dataset_id: 0` to `dataset_id: 4` (TCL is dataset 4, not DIST-ALERT which is 0)"

**Codebase reality:** The sidebar DIST-ALERT entry at line 794 has `"dataset_id": 14`, NOT `0`. The plan's parenthetical "(not DIST-ALERT which is 0)" is correct about DIST-ALERT being 0 in the YAML, but the plan does NOT flag that the sidebar DIST-ALERT entry also has the wrong ID (`14` instead of `0`). This is a missed bug.

**Impact:** Low -- the plan correctly identifies the TCL sidebar ID needs fixing (0 -> 4), but misses the opportunity to also fix the DIST-ALERT sidebar ID (14 -> 0). This is an omission rather than a factual error in the fix itself.

### Error 2: Plan References Line Numbers That Are Approximate

**Plan claims:** `render_dataset_map()` at "lines 175-191" for AOI handling, "line 199" for dataset name, "lines 209-224" for AOI overlay.

**Codebase reality:** These are all accurate to within 0-2 lines. The AOI check is at line 179, dataset name at line 199, AOI overlay at lines 209-224. This is not an error per se, but the plan should note these are approximate.

### Error 3: Plan's Change 1c Popup/Tooltip Text Differs From Existing Code

**Plan proposes (Change 1c):**
```python
popup=folium.Popup(
    aoi_data.get("name", "Area of Interest"),
    parse_html=True,
),
tooltip=aoi_data.get("name", "AOI"),
```

**Existing code (lines 220-221):**
```python
popup=folium.Popup("Area of Interest", parse_html=True),
tooltip="AOI",
```

**Issue:** The plan introduces a behavioral change (dynamic popup/tooltip from `aoi_data["name"]`) that is presented as a simple "use resolved geometry" refactor. This is a feature addition bundled into a bug fix. It is minor but should be explicitly called out as a change in behavior, not silently introduced.

---

## POTENTIAL ISSUES AND RISKS NOT ADDRESSED

### Issue 1: `fetch_geometry` Parameter `source` May Be None

**Plan proposes:** `client.fetch_geometry(source=aoi_data.get("source"), src_id=aoi_data["src_id"])`.

**Risk:** The sidebar AOI options (lines 752-775) do NOT have a `"source"` key. For example, the "Odisha" entry has `gadm_id`, `src_id`, `name`, `subtype` -- no `source`. If a user selects an AOI from the sidebar and then the dataset map tries to fetch geometry, `aoi_data.get("source")` returns `None`. The `fetch_geometry` signature requires `source: str`. This would raise a TypeError or produce an API error.

**Mitigation:** The plan wraps this in `try/except Exception`, so it would gracefully fall back. But this means sidebar-selected AOIs will never get geometry resolution, always rendering at global zoom. The plan does not acknowledge this limitation.

### Issue 2: `st.session_state.token` May Not Exist

**Plan proposes (Change 1b):** Creating `ZenoClient(base_url=API_BASE_URL, token=st.session_state.token)` inside `render_dataset_map()`.

**Risk:** If `st.session_state.token` is not set (e.g., in unauthenticated flows or test scenarios), this will raise an `AttributeError`. The existing `render_aoi_map()` at line 82 has the same pattern and is already wrapped in a top-level try/except, so this is consistent with existing risk, but the plan does not mention it.

### Issue 3: Plan Does Not Account for `LAND_COVER_CHANGE_ID` Import

**Plan proposes (Change 3a-3b):** Adding constants `TCL_TILE_MIN_YEAR`, `TCL_TILE_MAX_YEAR`, `TCL_TILE_MAX_START_YEAR` to `pick_dataset.py`.

**Observation:** The existing imports in `pick_dataset.py` (line 17-21) import from `analytics_handler.py`:
```python
from src.agent.tools.data_handlers.analytics_handler import (
    DIST_ALERT_ID,
    GRASSLANDS_ID,
    LAND_COVER_CHANGE_ID,
    TREE_COVER_LOSS_ID,
)
```
The plan proposes adding new constants directly in `pick_dataset.py`, which is fine but breaks the convention of dataset-related constants living in `analytics_handler.py`. This is a minor style inconsistency, not a bug.

### Issue 4: Test Suite References Non-Existent Test Infrastructure

**Plan claims (Test Suite 1):** "This is a new test directory (`tests/frontend/`). No frontend tests currently exist in the codebase."

**Confirmed:** The directory does not exist. However, the plan understates the setup needed. The frontend code imports from `client` (line 9) using a bare module name, not `from frontend.client` or `from src.frontend.client`. This means the test file will need special `sys.path` manipulation or a `conftest.py` that adds the `frontend/` directory to the path. The existing test infrastructure in `tests/conftest.py` is set up for `src/` imports, not `frontend/` imports.

---

## SUMMARY

| Category | Count |
|----------|-------|
| Claims verified correct | 16 |
| Factual errors | 3 (1 meaningful, 2 minor) |
| Unaddressed risks | 4 |

**Overall assessment:** The plan is factually accurate on all critical claims about root cause, code structure, and proposed fixes. The primary factual gap is the missed DIST-ALERT sidebar ID bug (14 should be 0). The proposed code changes are sound and correctly mirror existing patterns. The main risks are around edge cases (sidebar AOIs without `source`, unauthenticated sessions) that are mitigated by existing try/except patterns but should be documented.
