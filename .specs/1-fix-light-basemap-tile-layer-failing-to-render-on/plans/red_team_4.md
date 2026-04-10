# Red Team Report 4: Contradictions, Edge Cases & Failure Modes

## 1. CRITICAL: Unit Tests Will Fail Due to Wrong Attribute Access

**Severity: BLOCKER -- Tests will not pass as written.**

The master plan's unit tests access `tl.options.get("show")` and `tl.options.get("overlay")` to verify basemap configuration. However, in folium 0.17.0 (the actual resolved version in `uv.lock`):

- `show` is stored as `self.show` on the `Layer` base class (file: `folium/map.py`, line 69), NOT in `self.options`.
- `overlay` is stored as `self.overlay` on the `Layer` base class (line 68), NOT in `self.options`.
- `self.options` in `TileLayer` is populated by `parse_options()` which only includes `min_zoom`, `max_zoom`, `max_native_zoom`, `no_wrap`, `attribution`, `subdomains`, `detect_retina`, `tms`, `opacity`.

**Affected tests:**
- `test_exactly_one_default_basemap` -- `tl.options.get("show")` will return `None` for ALL tile layers, making `shown` an empty list. The assertion `len(shown) == 1` will fail.
- `test_basemap_layers_are_base_not_overlay` -- `tl.options.get("overlay")` will return `None`, not `False`. The assertion `is False` will fail because `None is not False`.

**Correct access patterns:**
- Use `tl.show` (boolean attribute on Layer)
- Use `tl.overlay` (boolean attribute on Layer)

This is a factual error in the plan that will cause test failures on every run.

## 2. Internal Contradiction: Section 2 vs Section 9.2 on `show` kwarg

Section 2 (Architecture Decision) states with confidence:
> "show=(i == 0) -- only the first basemap (Light/CartoDB Positron) is visible on init"

Section 9.2 (Implementation Pre-checks) hedges:
> "Verify `folium.raster_layers.TileLayer` accepts `show` kwarg: Check folium docs or source for the resolved version. If `show` is not supported, fall back..."

These contradict each other. The plan both commits to the `show` parameter as a design decision AND tells the implementer to verify it might not exist. The `show` parameter IS supported in folium 0.17.0 (confirmed in the actual source at `raster_layers.py` line 102), so the pre-check is unnecessary noise that undermines confidence in the plan. An implementer reading Section 9.2 might waste time investigating a non-issue or, worse, implement the fallback path unnecessarily.

## 3. Ordering Dependency: LayerControl Placement in `render_aoi_map`

The plan says to add `folium.LayerControl().add_to(m)` "after the subregion rendering block, before the `st.subheader` / `folium_static` call, around line 149."

However, the subregion rendering block (lines 122-147) contains a `try/except` that catches `Exception` and calls `st.warning`. If subregion rendering partially fails (e.g., `client.fetch_geometry` succeeds for some subregions but throws for one), execution continues past the except block. The LayerControl would still be added, but with an incomplete set of layers. This is technically correct behavior, but the plan does not acknowledge this partial-failure scenario.

More critically: the folium docs for `LayerControl` (line 141 of `folium/map.py`) explicitly state: "The LayerControl should be added last to the map. Otherwise, the LayerControl and/or the controlled layers may not appear." The plan places LayerControl correctly in the happy path, but does NOT verify that no code path adds layers AFTER the LayerControl. If future code adds a layer after `LayerControl().add_to(m)`, it will silently break the control. The plan should note this constraint for maintainability.

## 4. Edge Case: `render_aoi_map` Called with `geojson_data=None`

Looking at the actual code flow in `render_aoi_map` (line 105):
```python
m = folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")
```

After the proposed change to `_create_base_map(center=center, zoom_start=5)`, the map is created with `tiles=None`. If `geojson_data` is falsy (None, empty dict), no GeoJson is added. The map renders with basemap tiles only. This is fine.

But consider: if `aoi_data` itself is malformed (missing "geometry" key), the code at line 75-89 falls through to `center = [0, 0]`. The factory creates a map centered at [0, 0] (Gulf of Guinea, off the coast of Africa). With `tiles="OpenStreetMap"` this showed a blank white map (the bug). With the fix, it will show CartoDB Positron tiles centered on [0, 0]. This is an improvement but may confuse users -- they see a map of the Gulf of Guinea with no AOI overlay. The plan does not discuss this edge case.

## 5. Edge Case: ESRI Tile URL Uses `{y}/{x}` Not `{x}/{y}`

The ESRI World Imagery URL in the plan is:
```
https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}
```

Note the `{y}/{x}` order, which is correct for ESRI's REST API (row/column). However, the CartoDB URLs use `{z}/{x}/{y}` (standard Leaflet convention). This inconsistency is NOT a bug -- ESRI genuinely uses a different order -- but a developer unfamiliar with tile URL conventions might "fix" it to match the CartoDB pattern, breaking Satellite tiles. The plan should include a comment in the `BASEMAP_CONFIGS` noting that ESRI uses `{z}/{y}/{x}` intentionally.

## 6. Edge Case: `{s}` Subdomain in CartoDB URLs vs ESRI

The CartoDB URLs use `{s}` for subdomain load balancing:
```
https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png
```

The ESRI URL does NOT use `{s}`:
```
https://server.arcgisonline.com/ArcGIS/rest/...
```

Leaflet's default `subdomains` is `"abc"`, meaning it cycles through `a.basemaps.cartocdn.com`, `b.basemaps.cartocdn.com`, `c.basemaps.cartocdn.com`. This works for CartoDB. But for the ESRI URL, `{s}` is absent, so the default subdomain setting is harmless (unused). However, the plan does not specify whether to pass `subdomains` explicitly for ESRI or rely on the default. This is a non-issue in practice but represents an implicit assumption.

## 7. Failure Mode: Network-Level Tile Blocking (Corporate/Government Firewalls)

The plan identifies "both basemap providers down simultaneously" as an edge case (Section 5.2) but dismisses it as "extremely rare." A more realistic failure mode is deployment behind a corporate or government firewall that blocks CDN domains. Both `basemaps.cartocdn.com` and `server.arcgisonline.com` could be blocked by the same network policy. Since Zeno is used by WRI (a global NGO operating in many countries), this is not hypothetical.

The plan provides NO fallback for complete tile provider unavailability. The user sees a blank map with GeoJson overlays but no geographic context -- essentially the same broken state as the current bug, just for a different reason. A minimal mitigation would be to document this failure mode and suggest that deployers can customize `BASEMAP_CONFIGS` to use internally-hosted tile servers.

## 8. Failure Mode: `folium_static` vs `st_folium` Rendering Differences

The plan correctly notes (Section 4.3) not to switch from `folium_static` to `st_folium`. However, it does not discuss a subtle interaction: `folium_static` renders the map as a static PNG-like image (via `_repr_html_()` and iframe embedding). With `folium_static`, the `LayerControl` is visible but may not be interactive in all Streamlit deployment modes. Specifically:

- `folium_static` renders maps as static HTML in an iframe. LayerControl IS interactive within the iframe.
- But if the iframe height is constrained (the plan uses `height=400`), the LayerControl dropdown might overflow the iframe boundary and be clipped.

The plan adds three basemap options plus existing dataset layers. The LayerControl dropdown is now taller. With `height=400`, there is a risk the expanded LayerControl is clipped. This is a visual regression the manual test checklist should catch, but the plan does not identify it as a risk.

## 9. Contradiction: "Zero New Dependencies" Claim vs Test Requirements

Section 10 states: "Zero new dependencies."

Section 6.1 states tests should be run with: `uv run pytest tests/frontend/ -v`

The project currently has zero frontend tests (acknowledged in Section 6). The test file imports `from frontend.utils import BASEMAP_CONFIGS, _create_base_map`. For this import to work, `frontend/` must be on `sys.path` or configured as a package in `pyproject.toml`.

The plan says "uv handles path resolution via the pyproject.toml package config" but does not verify that `frontend/` is actually configured as a package in `pyproject.toml`. If it is NOT (which is common for Streamlit apps that are run directly, not installed as packages), the import will fail with `ModuleNotFoundError: No module named 'frontend'`. The plan should verify the `pyproject.toml` package configuration or provide a `conftest.py` that adds `frontend/` to `sys.path`.

Additionally, the test imports `from frontend.utils import _create_base_map` -- a function prefixed with `_` (private). While Python does not enforce access control, this is a code smell that the plan should acknowledge. If the function is meant to be tested, it arguably should not be private.

## 10. Edge Case: Concurrent Map Renders in Streamlit

Streamlit re-renders the entire app on every interaction. If a user interacts with a widget while a map is rendering, Streamlit may call `render_aoi_map` or `render_dataset_map` concurrently (in different threads if using Streamlit's newer threading model). The `_create_base_map` factory is stateless and reads from a module-level constant (`BASEMAP_CONFIGS`), so this is thread-safe. However, if a future developer makes `BASEMAP_CONFIGS` mutable (e.g., dynamically adding providers based on user preferences), this could introduce a race condition. The plan uses a plain list, not a tuple or `frozenset`. Using a tuple for `BASEMAP_CONFIGS` would signal immutability and prevent accidental mutation.

## 11. Security Concern: HTML Injection via Attribution Strings

The `attr` values in `BASEMAP_CONFIGS` contain raw HTML:
```python
'&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors ...'
```

These strings are passed directly to `folium.raster_layers.TileLayer(attr=...)` which renders them as HTML in the map attribution. Since these are hardcoded constants (not user input), there is no XSS risk. However, if a future developer makes `BASEMAP_CONFIGS` configurable via environment variables or a config file, the HTML attribution strings become an injection vector. The plan should note this as a maintenance consideration: attribution values must be treated as trusted HTML.

## 12. Missing Test: `_create_base_map` with `tiles=None` Interaction

The test `test_create_base_map_has_no_default_osm_tiles` checks for `"tile.openstreetmap.org"` in the rendered HTML. This is a good negative test. However, it does not verify that `tiles=None` was actually passed to the `folium.Map` constructor. If a future folium version changes the default tile behavior (e.g., `tiles=None` adds a different default), the test would not catch it. A more robust test would verify the map has exactly `len(BASEMAP_CONFIGS)` tile layers and no extras.

Wait -- `test_create_base_map_has_correct_tile_count` already does this. But it only checks `isinstance(child, folium.raster_layers.TileLayer)`. If folium adds a default tile layer of a different type (e.g., `xyzservices.TileProvider` wrapped in a different class), the test would miss it. This is a minor concern but worth noting.

## 13. Edge Case: `{r}` Retina Token Behavior

The plan states (Section 4.1, String splitting note): "The `{r}` token in CartoDB URLs handles retina/HiDPI tile requests."

In Leaflet, the `{r}` token is replaced with `@2x` on retina displays when `detect_retina` is enabled, or with an empty string otherwise. The plan does NOT set `detect_retina=True` in the TileLayer constructor. This means `{r}` will be replaced with an empty string on ALL displays, producing URLs like:
```
https://a.basemaps.cartocdn.com/light_all/5/10/12.png
```

This is correct behavior -- the tiles will load fine. But the plan's comment about `{r}` "automatically serving @2x retina tiles" is misleading. Without `detect_retina=True`, retina detection does not happen. The `{r}` token is present in the URL template but will always resolve to empty string. The tiles will work but will not be retina-optimized. This is not a bug but the plan's documentation is incorrect about the behavior.

## Summary of Findings by Severity

| # | Finding | Severity |
|---|---------|----------|
| 1 | Tests use `tl.options.get("show")` and `tl.options.get("overlay")` but these attributes live on `tl.show` and `tl.overlay` directly | **BLOCKER** |
| 9 | Test imports may fail if `frontend/` is not configured as a Python package | **HIGH** |
| 2 | Contradiction between Section 2 (commits to `show`) and Section 9.2 (says verify it exists) | MEDIUM |
| 7 | No fallback for complete tile provider unavailability behind firewalls | MEDIUM |
| 13 | `{r}` retina token documentation is incorrect -- `detect_retina` is not enabled | MEDIUM |
| 3 | LayerControl placement assumes no future code adds layers after it | LOW |
| 4 | Malformed `aoi_data` produces map centered on [0,0] with no explanation | LOW |
| 5 | ESRI `{y}/{x}` order could be "fixed" by unaware developers | LOW |
| 8 | LayerControl dropdown may be clipped in 400px iframe | LOW |
| 10 | `BASEMAP_CONFIGS` is a mutable list, not a tuple | LOW |
| 11 | HTML in attribution strings is safe now but could become injection vector | LOW |
| 6 | ESRI subdomain handling is implicit but harmless | INFORMATIONAL |
| 12 | Tile layer type check could miss exotic future layer types | INFORMATIONAL |
