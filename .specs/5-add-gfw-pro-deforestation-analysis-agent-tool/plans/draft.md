# Implementation Plan: GFW Pro Deforestation Analysis Agent Tool

## 1. Architecture Overview

This feature adds a new agent tool `gfw_pro_analysis` that reads pre-computed zarr rasters (SBTN, JRC, merged tree cover loss, integrated disturbance alerts) from S3 or local storage, clips them to user-selected AOI geometries, computes deforestation metrics, and returns a CSV string stored in agent state.

### Design Principles Applied

- **Minimal Surgery**: 5 files modified, 1 new file created, 1 new test file. All wiring follows existing patterns exactly.
- **Clean Architecture**: Analysis logic isolated in `gfw_pro_analysis.py`. Tool function is a thin async wrapper; computation runs in `asyncio.to_thread()`.
- **Robustness**: Graceful handling of missing AOI, geometry fetch failures, zarr open failures, empty clip results. Module-level dataset caching with lazy initialization.
- **Developer Experience**: Function signatures and return patterns identical to existing tools (`pull_data.py`, `pick_dataset.py`). No new abstractions or frameworks.

### File Change Summary

| File | Action | Purpose |
|---|---|---|
| `pyproject.toml` | Modify | Add xarray, zarr, rioxarray, dask dependencies |
| `src/agent/state.py` | Modify | Add `gfw_pro_csv: Optional[str]` to AgentState |
| `src/agent/tools/__init__.py` | Modify | Export `gfw_pro_analysis` |
| `src/agent/graph.py` | Modify | Import and register tool; add to prompt |
| `src/agent/tools/gfw_pro_analysis.py` | Create | Core analysis module + tool function |
| `tests/tools/test_gfw_pro_analysis.py` | Create | Unit and integration tests |

---

## 2. Dependency Changes

### File: `pyproject.toml`

Add to `[project].dependencies` (after existing geospatial deps):

```
"xarray>=2024.1.0",
"zarr>=2.18.0,<3",
"rioxarray>=0.17.0",
"dask[array,dataframe]>=2024.1.0",
```

**Rationale for version pins**:
- `zarr<3`: zarr v3 has breaking API changes; xarray compatibility is still maturing with zarr v3. Pin to v2.x for stability.
- Other packages: minimum versions ensure Python 3.12 compatibility without over-constraining.

**Already present** (no changes needed): `s3fs==2025.3.0`, `fiona==1.10.1`, `geopandas==1.0.1`, `pandas==2.2.3`, `boto3==1.38.27`.

After adding, run `uv lock` to regenerate `uv.lock`.

---

## 3. State Model Changes

### File: `src/agent/state.py`

Add `Optional` import and new field to `AgentState`:

```python
# Add to imports
from typing import Optional

# Add to AgentState TypedDict, after codeact_parts:
    # gfw-pro-analysis tool
    gfw_pro_csv: Optional[str]
```

This follows the existing pattern where each tool owns specific state keys (comments document which tool writes each key).

---

## 4. New Module: `src/agent/tools/gfw_pro_analysis.py`

This is the primary new file. It contains all analysis logic and the tool function.

### 4.1 Module Constants and Configuration

```python
"""GFW Pro deforestation and disturbance alert analysis tool."""

import asyncio
import os
from datetime import datetime
from typing import Annotated, Optional

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401 — registers .rio accessor on xarray
import xarray as xr
from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from shapely.geometry import shape

from src.agent.state import AgentState
from src.shared.geocoding_helpers import get_geometry_data
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

# S3 URIs for each zarr dataset (default when GFW_PRO_DATA_PATH is unset)
S3_ZARR_PATHS = {
    "sbtn": "s3://gfwpro-users/op-external-user/v2/sbtn.area.zarr",
    "jrc": "s3://gfwpro-users/op-external-user/v2/jrc.area.zarr",
    "mergedLoss": "s3://gfwpro-users/op-external-user/v2/mergedLoss.zarr",
    "intdist": "s3://gfwpro-users/op-external-user/v3/intdist_date_conf.zarr",
}

# Data version metadata (for CSV header comment)
DATA_VERSIONS = {
    "TCL": "2024 (umd_tree_cover_loss/v1.12)",
    "SBTN": "1.1 (sbtn_natural_forests_map/v202504)",
    "JRC": "2020.2 (jrc_global_forest_cover/v2020.2)",
    "Landmark": "(gfw_indigenous_community_and_indicative_lands/v202408)",
    "Integrated Alerts": "(gfw_integrated_dist_alerts/v20260208)",
}

# Default alert start date
DEFAULT_ALERT_START_DATE = "2025-01-01"

# Module-level dataset cache
_datasets_cache: Optional[dict[str, xr.Dataset]] = None
```

### 4.2 `get_datasets() -> dict[str, xr.Dataset]`

Opens all 4 zarr files lazily (backed by dask). Cached as module singleton.

```python
def get_datasets() -> dict[str, xr.Dataset]:
    """Open all zarr datasets. Returns cached dict on subsequent calls."""
    global _datasets_cache
    if _datasets_cache is not None:
        return _datasets_cache

    base_path = os.environ.get("GFW_PRO_DATA_PATH")

    datasets = {}
    for key, s3_uri in S3_ZARR_PATHS.items():
        if base_path:
            # Local path mode: base_path/sbtn.area.zarr, etc.
            zarr_name = s3_uri.rsplit("/", 1)[-1]
            path = os.path.join(base_path, zarr_name)
        else:
            path = s3_uri

        logger.info(f"Opening zarr dataset: {key}", path=path)
        datasets[key] = xr.open_zarr(path, chunks="auto")

    _datasets_cache = datasets
    return _datasets_cache
```

**Key decisions**:
- `chunks="auto"` lets dask choose chunk sizes from zarr metadata.
- Local path fallback uses the same filename from the S3 URI (e.g., `sbtn.area.zarr`).
- No try/except here -- failure to open datasets is fatal and should propagate up to the tool error handler.

### 4.3 `clip_ds_to_geojson(ds, geojson_geom) -> xr.Dataset`

Clips a zarr dataset to an AOI geometry using rioxarray.

```python
def clip_ds_to_geojson(
    ds: xr.Dataset, geojson_geom: dict
) -> xr.Dataset:
    """Clip dataset to GeoJSON geometry via bbox slice + rioxarray clip."""
    geom = shape(geojson_geom)
    minx, miny, maxx, maxy = geom.bounds

    # Bbox slice first (fast, reduces data volume before clip)
    ds_bbox = ds.sel(
        x=slice(minx, maxx),
        y=slice(maxy, miny),  # y-axis typically descending
    )

    # Set CRS if not already set (EPSG:4326 for all GFW Pro rasters)
    if not ds_bbox.rio.crs:
        ds_bbox = ds_bbox.rio.write_crs("EPSG:4326")

    # Precise clip to geometry
    clipped = ds_bbox.rio.clip(
        [geojson_geom], crs="EPSG:4326", drop=True
    )
    return clipped
```

**Key decisions**:
- Bbox slice before clip dramatically reduces memory/compute for large rasters.
- `y=slice(maxy, miny)` handles the common descending-y convention in raster data. If the dataset uses ascending y, we may need to detect and swap -- see Risk Register.
- `drop=True` removes all-NaN slices after clipping.

### 4.4 `run_analysis(geojson_geometry, name) -> pd.DataFrame`

Core analysis function. Computes all 9 metrics for a single AOI.

```python
def run_analysis(
    geojson_geometry: dict, name: str
) -> pd.DataFrame:
    """Compute deforestation metrics for a single AOI geometry.

    Returns a single-row DataFrame with columns:
    name, total_area, sbtn_area, sbtn_loss_area, jrc_area, jrc_loss_area,
    indig_area, alert_area, sbtn_alert_area, jrc_alert_area
    """
    datasets = get_datasets()
    alert_start = os.environ.get(
        "GFW_PRO_ALERT_START_DATE", DEFAULT_ALERT_START_DATE
    )
    alert_start_date = datetime.strptime(alert_start, "%Y-%m-%d")

    # Clip all datasets to AOI
    sbtn = clip_ds_to_geojson(datasets["sbtn"], geojson_geometry)
    jrc = clip_ds_to_geojson(datasets["jrc"], geojson_geometry)
    loss = clip_ds_to_geojson(datasets["mergedLoss"], geojson_geometry)
    intdist = clip_ds_to_geojson(datasets["intdist"], geojson_geometry)

    # Pixel area in hectares (from sbtn.area.zarr "area" variable)
    pixel_area = sbtn["area"].values  # area per pixel in hectares

    # Total area
    total_area = float(np.nansum(pixel_area))

    # SBTN natural forest mask and area
    sbtn_mask = sbtn["sbtn"].values > 0  # boolean mask
    sbtn_area = float(np.nansum(pixel_area[sbtn_mask]))

    # JRC forest mask and area
    jrc_mask = jrc["jrc"].values > 0
    jrc_area = float(np.nansum(pixel_area[jrc_mask]))

    # Tree cover loss 2021-2024 mask
    loss_vals = loss["mergedLoss"].values
    tcl_mask = (loss_vals >= 2021) & (loss_vals <= 2024)

    # SBTN forest with TCL loss
    sbtn_loss_area = float(
        np.nansum(pixel_area[sbtn_mask & tcl_mask])
    )

    # JRC forest with TCL loss
    jrc_loss_area = float(
        np.nansum(pixel_area[jrc_mask & tcl_mask])
    )

    # Indigenous/community lands area
    # (Landmark data is in the sbtn zarr as "indig" variable)
    indig_mask = sbtn["indig"].values > 0
    indig_area = float(np.nansum(pixel_area[indig_mask]))

    # Disturbance alerts since alert_start_date
    # intdist_date_conf has date encoded -- extract and filter
    alert_dates = intdist["date"].values
    alert_conf = intdist["conf"].values
    # High/highest confidence: conf >= 2
    alert_mask = (alert_conf >= 2) & (
        alert_dates >= int(alert_start_date.strftime("%Y%m%d"))
    )
    alert_area = float(np.nansum(pixel_area[alert_mask]))

    # Alert area intersected with SBTN/JRC forest
    sbtn_alert_area = float(
        np.nansum(pixel_area[alert_mask & sbtn_mask])
    )
    jrc_alert_area = float(
        np.nansum(pixel_area[alert_mask & jrc_mask])
    )

    return pd.DataFrame([{
        "name": name,
        "total_area": round(total_area, 4),
        "sbtn_area": round(sbtn_area, 4),
        "sbtn_loss_area": round(sbtn_loss_area, 4),
        "jrc_area": round(jrc_area, 4),
        "jrc_loss_area": round(jrc_loss_area, 4),
        "indig_area": round(indig_area, 4),
        "alert_area": round(alert_area, 4),
        "sbtn_alert_area": round(sbtn_alert_area, 4),
        "jrc_alert_area": round(jrc_alert_area, 4),
    }])
```

**IMPORTANT**: The exact variable names within each zarr dataset (`sbtn["sbtn"]`, `sbtn["area"]`, `jrc["jrc"]`, `loss["mergedLoss"]`, `intdist["date"]`, `intdist["conf"]`, `sbtn["indig"]`) are based on the PROMPT description and the query3.py reference. These MUST be verified against the actual zarr file contents during implementation. The implementer should open each dataset and inspect `ds.data_vars` to confirm variable names, coordinate names (`x`/`y` vs `lon`/`lat`), and value semantics.

### 4.5 `dataframes_to_csv(dfs) -> str`

```python
def dataframes_to_csv(dfs: list[pd.DataFrame]) -> str:
    """Concatenate DataFrames and serialize to CSV string with metadata header."""
    combined = pd.concat(dfs, ignore_index=True)
    version_lines = [
        f"# {k}: {v}" for k, v in DATA_VERSIONS.items()
    ]
    header = "\n".join(version_lines) + "\n"
    return header + combined.to_csv(index=False)
```

### 4.6 Tool Function: `gfw_pro_analysis`

```python
@tool("gfw_pro_analysis")
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[AgentState, InjectedState],
) -> Command:
    """Run GFW Pro deforestation and disturbance alert analysis
    for the current AOI. Returns SBTN/JRC forest area, tree cover
    loss 2021-2024, indigenous lands area, and integrated
    disturbance alerts. Results are provided as a downloadable
    CSV."""
    logger.info("GFW-PRO-ANALYSIS-TOOL")

    # 1. Get AOI list (prefer aoi_selection for multi-AOI)
    aoi_selection = state.get("aoi_selection")
    if aoi_selection and aoi_selection.get("aois"):
        aois = aoi_selection["aois"]
    elif state.get("aoi"):
        aois = [state["aoi"]]
    else:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="No AOI selected. Please select an "
                        "area of interest first using pick_aoi.",
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # 2. Fetch geometries for all AOIs
    geo_data_list = await asyncio.gather(
        *[
            get_geometry_data(aoi["source"], aoi["src_id"])
            for aoi in aois
        ]
    )

    # 3. Validate geometry results
    valid_pairs = []
    for aoi, geo_data in zip(aois, geo_data_list):
        if geo_data is None or geo_data.get("geometry") is None:
            logger.warning(
                f"No geometry found for AOI: {aoi.get('name')}"
            )
            continue
        valid_pairs.append((aoi, geo_data))

    if not valid_pairs:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content="Could not retrieve geometry for "
                        "any of the selected AOIs.",
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # 4. Run analysis in thread pool (non-blocking)
    dfs = []
    for aoi, geo_data in valid_pairs:
        name = aoi.get("name", "Unknown")
        geojson = geo_data["geometry"]
        df = await asyncio.to_thread(run_analysis, geojson, name)
        dfs.append(df)

    # 5. Build CSV
    csv_string = dataframes_to_csv(dfs)

    # 6. Build summary message
    total_aois = len(dfs)
    summary_parts = [
        f"GFW Pro analysis complete for {total_aois} AOI(s).",
        "Metrics computed: total area, SBTN forest area, "
        "SBTN loss area, JRC forest area, JRC loss area, "
        "indigenous lands area, disturbance alert area, "
        "SBTN alert area, JRC alert area.",
        "Results are available as a downloadable CSV.",
    ]

    return Command(
        update={
            "gfw_pro_csv": csv_string,
            "messages": [
                ToolMessage(
                    content=" ".join(summary_parts),
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )
```

**Key decisions**:
- Each AOI analysis runs sequentially in `asyncio.to_thread()` rather than parallel threads. This avoids concurrent zarr reads on the same cached datasets which could cause memory pressure. For typical use (1-5 AOIs), sequential is fine.
- Geometry fetch uses `asyncio.gather` (async I/O, no thread needed).
- Missing geometries are skipped with a warning rather than failing the entire operation.
- No AOI selected returns early with a helpful message (not an exception) so the LLM can guide the user.

---

## 5. Tool Registration

### File: `src/agent/tools/__init__.py`

```python
# Add import
from .gfw_pro_analysis import gfw_pro_analysis

# Add to __all__
__all__ = [
    "pick_aoi",
    "pick_dataset",
    "pull_data",
    "generate_insights",
    "get_capabilities",
    "gfw_pro_analysis",  # <-- add
]
```

### File: `src/agent/graph.py`

```python
# Add to import block (lines 17-23)
from src.agent.tools import (
    generate_insights,
    get_capabilities,
    gfw_pro_analysis,   # <-- add
    pick_aoi,
    pick_dataset,
    pull_data,
)

# Add to tools list (lines 113-119)
tools = [
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
    generate_insights,
    gfw_pro_analysis,   # <-- add
]
```

### File: `src/agent/graph.py` - Prompt Update

In the `get_prompt()` function, add to the TOOLS documentation section:

```
- gfw_pro_analysis: Run GFW Pro deforestation and disturbance alert analysis for the current AOI. Returns SBTN/JRC forest area, tree cover loss 2021-2024, indigenous lands area, and integrated disturbance alerts as a downloadable CSV. Requires an AOI to be selected first.
```

And add to the WORKFLOW section, as an alternative path after AOI selection:

```
If user asks for 'GFW Pro analysis' or deforestation metrics: call gfw_pro_analysis (requires AOI selected).
```

---

## 6. Error Handling Strategy

### Categorized Error Responses

| Error Condition | Handling | User Impact |
|---|---|---|
| No AOI selected | Return early with ToolMessage guidance | LLM tells user to select AOI first |
| Geometry fetch returns None | Skip that AOI, warn in logs | Other AOIs still processed |
| All geometries fail | Return early with ToolMessage | LLM explains failure |
| Zarr dataset open failure | Exception propagates to `handle_tool_errors` | Generic "Tool error: ..." message |
| Clip returns empty dataset | `np.nansum` returns 0.0 for all metrics | Valid row with 0.0 values (correct behavior) |
| Invalid geometry (not parseable by shapely) | Exception from `shape()` propagates | Caught by middleware |
| S3 credentials missing | `PermissionError` from s3fs propagates | Caught by middleware |
| Memory error on large AOI | `MemoryError` propagates | Caught by middleware |

### Logging

All operations logged at INFO level for traceability:
- Dataset opening (path used)
- Each AOI analysis start/complete (name, timing)
- Geometry fetch failures (WARNING level)

---

## 7. Testing Strategy

### New File: `tests/tools/test_gfw_pro_analysis.py`

#### Test Structure

```python
"""Tests for GFW Pro deforestation analysis tool."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

pytestmark = pytest.mark.asyncio(loop_scope="session")

# Override DB fixtures (tests don't need database)
@pytest.fixture(scope="function", autouse=True)
def test_db():
    pass

@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    pass

@pytest.fixture(scope="function", autouse=True)
def test_db_pool():
    pass
```

#### Unit Tests for Core Functions

1. **`test_get_datasets_caches_results`**: Call `get_datasets()` twice, verify `xr.open_zarr` called only N times (once per dataset), not 2N.

2. **`test_get_datasets_local_path`**: Set `GFW_PRO_DATA_PATH` env var, verify paths use local base.

3. **`test_get_datasets_s3_fallback`**: Unset `GFW_PRO_DATA_PATH`, verify S3 URIs used.

4. **`test_clip_ds_to_geojson`**: Create a small synthetic xarray Dataset with known values, clip to a small polygon, verify clipped result has correct bounds and values.

5. **`test_run_analysis_returns_correct_columns`**: Mock `get_datasets()` to return synthetic data, verify output DataFrame has all 9 metric columns plus `name`.

6. **`test_run_analysis_values`**: Use the IDN test case geometry (from query3.py reference). If running against real data, verify: `sbtn_area ~994.6 ha`, `sbtn_loss ~59.95 ha`, `total_area ~1006 ha`. Mark as `@pytest.mark.skipif` if zarr data not available locally.

7. **`test_dataframes_to_csv`**: Create 2 single-row DataFrames, verify concatenation and CSV header includes version metadata.

#### Tool Integration Tests

8. **`test_gfw_pro_analysis_no_aoi`**: Invoke tool with empty state (no `aoi` or `aoi_selection`). Verify returns Command with guidance message.

9. **`test_gfw_pro_analysis_single_aoi`**: Mock `get_geometry_data` and `run_analysis`. Invoke tool with single AOI in state. Verify `gfw_pro_csv` in Command update.

10. **`test_gfw_pro_analysis_multi_aoi`**: Mock with 2 AOIs. Verify CSV has 2 data rows.

11. **`test_gfw_pro_analysis_partial_geometry_failure`**: Mock 2 AOIs where one geometry fetch returns None. Verify tool still succeeds with 1 row.

12. **`test_gfw_pro_analysis_runs_in_thread`**: Patch `asyncio.to_thread` and verify it is called (non-blocking check).

#### Mocking Strategy

- Mock `xr.open_zarr` for unit tests to avoid needing actual zarr data.
- Mock `get_geometry_data` for tool-level tests to avoid DB dependency.
- Mock `get_datasets()` to return synthetic xarray Datasets with predictable values.
- For the IDN validation test, optionally use real zarr data (gated by env var or pytest marker).

---

## 8. Implementation Order

Steps ordered by dependency. Each step is independently verifiable.

### Step 1: Add Dependencies to `pyproject.toml`
- Add xarray, zarr, rioxarray, dask to `[project].dependencies`
- Run `uv lock` to update lockfile
- Run `uv sync` to verify install
- **Verify**: `python -c "import xarray, zarr, rioxarray, dask"` succeeds

### Step 2: Add `gfw_pro_csv` to AgentState
- Modify `src/agent/state.py`
- **Verify**: `python -c "from src.agent.state import AgentState"` succeeds; type checker accepts the new field

### Step 3: Create `src/agent/tools/gfw_pro_analysis.py`
- Implement all functions: `get_datasets`, `clip_ds_to_geojson`, `run_analysis`, `dataframes_to_csv`, `gfw_pro_analysis`
- **Verify**: `python -c "from src.agent.tools.gfw_pro_analysis import gfw_pro_analysis"` succeeds

### Step 4: Register the Tool
- Update `src/agent/tools/__init__.py`
- Update `src/agent/graph.py` (import, tools list, prompt)
- **Verify**: `python -c "from src.agent.tools import gfw_pro_analysis"` succeeds; grep confirms tool in `tools` list

### Step 5: Write Tests
- Create `tests/tools/test_gfw_pro_analysis.py`
- Run `uv run pytest tests/tools/test_gfw_pro_analysis.py -v`
- **Verify**: All tests pass

### Step 6: Integration Validation (Manual)
- Start the full stack with `GFW_PRO_DATA_PATH` pointing to local zarr data
- Select an AOI (IDN test case)
- Ask agent for "GFW Pro analysis"
- Verify CSV output matches expected values

---

## 9. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Zarr variable names differ from assumed (`sbtn`, `jrc`, etc.) | High | Medium | Implementer MUST inspect actual zarr `data_vars` before coding. Add a diagnostic script or test that prints variable names. |
| Y-axis direction (ascending vs descending) varies across datasets | Medium | Medium | `clip_ds_to_geojson` should detect y-direction and adjust slice accordingly. Add `if ds.y[0] < ds.y[-1]: slice(miny, maxy)` guard. |
| Large AOI causes OOM when loading zarr data into memory | High | Low | Bbox slice before clip reduces data volume. For very large AOIs, consider chunked processing or a size limit with user warning. |
| zarr v2 vs v3 compatibility | Medium | Low | Pin `zarr>=2.18.0,<3` explicitly. |
| S3 access latency on first call | Low | High | Expected behavior. Module-level caching means subsequent calls are fast. First call may take 10-30s. Document this in tool docstring or user-facing message. |
| `rioxarray` requires GDAL/libgdal system library | Medium | Medium | Dockerfile must include `libgdal-dev` or equivalent. Verify Docker build includes this. |
| Alert date encoding format unknown | High | Medium | The `intdist_date_conf.zarr` date format must be verified. Assumed `YYYYMMDD` integer. If different (e.g., days since epoch), conversion logic changes. |
| Coordinate names (`x`/`y` vs `lon`/`lat`) | Medium | Medium | Some zarr datasets may use `lon`/`lat`. `clip_ds_to_geojson` must handle both. Use `ds.rio.set_spatial_dims(x_dim=..., y_dim=...)` if needed. |
| `fsspec` version conflict with existing `s3fs==2025.3.0` | Low | Low | `s3fs` pins its own `fsspec` version. Adding explicit `fsspec` may conflict. Let `s3fs` manage `fsspec` transitively instead of adding it explicitly. |

---

## 10. Decisions and Trade-offs

1. **Environment variables via `os.environ.get()` vs SharedSettings**: The PROMPT specifies env vars directly. Using `os.environ.get()` in the module is simpler and avoids coupling to `SharedSettings`. Trade-off: less centralized config, but these are module-specific settings not shared across the app.

2. **Sequential vs parallel AOI analysis**: Sequential `asyncio.to_thread()` per AOI rather than parallel threads. Simpler, avoids memory pressure from concurrent zarr reads. For the typical 1-5 AOI case, the performance difference is negligible.

3. **No frontend changes in scope**: The PROMPT does not explicitly require frontend changes. The `gfw_pro_csv` state key is set, but rendering a download button requires frontend changes in `frontend/utils.py`. This is noted as a follow-up item.

4. **Error propagation strategy**: Validation errors (no AOI) return graceful ToolMessages. Infrastructure errors (zarr open failure, S3 auth) propagate as exceptions caught by `handle_tool_errors` middleware. This matches the existing codebase pattern.

5. **No `fsspec` in explicit dependencies**: `s3fs==2025.3.0` already depends on `fsspec`. Adding it explicitly risks version conflicts. Let it be transitive.
