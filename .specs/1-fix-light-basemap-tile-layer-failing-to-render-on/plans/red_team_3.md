# Codebase Validation Report: Master Plan

## Validation Summary

The master plan is largely accurate in its description of the codebase. Most file references, line numbers, function signatures, and behavioral claims are correct. However, several factual errors and risks were identified, primarily in the proposed unit tests.

---

## Verified Claims (Correct)

### File structure and locations
- `frontend/utils.py` exists and is the only file requiring modification. Confirmed.
- `render_aoi_map` starts at line 70. Confirmed.
- `render_dataset_map` starts at line 160. Confirmed.
- `render_stream` is at line 648. Confirmed.
- `API_BASE_URL` constant is at line 13-16. Plan says "around line 24" -- actually at line 13. Minor inaccuracy but does not affect implementation.

### Map creation code
- `render_aoi_map` line 105: `folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")`. Confirmed exact match.
- `render_dataset_map` lines 194-196: `m2 = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap")`. Confirmed exact match.
- `render_dataset_map` uses `folium.raster_layers.TileLayer` at line 200. Confirmed.
- `render_dataset_map` has `folium.LayerControl().add_to(m2)` at line 227. Confirmed.
- `render_aoi_map` has NO `LayerControl`. Confirmed.
- `folium_static` is used (not `st_folium`) with the "stalls the UI" comment. Confirmed at line 153.
- Dataset tile layer uses `overlay=True, control=True`. Confirmed at lines 204-205.

### Layer ordering
- In `render_dataset_map`: base tiles -> dataset TileLayer -> AOI GeoJson -> LayerControl. Confirmed.
- In `render_aoi_map`: base tiles -> AOI GeoJson -> subregion GeoJson -> no LayerControl. Confirmed.

### Dependencies
- `pyproject.toml` frontend group has `streamlit_folium==0.25.0`. Confirmed at line 68.
- `folium` is not directly listed; it is a transitive dep of `streamlit_folium`. Confirmed.
- Folium version in `uv.lock` is 0.17.0 (>= 0.12 requirement satisfied). Confirmed.

### `tiles=None` support in folium 0.17.0
- The `folium.Map.__init__` signature is `tiles: Union[str, TileLayer, None] = "OpenStreetMap"`. Line 247 of folium.py.
- When `tiles=None`, the `elif tiles:` guard at line 322 is `False`, so no default tile layer is added. Confirmed.

### `folium.raster_layers.TileLayer` constructor
- Accepts `tiles`, `attr`, `name`, `overlay`, `control`, `show` parameters. All confirmed in folium 0.17.0 at `/folium/raster_layers.py` lines 91-107.
- `show` parameter: `show: bool = True` (line 102). Confirmed.
- `overlay` parameter: `overlay: bool = False` (line 100). Confirmed -- default is already `False`, so explicitly passing `overlay=False` is redundant but harmless.

### `render_stream` data flow
- `"aoi"` key triggers `render_aoi_map` at line 693. Confirmed.
- `"dataset"` key triggers `render_dataset_map` at line 701. Confirmed.
- `"charts_data"` key triggers chart rendering at line 704. Confirmed.

---

## Factual Errors Found

### ERROR 1: Test code references `tl.options.get("show")` -- `show` is NOT in `options`

**Plan claims (Section 6.1, test `test_exactly_one_default_basemap`):**
```python
shown = [tl for tl in tile_layers if tl.options.get("show")]
```

**Codebase reality:**
In folium 0.17.0, `show` is stored as `self.show` on the `Layer` base class (file `folium/map.py` line 69), NOT in `self.options`. The `options` dict (created via `parse_options` in `raster_layers.py` lines 142-153) contains `min_zoom`, `max_zoom`, `attribution`, `subdomains`, etc. -- but NOT `show`, `overlay`, or `control`.

**Impact:** The test `test_exactly_one_default_basemap` will always find zero shown layers (`tl.options.get("show")` returns `None` for all layers) and will FAIL with `assert len(shown) == 1`.

**Fix:** Use `tl.show` instead of `tl.options.get("show")`.

### ERROR 2: Test code references `tl.options.get("overlay")` -- `overlay` is NOT in `options`

**Plan claims (Section 6.1, test `test_basemap_layers_are_base_not_overlay`):**
```python
assert tl.options.get("overlay") is False
```

**Codebase reality:**
`overlay` is stored as `self.overlay` on the `Layer` base class (`folium/map.py` line 67), NOT in `self.options`.

**Impact:** `tl.options.get("overlay")` returns `None`, and `None is False` evaluates to `False`, so `assert ... is False` will FAIL for every tile layer. All 3 assertions in the loop will fail.

**Fix:** Use `tl.overlay` instead of `tl.options.get("overlay")`.

### ERROR 3: `API_BASE_URL` location described as "around line 24"

**Plan claims (Section 4.1, Change 1):**
> Insert after the existing constants (around line 24, near `API_BASE_URL`).

**Codebase reality:**
`API_BASE_URL` is defined at lines 13-16. Line 24 falls inside the `generate_markdown` function body (which starts at line 21). The constant block should be inserted after line 16 (end of `API_BASE_URL` definition), before line 19 (the TODO comment).

**Impact:** Minor -- the implementer should place the constant after line 16, not "around line 24."

---

## Risks and Warnings

### WARNING 1: Test imports may fail -- `frontend` is not a Python package

**Plan claims (Section 6.1):**
```python
from frontend.utils import BASEMAP_CONFIGS, _create_base_map
```
> Run tests with `uv run pytest tests/frontend/ -v` from the project root (uv handles path resolution via the pyproject.toml package config).

**Codebase reality:**
- `frontend/` has NO `__init__.py` file.
- `pyproject.toml` hatch build config only packages `["src"]` (line 92).
- `frontend/` is NOT on the Python path by default.

The import `from frontend.utils import ...` requires either:
1. Adding `frontend/__init__.py` (not mentioned in the plan's deliverables beyond `tests/frontend/__init__.py`)
2. Adding `frontend` to the hatch packages list
3. Using `sys.path` manipulation in the test conftest
4. Running pytest with `PYTHONPATH=. uv run pytest ...`

The plan mentions creating `tests/frontend/__init__.py` but does NOT mention creating `frontend/__init__.py`. The import will fail without one of the above fixes.

**Impact:** All 8 tests will fail with `ModuleNotFoundError: No module named 'frontend'`.

### WARNING 2: `frontend/requirements.txt` is outdated vs `pyproject.toml`

**Plan claims (Section 4.3):**
> No changes to `frontend/requirements.txt` and `pyproject.toml`: No new dependencies needed.

**Codebase reality:**
`frontend/requirements.txt` lists `streamlit_folium==0.23.0` and `streamlit==1.40.1`, while `pyproject.toml` lists `streamlit_folium==0.25.0` and `streamlit==1.47.0`. These files are out of sync. The plan correctly references the `pyproject.toml` versions as authoritative, but the `frontend/requirements.txt` appears to be a stale artifact that could cause confusion if someone uses it directly (e.g., in a Docker build).

**Impact:** Not a bug in the plan, but worth noting. The recon document (`relevant_code.md`) incorrectly states `streamlit_folium==0.23.0` -- this is from the stale `requirements.txt`, not the actual resolved version.

### WARNING 3: `folium_static` rendering -- `st.subheader` placement for LayerControl

The plan says to add `folium.LayerControl().add_to(m)` in `render_aoi_map` "after the subregion rendering block, before the `st.subheader` / `folium_static` call, around line 149." The actual insertion point is between lines 147-149. This is correct and works fine. However, note that `folium_static` renders a static image/HTML of the map -- LayerControl interactivity depends on whether `folium_static` preserves JavaScript interactivity. The plan does not discuss this. In practice, `folium_static` renders an iframe with full Leaflet JS, so LayerControl should work.

---

## Items Verified as Not Reinventing Existing Utilities

- No existing basemap configuration or tile layer helper exists in the codebase. The `_create_base_map()` factory is genuinely new.
- No existing constants for tile provider URLs exist anywhere.
- The `folium.raster_layers.TileLayer` usage matches the existing pattern in `render_dataset_map` line 200.
- The `UPPER_SNAKE_CASE` naming for `BASEMAP_CONFIGS` follows the project's convention (matches `API_BASE_URL`, `RESULT_LIMIT`, etc.).

---

## Conclusion

The master plan is accurate in its core analysis and proposed changes to `frontend/utils.py`. The three factual errors are all in the test code (Section 6.1) and relate to incorrect assumptions about where folium stores `show` and `overlay` attributes. These are straightforward to fix by using direct attribute access (`tl.show`, `tl.overlay`) instead of `tl.options.get(...)`. The `frontend` import path issue is a more significant risk that could prevent all tests from running without additional setup steps.
