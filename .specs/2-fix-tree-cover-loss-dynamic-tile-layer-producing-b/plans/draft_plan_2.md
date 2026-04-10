# Draft Plan 2: Clean Architecture Lens

## Root Cause Analysis

The Tree Cover Loss (TCL) tile layer renders blank because of multiple compounding issues that stem from a lack of clear separation of concerns in both the tile URL construction pipeline and the frontend map rendering pipeline. The investigation reveals:

### Primary Root Cause: AOI Geometry Not Passed to Dataset Map

In `frontend/utils.py`, `render_stream()` (line 696-701) passes `aoi_data` to `render_dataset_map()`, but this `aoi_data` is the raw agent state dict containing `src_id`, `name`, `source`, etc. -- it does NOT contain a `"geometry"` key. The `render_dataset_map()` function checks for `"geometry" in aoi_data` (line 179), which evaluates to `False`. This means:

1. The map defaults to `center=[0, 0]` with `zoom_start=2` (global view)
2. At zoom level 2, TCL tiles (30m resolution data) produce transparent/empty PNG tiles because the data is too fine-grained to be visible at that scale
3. Grasslands works because its colormap-based rendering is visible even at low zoom levels
4. DIST-ALERT works because disturbance alert tiles use a different rendering pipeline on the GFW tile server that produces visible tiles at lower zooms

The geometry IS fetched inside `render_aoi_map()` via `client.fetch_geometry()` but is not returned or shared with `render_dataset_map()`.

### Secondary Issue: Dual Map Rendering

`render_aoi_map()` and `render_dataset_map()` create independent `folium.Map` instances. The user sees two separate maps instead of a single map with the correct layer order (basemap -> dataset tiles -> AOI outline). This violates the acceptance criteria.

### Tertiary Issue: Dataset Name Mismatch

`render_dataset_map()` uses `dataset_data.get("data_layer", "Dataset Layer")` (line 199) but `DatasetSelectionResult` serializes to have a `"dataset_name"` key, not `"data_layer"`. The layer always shows as "Dataset Layer".

## Architectural Approach: Introduce a TileURLBuilder Strategy and Unified Map Renderer

Rather than patching the existing monolithic if/elif chain and scattered rendering logic, this plan introduces proper separation of concerns through two key abstractions:

1. **TileURLBuilder strategy pattern** -- Each dataset type gets its own URL builder, replacing the if/elif chain in `pick_dataset.py`
2. **Unified map rendering pipeline** -- A single function that composes all layers (basemap, dataset tiles, AOI) onto one map

## Detailed File Changes

### Change 1: Introduce `TileURLBuilder` in `src/agent/tools/tile_url.py` (NEW FILE)

Create a new module that encapsulates tile URL construction logic, currently scattered across `pick_dataset.py` lines 283-312.

```python
"""
Tile URL construction strategies for different dataset types.

Each dataset type has its own URL builder that knows how to parameterize
the base tile URL template from analytics_datasets.yml.
"""

from abc import ABC, abstractmethod
from datetime import date
from typing import Optional

from src.shared.config import SharedSettings
from src.shared.logging_config import get_logger

logger = get_logger(__name__)


class TileURLBuilder(ABC):
    """Abstract base for dataset-specific tile URL construction."""

    @abstractmethod
    def build(
        self,
        base_url: str,
        start_date: date,
        end_date: date,
    ) -> str:
        """Build the final tile URL from base template and date range."""
        pass

    def _resolve_base_url(self, base_url: str) -> str:
        """Prefix relative URLs with eoAPI base URL."""
        if not base_url.startswith("http"):
            return SharedSettings.eoapi_base_url + base_url
        return base_url


class DistAlertURLBuilder(TileURLBuilder):
    def build(self, base_url, start_date, end_date):
        url = self._resolve_base_url(base_url)
        return f"{url}&start_date={start_date}&end_date={end_date}"


class YearFormatURLBuilder(TileURLBuilder):
    """For datasets using {year} path template (Grasslands, Land Cover Change)."""

    def __init__(self, valid_range: range, fallback_year: str = "2022"):
        self.valid_range = valid_range
        self.fallback_year = fallback_year

    def build(self, base_url, start_date, end_date):
        url = self._resolve_base_url(base_url)
        year = (
            end_date.year
            if end_date.year in self.valid_range
            else self.fallback_year
        )
        return url.format(year=year)


class TreeCoverLossURLBuilder(TileURLBuilder):
    """For TCL dataset with start_year/end_year query params."""

    MAX_TILE_START_YEAR = 2023  # GFW tile service constraint

    def build(self, base_url, start_date, end_date):
        url = self._resolve_base_url(base_url)
        if end_date.year in range(2001, 2025):
            tile_start_year = min(
                start_date.year, self.MAX_TILE_START_YEAR
            )
            return f"{url}&start_year={tile_start_year}&end_year={end_date.year}"
        return f"{url}&start_year=2001&end_year=2024"


class PassthroughURLBuilder(TileURLBuilder):
    """For datasets that need no date parameterization."""

    def build(self, base_url, start_date, end_date):
        return self._resolve_base_url(base_url)
```

Plus a registry function:

```python
def get_url_builder(dataset_id: int) -> TileURLBuilder:
    """Return the appropriate URL builder for a dataset ID."""
    from src.agent.tools.data_handlers.analytics_handler import (
        DIST_ALERT_ID,
        GRASSLANDS_ID,
        LAND_COVER_CHANGE_ID,
        TREE_COVER_LOSS_ID,
    )

    builders = {
        DIST_ALERT_ID: DistAlertURLBuilder(),
        GRASSLANDS_ID: YearFormatURLBuilder(range(2000, 2023)),
        LAND_COVER_CHANGE_ID: YearFormatURLBuilder(range(2000, 2023)),
        TREE_COVER_LOSS_ID: TreeCoverLossURLBuilder(),
    }
    return builders.get(dataset_id, PassthroughURLBuilder())
```

### Change 2: Refactor `pick_dataset.py` to Use TileURLBuilder

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pick_dataset.py`

Replace lines 283-312 (the if/elif chain) with:

```python
from src.agent.tools.tile_url import get_url_builder

# ... inside pick_dataset() function, after line 282 ...

start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

builder = get_url_builder(selection_result.dataset_id)
selection_result.tile_url = builder.build(
    selection_result.tile_url, start_date, end_date
)
```

This replaces ~30 lines of branching with 3 lines. The branching logic moves to the strategy objects where it can be tested independently.

**Remove imports** that are no longer needed in `pick_dataset.py`:
- `DIST_ALERT_ID`, `GRASSLANDS_ID`, `LAND_COVER_CHANGE_ID`, `TREE_COVER_LOSS_ID` (only if not used elsewhere in the file -- check first; they are likely used in `analytics_handler.py` import only)

Actually, these constants ARE used in `analytics_handler.py` and defined there, so `pick_dataset.py` already imports them. The imports can stay since the `tile_url.py` module will import them too. But the direct usage in `pick_dataset.py` is no longer needed once the if/elif is replaced.

### Change 3: Unified Map Rendering in `frontend/utils.py`

This is the critical fix. The current architecture has two problems:
1. Two separate maps are rendered (AOI map + dataset map)
2. The AOI geometry is fetched in `render_aoi_map()` but not shared with `render_dataset_map()`

**New function: `render_unified_map()`**

Add a new function in `frontend/utils.py` that replaces the separate `render_aoi_map()` and `render_dataset_map()` calls when both AOI and dataset data are available:

```python
def render_unified_map(dataset_data, aoi_data=None, subregion_data=None):
    """
    Render a single map with correct layer order:
    basemap (bottom) -> dataset tiles (middle) -> AOI outline (top).

    This replaces the separate render_aoi_map + render_dataset_map
    pattern to ensure all layers are on a single map.
    """
    try:
        tile_url = dataset_data.get("tile_url")
        if not tile_url:
            st.warning("No tile_url found in dataset")
            return

        # Fetch AOI geometry if we have aoi_data with src_id
        geojson_data = None
        center = [0, 0]
        zoom_start = 2

        if aoi_data and isinstance(aoi_data, dict):
            src_id = aoi_data.get("src_id")
            if src_id:
                try:
                    client = ZenoClient(
                        base_url=API_BASE_URL,
                        token=st.session_state.token,
                    )
                    geom_response = client.fetch_geometry(
                        source=aoi_data.get("source"),
                        src_id=src_id,
                    )
                    geojson_data = geom_response.get("geometry")
                except Exception as e:
                    st.warning(
                        f"Could not fetch AOI geometry: {str(e)}"
                    )

            # Also check if geometry is directly in aoi_data
            if not geojson_data and "geometry" in aoi_data:
                geojson_data = aoi_data["geometry"]

        # Calculate center from geometry
        if geojson_data and isinstance(geojson_data, dict):
            try:
                geom = shape(geojson_data)
                minx, miny, maxx, maxy = geom.bounds
                center = [(miny + maxy) / 2, (minx + maxx) / 2]
                zoom_start = 5
            except (ValueError, AttributeError, TypeError):
                pass

        # Layer 1: Basemap
        m = folium.Map(
            location=center,
            zoom_start=zoom_start,
            tiles="OpenStreetMap",
        )

        # Layer 2: Dataset tile layer
        dataset_name = dataset_data.get(
            "dataset_name", "Dataset Layer"
        )
        folium.raster_layers.TileLayer(
            tiles=tile_url,
            attr="Dataset Tiles",
            name=dataset_name,
            overlay=True,
            control=True,
        ).add_to(m)

        # Layer 3: AOI outline (top)
        if geojson_data:
            folium.GeoJson(
                geojson_data,
                style_function=lambda feature: {
                    "fillColor": "blue",
                    "color": "blue",
                    "weight": 2,
                    "fillOpacity": 0.1,
                },
                popup=folium.Popup(
                    aoi_data.get("name", "AOI"), parse_html=True
                ),
                tooltip=aoi_data.get("name", "AOI"),
            ).add_to(m)

        # Layer 3b: Subregions (if any)
        if subregion_data and isinstance(subregion_data, list):
            try:
                client = ZenoClient(
                    base_url=API_BASE_URL,
                    token=st.session_state.token,
                )
                for subregion in subregion_data:
                    if isinstance(subregion, dict):
                        sub_geojson = client.fetch_geometry(
                            source=subregion.get("source"),
                            src_id=subregion.get("src_id"),
                        ).get("geometry")
                        if sub_geojson:
                            folium.GeoJson(
                                sub_geojson,
                                style_function=lambda f: {
                                    "fillColor": "red",
                                    "color": "red",
                                    "weight": 2,
                                    "fillOpacity": 0.2,
                                },
                                tooltip=subregion.get(
                                    "name", "Subregion"
                                ),
                            ).add_to(m)
            except Exception as e:
                st.warning(
                    f"Could not render subregions: {str(e)}"
                )

        folium.LayerControl().add_to(m)

        st.subheader(f"Map: {dataset_name}")
        folium_static(m, width=700, height=400)

        # Dataset info expander (preserve existing behavior)
        with st.expander("Dataset Information"):
            dataset_info = {
                "Dataset ID": dataset_data.get("dataset_id", "N/A"),
                "Dataset Name": dataset_data.get(
                    "dataset_name", "N/A"
                ),
                "Source": dataset_data.get("source", "N/A"),
                "Context Layer": dataset_data.get(
                    "context_layer", "N/A"
                ),
                "Tile URL": dataset_data.get("tile_url", "N/A"),
            }
            for key, value in dataset_info.items():
                if value != "N/A":
                    st.write(f"**{key}:** {value}")

    except Exception as e:
        st.error(f"Error rendering dataset map: {str(e)}")
        st.json(dataset_data)
```

### Change 4: Update `render_stream()` in `frontend/utils.py`

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`, lines 684-701

Replace the current rendering logic:

```python
# BEFORE (current):
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
# AFTER:
aoi_data = None
subregion_data = None
if "aoi" in update:
    aoi_data = update["aoi"]
    subregion_data = (
        update.get("subregion_aois")
        if update.get("subregion") is not None
        else None
    )

if "dataset" in update:
    dataset_data = update["dataset"]
    aoi_data = update.get("aoi") or aoi_data
    # Unified map: basemap -> tiles -> AOI
    render_unified_map(dataset_data, aoi_data, subregion_data)
elif aoi_data:
    # AOI-only update (no dataset yet): render standalone AOI map
    render_aoi_map(aoi_data, subregion_data)
```

Key changes:
- When both AOI and dataset are available, render a SINGLE unified map
- When only AOI is available (dataset not yet selected), fall back to the existing `render_aoi_map()`
- The unified map fetches AOI geometry via `client.fetch_geometry()` (same as `render_aoi_map()` does) so the map is centered on the AOI at zoom 5, making TCL tiles visible

### Change 5: Fix Dataset Name Key in Existing `render_dataset_map()`

Even though the primary rendering path now uses `render_unified_map()`, keep `render_dataset_map()` working for backward compatibility and fix the name key:

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`, line 199

```python
# BEFORE:
dataset_name = dataset_data.get("data_layer", "Dataset Layer")

# AFTER:
dataset_name = dataset_data.get("dataset_name", dataset_data.get("data_layer", "Dataset Layer"))
```

### Change 6: Fix Hardcoded Sidebar Data

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`, lines 779-801

Fix the hardcoded TCL test data in `display_sidebar_selections()`:
- Change `"dataset_id": 0` to `"dataset_id": 4`
- Change `tree_cover_density_threshold=25` to `tree_cover_density_threshold=30`

This prevents confusion during debugging and ensures consistency with the YAML config.

## Data Model Changes

No database schema changes required. No new Pydantic models needed beyond the `TileURLBuilder` hierarchy.

The `DatasetSelectionResult` model remains unchanged. The `model_dump()` output already contains `dataset_name` -- the only issue was that `render_dataset_map()` was looking for `data_layer` instead.

## API Design

No API endpoint changes. The tile URL construction is internal to the agent tools, and the frontend rendering is client-side only. The only "API" change is the new `tile_url.py` module's public interface:

```python
# Public API of src/agent/tools/tile_url.py
def get_url_builder(dataset_id: int) -> TileURLBuilder
```

This is consumed only by `pick_dataset.py`.

## Error Handling Strategy

### Tile URL Construction (`tile_url.py`)
- Each `TileURLBuilder.build()` method handles its own edge cases (year out of range, etc.)
- The `PassthroughURLBuilder` acts as a safe default -- unknown dataset types get their base URL resolved without date parameterization
- Logging at debug level when a builder is selected and at info level for the final constructed URL

### Frontend Map Rendering (`render_unified_map`)
- `fetch_geometry()` failure is caught and logged as a warning; map falls back to global view (degraded but not broken)
- Invalid geometry data is caught via try/except on `shape()` call
- Missing `tile_url` shows a warning and returns early
- Outer try/except catches any unexpected error and falls back to `st.json()` display of raw data

### Backward Compatibility
- `render_aoi_map()` and `render_dataset_map()` are NOT deleted -- they remain for any other callers
- The change is only in `render_stream()` which now routes to `render_unified_map()` when dataset data is present

## Testing Strategy

### Unit Tests for TileURLBuilder (`tests/tools/test_tile_url.py`, NEW FILE)

```python
"""Tests for tile URL construction strategies."""
import pytest
from datetime import date

from src.agent.tools.tile_url import (
    DistAlertURLBuilder,
    YearFormatURLBuilder,
    TreeCoverLossURLBuilder,
    PassthroughURLBuilder,
    get_url_builder,
)


class TestDistAlertURLBuilder:
    def test_appends_date_params(self):
        builder = DistAlertURLBuilder()
        url = builder.build(
            "https://tiles.globalforestwatch.org/umd_glad_dist_alerts/latest/dynamic/{z}/{x}/{y}.png?render_type=true_color",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
        assert "&start_date=2024-01-01" in url
        assert "&end_date=2024-12-31" in url
        assert url.startswith("https://")


class TestYearFormatURLBuilder:
    def test_substitutes_year_in_range(self):
        builder = YearFormatURLBuilder(range(2000, 2023))
        url = builder.build(
            "/raster/collections/grasslands-v-1/items/grasslands-{year}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png",
            date(2020, 1, 1),
            date(2020, 12, 31),
        )
        assert "grasslands-2020" in url
        assert "{z}" in url  # Double braces survive .format()

    def test_uses_fallback_year_when_out_of_range(self):
        builder = YearFormatURLBuilder(
            range(2000, 2023), fallback_year="2022"
        )
        url = builder.build(
            "/raster/grasslands-{year}/tiles",
            date(2025, 1, 1),
            date(2025, 12, 31),
        )
        assert "grasslands-2022" in url


class TestTreeCoverLossURLBuilder:
    def test_appends_year_params_within_range(self):
        builder = TreeCoverLossURLBuilder()
        url = builder.build(
            "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color",
            date(2020, 1, 1),
            date(2024, 12, 31),
        )
        assert "&start_year=2020&end_year=2024" in url

    def test_caps_start_year_at_2023(self):
        builder = TreeCoverLossURLBuilder()
        url = builder.build(
            "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color",
            date(2024, 1, 1),
            date(2024, 12, 31),
        )
        assert "&start_year=2023" in url

    def test_uses_defaults_when_out_of_range(self):
        builder = TreeCoverLossURLBuilder()
        url = builder.build(
            "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color",
            date(1999, 1, 1),
            date(2000, 12, 31),
        )
        assert "&start_year=2001&end_year=2024" in url

    def test_preserves_tile_placeholders(self):
        builder = TreeCoverLossURLBuilder()
        url = builder.build(
            "https://example.com/{z}/{x}/{y}.png?foo=bar",
            date(2020, 1, 1),
            date(2024, 12, 31),
        )
        assert "{z}" in url
        assert "{x}" in url
        assert "{y}" in url


class TestGetURLBuilder:
    def test_returns_correct_builder_type(self):
        from src.agent.tools.data_handlers.analytics_handler import (
            DIST_ALERT_ID,
            TREE_COVER_LOSS_ID,
        )
        assert isinstance(
            get_url_builder(DIST_ALERT_ID), DistAlertURLBuilder
        )
        assert isinstance(
            get_url_builder(TREE_COVER_LOSS_ID),
            TreeCoverLossURLBuilder,
        )

    def test_unknown_id_returns_passthrough(self):
        assert isinstance(
            get_url_builder(9999), PassthroughURLBuilder
        )
```

### Existing Test Compatibility

The existing test `tests/tools/test_pick_dataset.py::test_tile_url_contains_date` (line 306) should continue to pass without modification because:
- The behavior is identical -- only the internal structure changed
- The final URL produced by `pick_dataset()` is the same
- The test calls `.format(z=3, x=5, y=3)` on the resulting URL and checks HTTP 200

### Frontend Testing

Frontend testing is manual via Streamlit (no automated frontend tests exist in the codebase). Manual test plan:

1. **TCL query**: "How much forest was lost in Brazil in 2020?" -- verify pink/red pixels visible on map, map centered on Brazil at zoom ~5
2. **Grasslands query**: "Show grasslands in Kenya" -- verify colormap tiles visible, no regression
3. **DIST-ALERT query**: "Show disturbance alerts in Indonesia" -- verify tiles visible, no regression
4. **AOI-only**: Ask about an area without requesting a dataset -- verify standalone AOI map still renders
5. **Year range**: Test TCL with years 2001, 2010, 2023, 2024 -- all should show tiles

## Migration Plan

This is a non-breaking change with no database migrations required. The rollout is:

1. **Phase 1**: Add `src/agent/tools/tile_url.py` with `TileURLBuilder` strategy classes and `tests/tools/test_tile_url.py`
2. **Phase 2**: Refactor `pick_dataset.py` to use `get_url_builder()` -- run existing `test_tile_url_contains_date` to verify no regression
3. **Phase 3**: Add `render_unified_map()` to `frontend/utils.py`
4. **Phase 4**: Update `render_stream()` to use `render_unified_map()` -- manual frontend testing
5. **Phase 5**: Fix `data_layer` -> `dataset_name` key and sidebar hardcoded data

Each phase is independently deployable and verifiable. Phases 1-2 (backend) and 3-5 (frontend) can be done in parallel.

## Risk Register

| Risk | Severity | Likelihood | Mitigation |
|------|----------|------------|------------|
| GFW tile service returns empty tiles at zoom 5 for some regions | Medium | Low | Test with multiple countries. If issue persists, investigate `render_type` parameter or add `minZoom`/`maxZoom` to TileLayer |
| `fetch_geometry()` in `render_unified_map()` adds latency | Low | Medium | The geometry fetch already happens in `render_aoi_map()` -- same latency. Could cache geometry in session state. |
| Circular import from `tile_url.py` importing `analytics_handler.py` constants | Medium | Medium | Use lazy imports inside `get_url_builder()` function (already shown in the design) |
| Other callers of `render_dataset_map()` broken by not updating them | Low | Low | `render_dataset_map()` is NOT modified in a breaking way -- only the key lookup is made more robust |
| TCL tiles genuinely require a different `render_type` parameter | High | Low | After implementing the zoom fix, if tiles are still blank, investigate the GFW tile API docs for correct `render_type` values. The existing test `test_tile_url_contains_date` fetches actual tiles and checks HTTP 200 -- if the tile content is transparent, that test won't catch it. Add a visual/size check. |

## Summary of Files Changed

| File | Change Type | Description |
|------|------------|-------------|
| `src/agent/tools/tile_url.py` | NEW | TileURLBuilder strategy pattern |
| `src/agent/tools/pick_dataset.py` | MODIFY | Replace if/elif chain with `get_url_builder()` call |
| `frontend/utils.py` | MODIFY | Add `render_unified_map()`, update `render_stream()`, fix `data_layer` key, fix sidebar data |
| `tests/tools/test_tile_url.py` | NEW | Unit tests for TileURLBuilder strategies |

Total: 2 new files, 2 modified files. The architectural improvement (strategy pattern + unified renderer) justifies the additional file, and the separation of tile URL logic from `pick_dataset.py` makes both easier to understand and test independently.
