# SPEC: GFW Pro Deforestation Analysis Agent Tool

## 1. Requirements Traceability Matrix

| ID | Requirement | Spec Section | Status |
|---|---|---|---|
| R1 | New module `src/agent/tools/gfw_pro_analysis.py` | 3.3 | Addressed |
| R2 | 4 zarr data sources (sbtn, jrc, mergedLoss, intdist) | 3.3.1 | Addressed |
| R3 | `GFW_PRO_DATA_PATH` env var with S3 fallback | 3.3.2 | Addressed |
| R4 | `GFW_PRO_ALERT_START_DATE` env var, default `2025-01-01` | 3.3.1, 3.3.4 | Addressed |
| R5 | AWS credential env vars for S3 access | 3.3.2 (implicit via s3fs) | Addressed |
| R6 | 10 output columns (name + 9 metrics) | 3.3.4 | Addressed |
| R7 | Values in hectares, 4 decimal places | 3.3.4 | Addressed |
| R8 | `get_datasets()` with module-level singleton cache | 3.3.2 | Addressed |
| R9 | `clip_ds_to_geojson()` with bbox slice + rioxarray clip | 3.3.3 | Addressed |
| R10 | `run_analysis()` computing all 9 metrics | 3.3.4 | Addressed |
| R11 | `dataframes_to_csv()` with version header | 3.3.5 | Addressed |
| R12 | `asyncio.to_thread()` for non-blocking execution | 3.3.6 | Addressed |
| R13 | Data version comments in CSV header | 3.3.5 | Addressed |
| R14 | `@tool("gfw_pro_analysis")` following existing pattern | 3.3.6 | Addressed |
| R15 | Read `state["aoi"]` for AOI info | 3.3.6 | Addressed |
| R16 | Multi-AOI support via `aoi_selection["aois"]` | 3.3.6 | Addressed |
| R17 | Call `get_geometry_data(source, src_id)` | 3.3.6 | Addressed |
| R18 | Return Command with `gfw_pro_csv` state key | 3.3.6 | Addressed |
| R19 | Add tool to `tools` list in `graph.py` | 3.4 | Addressed |
| R20 | Add `gfw_pro_csv: Optional[str]` to AgentState | 3.2 | Addressed |
| R21 | Add deps (xarray, zarr, rioxarray, dask) | 3.1 | Addressed |
| AC1 | `run_analysis()` correct IDN test values | 4.2 | Addressed (conditional on data availability) |
| AC2 | Tool callable from agent (in tools list) | 3.4 | Addressed |
| AC3 | `gfw_pro_csv` in state after tool runs | 4.1 | Addressed |
| AC4 | Multi-AOI produces multi-row CSV | 4.1 | Addressed |
| AC5 | Analysis runs in thread pool | 4.1 | Addressed |
| AC6 | S3 and local path modes both work | 4.1 | Addressed |

### Gaps

| Gap | Justification | Severity | Follow-up |
|---|---|---|---|
| Frontend download button for `gfw_pro_csv` | PROMPT says "downloadable CSV" but does not specify frontend changes. The state key is set; rendering a download button in `frontend/utils.py` is a separate UI task. | Medium | Create follow-up issue for frontend `gfw_pro_csv` download rendering. |
| PROMPT references `Pipfile` | Project uses `pyproject.toml` with `uv`. Spec targets `pyproject.toml` correctly. | None (PROMPT error) | N/A |

---

## 2. Validation Resolution Log

| # | Finding | Resolution |
|---|---|---|
| V-E1 | `InjectedToolCallId` imported from `langchain_core.tools` but codebase uses `langchain_core.tools.base` | **Fixed**: Spec uses `from langchain_core.tools.base import InjectedToolCallId` to match codebase convention. |
| V-E2 | Injected parameters missing `= None` defaults | **Fixed**: Spec adds `= None` defaults to `tool_call_id` and `state` parameters to match codebase convention. |
| V-E3 | State type annotation uses `AgentState` but codebase uses `Dict` | **Fixed**: Spec uses `Annotated[Dict, InjectedState]` to match existing tools. |
| V-E4 | `graph.py` import style mismatch (`langchain_core.messages` vs `langchain.messages`) | **Accepted**: The new module (`gfw_pro_analysis.py`) uses `langchain_core.messages` which is correct for tool files. `graph.py` modifications only add to the import list and tools list, no new ToolMessage imports in graph.py. |
| V-E5 | Dockerfile missing `libgdal-dev` for rioxarray | **Fixed**: Added as explicit Step 0 in implementation plan. |
| V-E6 | `get_geometry_data` requires active DB pool | **Noted**: At runtime the pool is initialized at app startup. Tests must mock `get_geometry_data` entirely. Spec testing strategy accounts for this. |
| V-A4 | Trailing slash in intdist S3 URI causes empty filename for local path | **Fixed**: `get_datasets()` now strips trailing slashes before extracting filename. |
| V-A5 | GeometryCollection not handled by `rio.clip()` | **Fixed**: `clip_ds_to_geojson` decomposes GeometryCollection into individual geometries before clipping. |
| V-A6 | CRS assumption (all datasets EPSG:4326) | **Accepted with guard**: Spec writes CRS as EPSG:4326 if not set, which is correct for GFW Pro rasters. If a dataset has a different CRS, the write_crs call is skipped and the existing CRS is used. |
| V-A7 | Pixel area from sbtn used across all datasets assumes aligned grids | **Accepted**: All 4 GFW Pro zarr datasets are co-registered at 10m resolution on the same grid. This is a property of the GFW Pro data pipeline. Documented as assumption. |
| V-A8 | Array shape alignment across datasets after clipping | **Accepted**: Same grid alignment. If shapes differ, numpy broadcasting will raise a clear error caught by middleware. |
| V-A10 | `asyncio.gather` for geometry fetch could exhaust DB pool | **Accepted**: Typical use is 1-5 AOIs. DB pool default is 5 connections with overflow. Not a practical concern. |
| V-A11 | `run_analysis` exception for one AOI fails entire tool | **Fixed**: Added per-AOI try/except in tool function with warning and skip. |
| V-A12 | Prompt update insertion point not specified | **Fixed**: Spec provides exact insertion points with surrounding context. |
| V-A13 | Test invocation format not specified | **Fixed**: Spec provides exact `ainvoke` input format. |
| V-EC2 | Trailing slash bug in local path construction | **Fixed**: Same as V-A4. |
| V-EC4 | Race condition in `get_datasets()` with concurrent threads | **Deferred**: Severity Low. The worst case is opening datasets twice on first concurrent access. A threading lock could be added but adds complexity for negligible benefit. Recommended follow-up: add `threading.Lock` if concurrency issues observed. |
| V-EC5 | Dataset cache never invalidated | **Accepted**: Process restart is sufficient. Zarr data updates are infrequent (monthly at most). |
| V-EC6 | All-NaN clip returns 0.0 metrics (misleading) | **Deferred**: Severity Low. Adding "no data" detection adds complexity. 0.0 is technically correct. Follow-up: add a warning message if total_area is 0. |
| V-EC7 | GeometryCollection handling | **Fixed**: Same as V-A5. |
| V-EC12 | Plan omits `fsspec` but PROMPT lists it | **Accepted**: `fsspec` is a transitive dependency of `s3fs`. Adding it explicitly risks version conflicts. |
| V-EC13 | `shapely` is transitive via geopandas, not explicit | **Accepted**: `geopandas` is a core dependency unlikely to be removed. Adding `shapely` explicitly is unnecessary churn. |
| V-EC15 | No input validation on geometry complexity | **Deferred**: Severity Low. Geometry comes from DB, not direct user input. Follow-up: add vertex count check if abuse observed. |
| V-EC16 | CSV injection via AOI name | **Fixed**: Spec sanitizes name field by stripping leading `=`, `+`, `-`, `@` characters. |
| V-A9 | `.values` forces full materialization into memory | **Accepted with mitigation**: Bbox slice before clip reduces data volume significantly. Added size guard: if clipped area exceeds 100M pixels, raise with user-friendly error. |
| V-EC8 | S3 throttling / rate limiting | **Deferred**: Severity Low, Likelihood Low. S3 throttling is rare for read operations. Follow-up: add retry with exponential backoff if observed. |
| V-EC9 | No timeout for long-running analysis | **Deferred**: Severity Medium, Likelihood Low. FastAPI has its own request timeout. Adding explicit timeout adds complexity. Follow-up: wrap `asyncio.to_thread` in `asyncio.wait_for` if timeouts observed. |

---

## 3. Implementation Plan

### 3.0 Prerequisites: Dockerfile Update

**File**: `/mnt/e/agentdev/projects/project-zeno/Dockerfile`

Add GDAL system library required by `rioxarray`:

```dockerfile
# Find the existing apt-get install block:
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    ca-certificates \
    libexpat1 \

# Add after libexpat1:
    libgdal-dev \
```

**Verify**: `docker build .` succeeds.

---

### 3.1 Add Dependencies to `pyproject.toml`

**File**: `/mnt/e/agentdev/projects/project-zeno/pyproject.toml`

Add to `[project].dependencies` array (after existing geospatial deps like `geopandas`):

```
"xarray>=2024.1.0",
"zarr>=2.18.0,<3",
"rioxarray>=0.17.0",
"dask[array,dataframe]>=2024.1.0",
```

**Rationale**: `zarr<3` pins to v2.x for xarray compatibility (zarr v3 has breaking changes). Other minimums ensure Python 3.12 support.

**Do NOT add**: `fsspec` (transitive via `s3fs`), `shapely` (transitive via `geopandas`).

After editing, run:
```bash
uv lock
uv sync
```

**Verify**: `python -c "import xarray, zarr, rioxarray, dask"` succeeds.

---

### 3.2 Add `gfw_pro_csv` to AgentState

**File**: `/mnt/e/agentdev/projects/project-zeno/src/agent/state.py`

Add `Optional` to the typing import:

```python
# Current:
from typing import Annotated, Sequence

# Change to:
from typing import Annotated, Optional, Sequence
```

Add field to `AgentState` TypedDict, after the `codeact_parts` field:

```python
    codeact_parts: list[CodeActPart]

    # gfw-pro-analysis tool
    gfw_pro_csv: Optional[str]
```

**Verify**: `python -c "from src.agent.state import AgentState; print('gfw_pro_csv' in AgentState.__annotations__)"` prints `True`.

---

### 3.3 Create `src/agent/tools/gfw_pro_analysis.py`

**File**: `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/gfw_pro_analysis.py` (NEW)

#### 3.3.1 Module Header, Constants, Imports

```python
"""GFW Pro deforestation and disturbance alert analysis tool."""

import asyncio
import os
import re
import threading
from datetime import datetime
from typing import Annotated, Dict, Optional

import numpy as np
import pandas as pd
import rioxarray  # noqa: F401 -- registers .rio accessor
import xarray as xr
from langchain_core.messages import ToolMessage
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command
from shapely.geometry import mapping, shape

from src.shared.geocoding_helpers import get_geometry_data
from src.shared.logging_config import get_logger

logger = get_logger(__name__)

# S3 URIs for zarr datasets (used when GFW_PRO_DATA_PATH is unset)
S3_ZARR_PATHS = {
    "sbtn": "s3://gfwpro-users/op-external-user/v2/sbtn.area.zarr",
    "jrc": "s3://gfwpro-users/op-external-user/v2/jrc.area.zarr",
    "mergedLoss": (
        "s3://gfwpro-users/op-external-user/v2/mergedLoss.zarr"
    ),
    "intdist": (
        "s3://gfwpro-users/op-external-user/v3/"
        "intdist_date_conf.zarr"
    ),
}

# Data version metadata for CSV header
DATA_VERSIONS = {
    "TCL": "2024 (umd_tree_cover_loss/v1.12)",
    "SBTN": "1.1 (sbtn_natural_forests_map/v202504)",
    "JRC": "2020.2 (jrc_global_forest_cover/v2020.2)",
    "Landmark": (
        "(gfw_indigenous_community_and_indicative_lands/v202408)"
    ),
    "Integrated Alerts": (
        "(gfw_integrated_dist_alerts/v20260208)"
    ),
}

DEFAULT_ALERT_START_DATE = "2025-01-01"

# Max pixels after clip before refusing (memory guard)
MAX_PIXELS = 100_000_000

# Module-level dataset cache
_datasets_cache: Optional[dict[str, xr.Dataset]] = None
_datasets_lock = threading.Lock()
```

#### 3.3.2 `get_datasets()`

```python
def get_datasets() -> dict[str, xr.Dataset]:
    """Open all zarr datasets. Cached as module singleton."""
    global _datasets_cache
    if _datasets_cache is not None:
        return _datasets_cache

    with _datasets_lock:
        # Double-check after acquiring lock
        if _datasets_cache is not None:
            return _datasets_cache

        base_path = os.environ.get("GFW_PRO_DATA_PATH")
        datasets = {}

        for key, s3_uri in S3_ZARR_PATHS.items():
            if base_path:
                # Extract filename, strip trailing slashes
                zarr_name = s3_uri.rstrip("/").rsplit("/", 1)[-1]
                path = os.path.join(base_path, zarr_name)
            else:
                path = s3_uri

            logger.info(
                "Opening zarr dataset",
                key=key,
                path=path,
            )
            datasets[key] = xr.open_zarr(path, chunks="auto")

        _datasets_cache = datasets
        return _datasets_cache
```

**Key points**:
- `rstrip("/")` before `rsplit` fixes the trailing-slash bug for `intdist_date_conf.zarr/`.
- `threading.Lock` with double-check prevents duplicate opens under concurrent `asyncio.to_thread` calls.
- `chunks="auto"` defers to dask for chunking from zarr metadata.
- No try/except: failure to open is fatal and propagates to `handle_tool_errors` middleware.

#### 3.3.3 `clip_ds_to_geojson()`

```python
def clip_ds_to_geojson(
    ds: xr.Dataset, geojson_geom: dict
) -> xr.Dataset:
    """Clip dataset to GeoJSON geometry via bbox + rioxarray."""
    geom = shape(geojson_geom)
    minx, miny, maxx, maxy = geom.bounds

    # Determine spatial dimension names
    if "lon" in ds.dims:
        x_dim, y_dim = "lon", "lat"
    else:
        x_dim, y_dim = "x", "y"

    # Detect y-axis direction (ascending vs descending)
    y_vals = ds[y_dim].values
    if y_vals[0] < y_vals[-1]:
        # Ascending y
        y_slice = slice(miny, maxy)
    else:
        # Descending y
        y_slice = slice(maxy, miny)

    # Bbox slice (fast, reduces data volume)
    ds_bbox = ds.sel(
        {x_dim: slice(minx, maxx), y_dim: y_slice}
    )

    # Set spatial dims for rioxarray
    ds_bbox = ds_bbox.rio.set_spatial_dims(
        x_dim=x_dim, y_dim=y_dim
    )

    # Set CRS if not already set
    if not ds_bbox.rio.crs:
        ds_bbox = ds_bbox.rio.write_crs("EPSG:4326")

    # Decompose GeometryCollection into individual geometries
    if geojson_geom.get("type") == "GeometryCollection":
        clip_geoms = [
            mapping(g) for g in geom.geoms
        ]
    else:
        clip_geoms = [geojson_geom]

    clipped = ds_bbox.rio.clip(
        clip_geoms, crs="EPSG:4326", drop=True
    )
    return clipped
```

**Key fixes from validation**:
- Handles `lon`/`lat` vs `x`/`y` dimension names.
- Detects ascending vs descending y-axis.
- Decomposes `GeometryCollection` into individual geometries for `rio.clip`.
- Sets spatial dims explicitly for rioxarray.

#### 3.3.4 `run_analysis()`

```python
def run_analysis(
    geojson_geometry: dict, name: str
) -> pd.DataFrame:
    """Compute deforestation metrics for a single AOI.

    Returns single-row DataFrame with columns:
    name, total_area, sbtn_area, sbtn_loss_area, jrc_area,
    jrc_loss_area, indig_area, alert_area, sbtn_alert_area,
    jrc_alert_area
    """
    datasets = get_datasets()
    alert_start = os.environ.get(
        "GFW_PRO_ALERT_START_DATE", DEFAULT_ALERT_START_DATE
    )
    alert_start_int = int(
        datetime.strptime(alert_start, "%Y-%m-%d")
        .strftime("%Y%m%d")
    )

    # Clip all datasets to AOI
    sbtn = clip_ds_to_geojson(datasets["sbtn"], geojson_geometry)
    jrc = clip_ds_to_geojson(datasets["jrc"], geojson_geometry)
    loss = clip_ds_to_geojson(
        datasets["mergedLoss"], geojson_geometry
    )
    intdist = clip_ds_to_geojson(
        datasets["intdist"], geojson_geometry
    )

    # Memory guard: check clipped size
    total_size = sum(
        np.prod(v.shape) for v in sbtn.data_vars.values()
    )
    if total_size > MAX_PIXELS:
        raise ValueError(
            f"AOI '{name}' is too large ({total_size:,} pixels "
            f"after clipping). Maximum is {MAX_PIXELS:,}. "
            "Please select a smaller area."
        )

    # Pixel area in hectares (from sbtn.area.zarr)
    # NOTE: Variable name "area" must be verified against
    # actual zarr contents. Inspect with ds.data_vars.
    pixel_area = sbtn["area"].values

    # Total area
    total_area = float(np.nansum(pixel_area))

    # SBTN natural forest mask
    # NOTE: Variable name "sbtn" must be verified.
    sbtn_mask = sbtn["sbtn"].values > 0
    sbtn_area_val = float(np.nansum(pixel_area[sbtn_mask]))

    # JRC forest mask
    # NOTE: Variable name "jrc" must be verified.
    jrc_mask = jrc["jrc"].values > 0
    jrc_area_val = float(np.nansum(pixel_area[jrc_mask]))

    # Tree cover loss 2021-2024
    # NOTE: Variable name "mergedLoss" must be verified.
    loss_vals = loss["mergedLoss"].values
    tcl_mask = (loss_vals >= 2021) & (loss_vals <= 2024)

    sbtn_loss_area = float(
        np.nansum(pixel_area[sbtn_mask & tcl_mask])
    )
    jrc_loss_area = float(
        np.nansum(pixel_area[jrc_mask & tcl_mask])
    )

    # Indigenous/community lands
    # NOTE: Variable name "indig" must be verified.
    indig_mask = sbtn["indig"].values > 0
    indig_area_val = float(np.nansum(pixel_area[indig_mask]))

    # Disturbance alerts since alert_start_date
    # NOTE: Variable names "date" and "conf" must be verified.
    # Assumed: date is YYYYMMDD integer, conf >= 2 = high/highest
    alert_dates = intdist["date"].values
    alert_conf = intdist["conf"].values
    alert_mask = (alert_conf >= 2) & (
        alert_dates >= alert_start_int
    )
    alert_area_val = float(np.nansum(pixel_area[alert_mask]))

    sbtn_alert_area = float(
        np.nansum(pixel_area[alert_mask & sbtn_mask])
    )
    jrc_alert_area = float(
        np.nansum(pixel_area[alert_mask & jrc_mask])
    )

    return pd.DataFrame([{
        "name": _sanitize_csv_field(name),
        "total_area": round(total_area, 4),
        "sbtn_area": round(sbtn_area_val, 4),
        "sbtn_loss_area": round(sbtn_loss_area, 4),
        "jrc_area": round(jrc_area_val, 4),
        "jrc_loss_area": round(jrc_loss_area, 4),
        "indig_area": round(indig_area_val, 4),
        "alert_area": round(alert_area_val, 4),
        "sbtn_alert_area": round(sbtn_alert_area, 4),
        "jrc_alert_area": round(jrc_alert_area, 4),
    }])
```

**CRITICAL IMPLEMENTATION NOTE**: The variable names within each zarr dataset (`sbtn["sbtn"]`, `sbtn["area"]`, `jrc["jrc"]`, `loss["mergedLoss"]`, `intdist["date"]`, `intdist["conf"]`, `sbtn["indig"]`) are assumed from the PROMPT and query3.py reference. The implementer **MUST** run a diagnostic to discover actual variable names:

```python
import xarray as xr
for name, path in S3_ZARR_PATHS.items():
    ds = xr.open_zarr(path)
    print(f"{name}: dims={list(ds.dims)}, vars={list(ds.data_vars)}")
```

Adjust all variable name references based on the output. **Do not proceed with the rest of the implementation until variable names are confirmed.**

#### 3.3.5 Helper Functions

```python
def _sanitize_csv_field(value: str) -> str:
    """Strip leading characters that could trigger CSV injection."""
    return re.sub(r'^[=+\-@]+', '', value)


def dataframes_to_csv(dfs: list[pd.DataFrame]) -> str:
    """Concatenate DataFrames to CSV string with version header."""
    combined = pd.concat(dfs, ignore_index=True)
    version_lines = [
        f"# {k}: {v}" for k, v in DATA_VERSIONS.items()
    ]
    header = "\n".join(version_lines) + "\n"
    return header + combined.to_csv(index=False)
```

#### 3.3.6 Tool Function

```python
@tool("gfw_pro_analysis")
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    state: Annotated[Dict, InjectedState] = None,
) -> Command:
    """Run GFW Pro deforestation and disturbance alert analysis
    for the current AOI. Returns SBTN/JRC forest area, tree
    cover loss 2021-2024, indigenous lands area, and integrated
    disturbance alerts. Results are provided as a downloadable
    CSV."""
    logger.info("GFW-PRO-ANALYSIS-TOOL")

    # 1. Get AOI list
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
                        content=(
                            "No AOI selected. Please select "
                            "an area of interest first using "
                            "pick_aoi."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # 2. Fetch geometries concurrently
    geo_data_list = await asyncio.gather(
        *[
            get_geometry_data(
                aoi["source"], aoi["src_id"]
            )
            for aoi in aois
        ]
    )

    # 3. Validate geometry results
    valid_pairs = []
    for aoi, geo_data in zip(aois, geo_data_list):
        if (
            geo_data is None
            or geo_data.get("geometry") is None
        ):
            logger.warning(
                "No geometry found for AOI",
                aoi_name=aoi.get("name"),
            )
            continue
        valid_pairs.append((aoi, geo_data))

    if not valid_pairs:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Could not retrieve geometry "
                            "for any selected AOIs."
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # 4. Run analysis per AOI (sequential, non-blocking)
    dfs = []
    failed_aois = []
    for aoi, geo_data in valid_pairs:
        aoi_name = aoi.get("name", "Unknown")
        geojson = geo_data["geometry"]
        try:
            df = await asyncio.to_thread(
                run_analysis, geojson, aoi_name
            )
            dfs.append(df)
        except Exception as e:
            logger.warning(
                "Analysis failed for AOI",
                aoi_name=aoi_name,
                error=str(e),
            )
            failed_aois.append(aoi_name)

    if not dfs:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=(
                            "Analysis failed for all AOIs. "
                            f"Errors: {', '.join(failed_aois)}"
                        ),
                        tool_call_id=tool_call_id,
                    )
                ],
            },
        )

    # 5. Build CSV
    csv_string = dataframes_to_csv(dfs)

    # 6. Summary message
    parts = [
        f"GFW Pro analysis complete for "
        f"{len(dfs)} AOI(s).",
    ]
    if failed_aois:
        parts.append(
            f"Failed for: {', '.join(failed_aois)}."
        )
    parts.append(
        "Metrics: total area, SBTN forest, SBTN loss, "
        "JRC forest, JRC loss, indigenous lands, "
        "alert area, SBTN alerts, JRC alerts."
    )
    parts.append("Results available as downloadable CSV.")

    return Command(
        update={
            "gfw_pro_csv": csv_string,
            "messages": [
                ToolMessage(
                    content=" ".join(parts),
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )
```

**Key design decisions**:
- Sequential `asyncio.to_thread()` per AOI (not parallel) to avoid memory pressure from concurrent zarr reads.
- Per-AOI try/except so one failure does not abort the entire batch.
- Geometry fetch uses `asyncio.gather` (async I/O, not threaded).
- Missing geometries logged and skipped.
- No AOI returns early with guidance message (not exception).

---

### 3.4 Register the Tool

#### 3.4.1 `src/agent/tools/__init__.py`

Add import and export:

```python
from .gfw_pro_analysis import gfw_pro_analysis

__all__ = [
    "pick_aoi",
    "pick_dataset",
    "pull_data",
    "generate_insights",
    "get_capabilities",
    "gfw_pro_analysis",
]
```

#### 3.4.2 `src/agent/graph.py` - Imports

Change the import block (currently lines 17-23):

```python
# Current:
from src.agent.tools import (
    generate_insights,
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
)

# Change to:
from src.agent.tools import (
    generate_insights,
    get_capabilities,
    gfw_pro_analysis,
    pick_aoi,
    pick_dataset,
    pull_data,
)
```

#### 3.4.3 `src/agent/graph.py` - Tools List

Change the tools list (currently lines 113-119):

```python
# Current:
tools = [
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
    generate_insights,
]

# Change to:
tools = [
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
    generate_insights,
    gfw_pro_analysis,
]
```

#### 3.4.4 `src/agent/graph.py` - Prompt Update

In the `get_prompt()` function, locate the TOOLS section (within the large prompt string). Add after the `generate_insights` entry:

```
- gfw_pro_analysis: Run GFW Pro deforestation and disturbance alert analysis for the current AOI. Returns SBTN/JRC forest area, tree cover loss 2021-2024, indigenous lands area, and disturbance alerts as a downloadable CSV. Requires AOI selected first.
```

In the WORKFLOW section, add an alternative path after AOI selection:

```
If user asks for 'GFW Pro analysis', 'deforestation metrics', or 'GFW Pro analytical results': call gfw_pro_analysis (requires AOI selected first via pick_aoi).
```

**Verify**: `python -c "from src.agent.graph import fetch_zeno"` succeeds.

---

### 3.5 Implementation Order Summary

| Step | File(s) | Depends On | Verify Command |
|---|---|---|---|
| 0 | `Dockerfile` | None | `docker build .` |
| 1 | `pyproject.toml` | Step 0 (for Docker) | `python -c "import xarray, zarr, rioxarray, dask"` |
| 2 | `src/agent/state.py` | None | `python -c "from src.agent.state import AgentState"` |
| 3 | `src/agent/tools/gfw_pro_analysis.py` | Steps 1, 2 | `python -c "from src.agent.tools.gfw_pro_analysis import gfw_pro_analysis"` |
| 4 | `src/agent/tools/__init__.py`, `src/agent/graph.py` | Step 3 | `python -c "from src.agent.tools import gfw_pro_analysis"` |
| 5 | `tests/tools/test_gfw_pro_analysis.py` | Steps 3, 4 | `uv run pytest tests/tools/test_gfw_pro_analysis.py -v` |

---

## 4. Testing Strategy

### Test File: `tests/tools/test_gfw_pro_analysis.py`

#### 4.0 Test Boilerplate

```python
"""Tests for GFW Pro deforestation analysis tool."""

import uuid
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.agent.tools.gfw_pro_analysis import (
    clip_ds_to_geojson,
    dataframes_to_csv,
    gfw_pro_analysis,
    get_datasets,
    run_analysis,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


# Override DB fixtures (no database needed)
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

#### 4.1 Unit Tests

**test_get_datasets_caches_results**:
- Patch `xr.open_zarr` to return `MagicMock()`.
- Reset `_datasets_cache` to `None`.
- Call `get_datasets()` twice.
- Assert `xr.open_zarr` called exactly 4 times (once per dataset), not 8.

**test_get_datasets_local_path**:
- Set `GFW_PRO_DATA_PATH=/tmp/test_zarr` via `monkeypatch.setenv`.
- Patch `xr.open_zarr`.
- Reset cache, call `get_datasets()`.
- Assert all 4 `open_zarr` calls use paths starting with `/tmp/test_zarr/`.
- Assert `intdist_date_conf.zarr` (not empty string) is in the path for the intdist dataset.

**test_get_datasets_s3_fallback**:
- Ensure `GFW_PRO_DATA_PATH` is unset via `monkeypatch.delenv`.
- Patch `xr.open_zarr`.
- Reset cache, call `get_datasets()`.
- Assert all 4 calls use `s3://` URIs.

**test_clip_ds_to_geojson_basic**:
- Create synthetic `xr.Dataset` with known `x`, `y` coords and a data variable.
- Clip to a small polygon.
- Assert result has correct spatial extent and data values.

**test_clip_ds_to_geojson_geometry_collection**:
- Create synthetic dataset.
- Clip with a `GeometryCollection` containing 2 polygons.
- Assert result covers both polygon extents.

**test_run_analysis_returns_correct_columns**:
- Patch `get_datasets()` to return 4 synthetic xr.Datasets with matching grids.
- Each dataset has the expected variable names and small (10x10) arrays.
- Call `run_analysis(geojson, "test_aoi")`.
- Assert result is a 1-row DataFrame with all 10 expected columns.
- Assert all numeric values are rounded to 4 decimal places.

**test_run_analysis_too_large_aoi**:
- Patch `get_datasets()` and `clip_ds_to_geojson` to return a dataset exceeding `MAX_PIXELS`.
- Assert `run_analysis` raises `ValueError` with "too large" message.

**test_dataframes_to_csv_format**:
- Create 2 single-row DataFrames.
- Call `dataframes_to_csv([df1, df2])`.
- Assert CSV starts with `# TCL:` header lines.
- Assert 2 data rows (plus header row) after the comment lines.

**test_sanitize_csv_field**:
- Assert `_sanitize_csv_field("=CMD()")` returns `"CMD()"`.
- Assert `_sanitize_csv_field("Normal Name")` returns `"Normal Name"`.

#### 4.2 Tool Integration Tests

**test_tool_no_aoi_selected**:
```python
async def test_tool_no_aoi_selected():
    command = await gfw_pro_analysis.ainvoke({
        "type": "tool_call",
        "name": "gfw_pro_analysis",
        "id": str(uuid.uuid4()),
        "args": {"state": {}},
    })
    msg = command.update["messages"][0]
    assert "No AOI selected" in msg.content
```

**test_tool_single_aoi**:
- Patch `get_geometry_data` to return `{"geometry": <test_polygon>}`.
- Patch `run_analysis` to return a mock DataFrame.
- Invoke with state containing single AOI in `aoi_selection`.
- Assert `"gfw_pro_csv"` in `command.update`.
- Assert CSV string contains expected header and data.

**test_tool_multi_aoi**:
- Same as above but with 2 AOIs.
- Assert CSV has 2 data rows.

**test_tool_partial_geometry_failure**:
- Patch `get_geometry_data` to return `None` for first AOI, valid geometry for second.
- Assert tool succeeds with 1-row CSV.

**test_tool_runs_in_thread**:
- Patch `asyncio.to_thread` with `AsyncMock(return_value=mock_df)`.
- Invoke tool.
- Assert `asyncio.to_thread` was called.

**test_tool_analysis_failure_per_aoi**:
- Patch `run_analysis` to raise for first AOI, succeed for second.
- Assert tool returns 1-row CSV and message mentions failed AOI.

#### 4.3 IDN Validation Test (Conditional)

```python
@pytest.mark.skipif(
    not os.environ.get("GFW_PRO_DATA_PATH"),
    reason="Requires local zarr data",
)
async def test_idn_reference_values():
    """Validate against IDN test case from query3.py."""
    # IDN test geometry (a specific admin boundary)
    geo = await get_geometry_data("gadm", "IDN.12.26_1")
    df = await asyncio.to_thread(
        run_analysis, geo["geometry"], "IDN_test"
    )
    assert abs(df["sbtn_area"].iloc[0] - 994.6) < 10
    assert abs(df["sbtn_loss_area"].iloc[0] - 59.95) < 5
    assert abs(df["total_area"].iloc[0] - 1006) < 10
```

This test requires both local zarr data and a database with GADM geometries. It is excluded from CI.

---

## 5. Risk Register

| Risk | Severity | Likelihood | Mitigation |
|---|---|---|---|
| Zarr variable names differ from assumed names | **High** | Medium | Implementer MUST run diagnostic script (Section 3.3.4 note) before coding. All variable references are marked with `# NOTE` comments. |
| `rioxarray` requires GDAL system library not in Dockerfile | **High** | High (certain) | Step 0 adds `libgdal-dev` to Dockerfile. Verify Docker build succeeds before proceeding. |
| Large AOI causes OOM | **High** | Low | MAX_PIXELS guard in `run_analysis` rejects oversized clips. Bbox slice reduces data before full clip. |
| Alert date encoding differs from assumed YYYYMMDD | **High** | Medium | Must verify against actual zarr data. If different (e.g., days since epoch), adjust the comparison in `run_analysis`. |
| Y-axis direction varies across datasets | **Medium** | Medium | `clip_ds_to_geojson` detects ascending/descending y and adjusts slice. |
| Coordinate names (`x`/`y` vs `lon`/`lat`) | **Medium** | Medium | `clip_ds_to_geojson` checks for `lon` dim and adjusts. |
| S3 first-access latency (10-30s) | **Low** | High | Expected. Module cache ensures one-time cost. Document in tool response. |
| Thread safety of `get_datasets()` | **Low** | Low | `threading.Lock` with double-check pattern prevents duplicate opens. |
| `zarr` v3 breaking changes | **Medium** | Low | Pinned to `zarr>=2.18.0,<3`. |
| Frontend cannot render CSV download | **Medium** | Certain | Out of scope per requirements. State key is set. Follow-up issue needed for `frontend/utils.py`. |
| Array shape mismatch across datasets | **Medium** | Low | All GFW Pro datasets share same 10m grid. If shapes differ, numpy raises clear error caught by middleware. |
| `fsspec` version conflict | **Low** | Low | Not added explicitly; transitive via `s3fs`. |
