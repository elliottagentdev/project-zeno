# Plan Validation Report

## 1. Requirements Coverage Matrix

| # | Requirement (from PROMPT.md) | Addressed in Plan? | Where in Plan | Testable? | Notes |
|---|---|---|---|---|---|
| R1 | New module `src/agent/tools/gfw_pro_analysis.py` | Yes | Section 4 | Yes | Full implementation provided |
| R2 | 4 zarr data sources (sbtn, jrc, mergedLoss, intdist) | Yes | Section 4.1 (S3_ZARR_PATHS) | Yes | S3 URIs match PROMPT |
| R3 | `GFW_PRO_DATA_PATH` env var with S3 fallback | Yes | Section 4.2 (get_datasets) | Yes | |
| R4 | `GFW_PRO_ALERT_START_DATE` env var, default 2025-01-01 | Yes | Section 4.1/4.4 | Yes | |
| R5 | AWS credential env vars | Yes (implicit) | Section 6 table (S3 credentials) | Yes | s3fs picks these up automatically |
| R6 | 10 output metric columns (name + 9 metrics) | Yes | Section 4.4 | Yes | All columns present |
| R7 | Values in hectares, 4 decimal places | Yes | Section 4.4 (round(..., 4)) | Yes | |
| R8 | `get_datasets()` with module-level singleton cache | Yes | Section 4.2 | Yes | |
| R9 | `clip_ds_to_geojson()` with bbox slice + rioxarray clip | Yes | Section 4.3 | Yes | |
| R10 | `run_analysis()` computing all 9 metrics | Yes | Section 4.4 | Yes | Variable names flagged as needing verification |
| R11 | `dataframes_to_csv()` with version header | Yes | Section 4.5 | Yes | |
| R12 | `asyncio.to_thread()` for non-blocking | Yes | Section 4.6 | Yes | |
| R13 | Data version comments in CSV header | Yes | Section 4.5 (DATA_VERSIONS) | Yes | Versions match PROMPT |
| R14 | `@tool("gfw_pro_analysis")` following existing pattern | Yes | Section 4.6 | Yes | |
| R15 | Read `state["aoi"]` for AOI info | Yes | Section 4.6 | Yes | Uses aoi_selection with aoi fallback |
| R16 | Multi-AOI support via `aoi_selection["aois"]` | Yes | Section 4.6 | Yes | |
| R17 | Call `get_geometry_data(source, src_id)` | Yes | Section 4.6 | Yes | Uses asyncio.gather |
| R18 | Return Command with `gfw_pro_csv` state key | Yes | Section 4.6 | Yes | |
| R19 | Add tool to `tools` list in `graph.py` | Yes | Section 5 | Yes | |
| R20 | Add `gfw_pro_csv: Optional[str]` to AgentState | Yes | Section 3 | Yes | |
| R21 | Add deps to Pipfile (xarray, zarr, etc.) | Yes | Section 2 | Yes | Correctly targets pyproject.toml instead of Pipfile |
| AC1 | `run_analysis()` produces correct IDN test values | Partially | Section 7 (test 6) | Conditional | Gated behind data availability; not a mandatory CI test |
| AC2 | Tool callable from agent (in tools list) | Yes | Section 5 | Yes | |
| AC3 | `gfw_pro_csv` in state after tool runs | Yes | Section 4.6 | Yes | |
| AC4 | Multi-AOI produces multi-row CSV | Yes | Section 7 (test 10) | Yes | |
| AC5 | Analysis runs in thread pool | Yes | Section 4.6, 7 (test 12) | Yes | |
| AC6 | S3 and local path modes both work | Yes | Section 4.2, 7 (tests 2-3) | Yes | |

### Gaps

- **Frontend download rendering**: PROMPT says "provide a downloadable CSV". Plan acknowledges frontend changes are needed (Section 10, item 3) but explicitly defers them. The `gfw_pro_csv` state key is set but nothing renders a download button. This is a functional gap -- the user cannot actually download the CSV without frontend work.
- **PROMPT says "Pipfile"**: The PROMPT incorrectly references `Pipfile`, but the project uses `pyproject.toml`. The plan correctly handles this but does not call out the discrepancy.

---

## 2. Codebase Fact-Check

### Verified Correct

| Claim | Status | Evidence |
|---|---|---|
| `src/agent/state.py` contains AgentState TypedDict | Correct | File verified, lines 25-45 |
| `src/agent/tools/__init__.py` exports 5 tools | Correct | Lines 1-13 verified |
| `src/agent/graph.py` has `tools` list at lines 113-119 | Correct | Lines 113-119 verified |
| `pyproject.toml` uses `[project].dependencies` (not Pipfile) | Correct | pyproject.toml verified |
| `s3fs==2025.3.0` already in dependencies | Correct | Line 35 of pyproject.toml |
| `pandas==2.2.3` already in dependencies | Correct | Line 36 of pyproject.toml |
| `boto3==1.38.27` already in dependencies | Correct | Line 43 of pyproject.toml |
| `fiona==1.10.1` already in dependencies | Correct | Line 19 of pyproject.toml |
| `geopandas==1.0.1` already in dependencies | Correct | Line 20 of pyproject.toml |
| `get_geometry_data(source, src_id)` signature | Correct | `geocoding_helpers.py` line 64 |
| `get_geometry_data` returns dict with `geometry` key | Correct | Lines 127-133, 174-180 |
| `AgentState` does NOT have `Optional` imported | Correct | `state.py` imports only `Annotated, Sequence` from `typing` |
| Test pattern uses `pytestmark = pytest.mark.asyncio(loop_scope="session")` | Correct | `test_pull_data.py` line 17 |
| Module-level singleton cache pattern exists (e.g., `retriever_cache`) | Correct | Referenced in recon docs, confirmed in `pick_dataset.py` |
| `handle_tool_errors` middleware wraps tool calls | Correct | `graph.py` lines 173-182 |

### Factual Errors Found

#### Error 1: `InjectedToolCallId` import path

**Plan claims** (Section 4.1, line 88):
```python
from langchain_core.tools import InjectedToolCallId, tool
```

**Codebase actually uses** (all existing tools):
```python
from langchain_core.tools import tool
from langchain_core.tools.base import InjectedToolCallId
```

`InjectedToolCallId` is imported from `langchain_core.tools.base`, NOT from `langchain_core.tools`. These are separate imports in every existing tool file (`pull_data.py`, `pick_aoi.py`, `pick_dataset.py`, `generate_insights.py`).

**Severity**: Medium. The import `from langchain_core.tools import InjectedToolCallId` may work (if re-exported), but deviates from the established pattern and could fail.

#### Error 2: Tool parameter default values

**Plan claims** (Section 4.6):
```python
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[AgentState, InjectedState],
) -> Command:
```

**Codebase convention** (all existing tools):
```python
tool_call_id: Annotated[str, InjectedToolCallId] = None,
state: Annotated[Dict, InjectedState] = None,
```

All existing tools use `= None` defaults for injected parameters. The plan omits these defaults. This may cause issues with LangGraph's tool invocation infrastructure.

**Severity**: Medium. LangGraph may handle this correctly, but it's inconsistent with every other tool in the codebase.

#### Error 3: State type annotation

**Plan claims**: `state: Annotated[AgentState, InjectedState]`

**Codebase convention**: `state: Annotated[Dict, InjectedState]`

All existing tools (`pull_data.py`, `generate_insights.py`) use `Dict`, not `AgentState`. Both work functionally (LangGraph injects the full state dict regardless), but the plan deviates from the established pattern.

**Severity**: Low. Functionally equivalent, but inconsistent.

#### Error 4: graph.py import style mismatch

**Plan claims** (Section 4.1):
```python
from langchain_core.messages import ToolMessage
```

**graph.py actually uses**:
```python
from langchain.messages import ToolMessage
```

The plan's new module imports from `langchain_core.messages`, which is fine for the new module itself (other tools do this). But Section 5 implies modifying `graph.py` imports without noting the different import convention used there. This is not a bug but could cause confusion.

**Severity**: Low.

#### Error 5: Dockerfile missing GDAL system library

**Plan's Risk Register** (Section 9) correctly identifies that `rioxarray` requires `libgdal-dev`. However, the **actual Dockerfile** (`/mnt/e/agentdev/projects/project-zeno/Dockerfile`) does NOT include `libgdal-dev`:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    libpq-dev \
    ca-certificates \
    libexpat1 \
```

The plan lists this as a risk but does NOT include a Dockerfile modification step in the Implementation Order (Section 8). This will cause `uv sync` or `pip install rioxarray` to fail at build time if GDAL is not present.

**Severity**: High. The Docker build will fail without this change. This should be an explicit implementation step, not just a risk note.

#### Error 6: `get_geometry_data` requires database connection

The plan calls `get_geometry_data` via `asyncio.gather` (Section 4.6) but does not mention that this function requires an active database connection pool (via `get_session_from_pool()`). The function opens a database session internally. If the global pool is not initialized (e.g., in testing or certain deployment scenarios), this will fail with a connection error.

**Severity**: Medium. The pool is initialized at app startup, so this works at runtime. But it affects test mocking strategy -- tests must either mock `get_geometry_data` entirely or ensure the pool is available.

### Utilities the Plan Reinvents

No cases found where the plan reinvents existing utilities. The plan correctly reuses:
- `get_geometry_data` from `geocoding_helpers.py`
- `get_logger` from `logging_config.py`
- Tool registration pattern from `__init__.py` and `graph.py`
- Module-level caching pattern from `pick_dataset.py`

---

## 3. Ambiguity Audit

### Section 4.1 (Constants & Configuration)

1. **Zarr variable names are assumed, not verified.** The plan assumes variable names like `sbtn["sbtn"]`, `sbtn["area"]`, `jrc["jrc"]`, `loss["mergedLoss"]`, `intdist["date"]`, `intdist["conf"]`, `sbtn["indig"]`. The plan acknowledges this in Section 4.4 (IMPORTANT note) and Risk Register, but a developer reading the plan cannot implement without access to the actual zarr files to discover the real variable names. **This is the single largest ambiguity in the entire plan.**

2. **Coordinate dimension names (`x`/`y` vs `lon`/`lat`)**: The plan assumes `x` and `y` for `ds.sel(x=slice(...), y=slice(...))`. The Risk Register notes this but does not specify what the fallback code should look like.

3. **Alert date encoding**: The plan assumes `intdist["date"]` contains integer dates in `YYYYMMDD` format. The Risk Register flags this but offers no fallback.

### Section 4.2 (get_datasets)

4. **Local path construction**: The plan derives local filenames from S3 URIs via `s3_uri.rsplit("/", 1)[-1]`. For the `intdist` dataset, the S3 URI is `s3://gfwpro-users/op-external-user/v3/intdist_date_conf.zarr/` (trailing slash). `rsplit("/", 1)[-1]` on this URI would return an empty string `""`, not `intdist_date_conf.zarr`. The local path would be `os.path.join(base_path, "")` which just returns `base_path`. **This is a bug.**

### Section 4.3 (clip_ds_to_geojson)

5. **Handling GeometryCollection**: `get_geometry_data` can return `GeometryCollection` for custom areas with multiple geometries (see `geocoding_helpers.py` lines 118-123). `shapely.geometry.shape()` handles this, but `rio.clip([geojson_geom])` expects a list of geometry-like objects, not a GeometryCollection dict. The plan does not address how to handle GeometryCollection inputs.

6. **CRS assumption**: The plan assumes all zarr datasets are EPSG:4326. If any dataset uses a different CRS, the clip will produce wrong results silently.

### Section 4.4 (run_analysis)

7. **Pixel area source**: The plan uses `sbtn["area"].values` for pixel area across all metrics, including JRC and alert calculations. This assumes the pixel grids align perfectly across all 4 zarr datasets. If they have different resolutions or extents, array broadcasting will fail or produce incorrect results.

8. **Array shape alignment**: The plan applies boolean masks across different datasets (e.g., `pixel_area[sbtn_mask & tcl_mask]`). This requires `sbtn`, `jrc`, `loss`, and `intdist` clipped arrays to have identical shapes. After clipping to the same geometry, they may differ if the source datasets have different resolutions or grid alignments.

9. **`.values` forces full materialization**: Calling `.values` on dask-backed arrays loads all data into memory. For a large AOI, this could consume significant memory. The plan's bbox-first approach mitigates this, but the plan does not state the expected memory envelope or set any size guard.

### Section 4.6 (Tool Function)

10. **`asyncio.gather` for `get_geometry_data`**: The plan uses `asyncio.gather` to fetch all geometries concurrently. Since `get_geometry_data` opens a database session from the global pool for each call, many AOIs could exhaust the connection pool. The plan does not discuss connection pool limits.

11. **Error handling for `run_analysis`**: If `run_analysis` raises an exception for one AOI in a multi-AOI batch, the entire tool fails. The plan skips failed geometry fetches but does not handle analysis failures per-AOI.

### Section 5 (Tool Registration)

12. **Prompt update content**: The plan says to add tool documentation to `get_prompt()` but does not provide the exact location in the prompt string where the new lines should be inserted. The prompt has specific TOOLS and WORKFLOW sections. A developer must read the prompt to find the right insertion point.

### Section 7 (Testing)

13. **Test invocation pattern**: The plan shows tests using `await tool.ainvoke({...})` but does not specify the exact `ainvoke` input format. From `test_pull_data.py`, the format is `{"type": "tool_call", "name": "...", "id": "...", "args": {...}}`. The plan should specify this.

14. **No test for GeometryCollection input**: Tests do not cover the case where `get_geometry_data` returns a GeometryCollection.

### Section 8 (Implementation Order)

15. **Missing Dockerfile step**: The implementation order has no step for modifying the Dockerfile to add `libgdal-dev`. Without this, Step 1 (`uv sync`) may succeed locally (if GDAL is already installed) but Docker builds will fail.

---

## 4. Edge Cases & Risks

### Unhandled Edge Cases

1. **Empty geometry from `get_geometry_data`**: The function can return a dict with `"geometry": None` (e.g., if `custom_area.geometries` is empty or JSON parsing fails). The plan checks `geo_data is None or geo_data.get("geometry") is None` which correctly handles this.

2. **Trailing slash in S3 URI causing empty filename**: As noted in Ambiguity #4, the `intdist` S3 URI has a trailing slash. `rsplit("/", 1)[-1]` returns `""`. **This is a concrete bug that will cause local path mode to fail for the intdist dataset.**

3. **Very large AOI (country-level or larger)**: Even with bbox slicing, a country-sized AOI at 10m resolution could load gigabytes of data. The plan notes this in the Risk Register but provides no concrete guard (e.g., max area check, warning to user, or chunk-by-chunk processing).

4. **Concurrent tool invocations**: If two users invoke `gfw_pro_analysis` simultaneously, both will call `get_datasets()`. The first call initializes the cache; the second will find it populated. However, if both start before either completes, both may simultaneously open all 4 zarr datasets. The plan uses a simple `if _datasets_cache is not None` check which is not thread-safe. Since `run_analysis` is called via `asyncio.to_thread()`, multiple threads could race on `get_datasets()`.

5. **Dataset cache invalidation**: The module-level cache is never invalidated. If the zarr data on S3 is updated, the cached Dataset objects will not reflect changes until the process restarts. This is acceptable for the stated use case but should be documented.

6. **NaN handling in metrics**: `np.nansum` correctly treats NaN as zero, so areas with NoData pixels will not inflate totals. However, if an entire clipped region is NaN (e.g., geometry falls outside the data extent), all metrics will be 0.0 rather than indicating "no data available". The plan handles this (Section 6 table: "Valid row with 0.0 values") but this could be misleading to users.

7. **Custom area with GeometryCollection**: The `rioxarray.clip()` function expects a list of geometry-like objects. A GeoJSON `GeometryCollection` dict is not directly supported. The plan should either decompose the GeometryCollection into individual geometries or convert it to a single MultiPolygon before clipping.

### Unhandled Error Paths

8. **S3 throttling / rate limiting**: Large zarr datasets may require many S3 GET requests. If S3 throttles the requests, `xr.open_zarr` or `.values` will raise. The plan has no retry logic.

9. **Timeout for long-running analysis**: A very large AOI could take minutes. There is no timeout mechanism. The FastAPI request may time out before the analysis completes.

10. **`xr.open_zarr` with invalid local path**: If `GFW_PRO_DATA_PATH` is set but points to a nonexistent directory, `open_zarr` will raise `FileNotFoundError`. This propagates to the error middleware, but the error message may be cryptic to the user.

11. **`rioxarray` import side effect**: The plan imports `rioxarray` with `# noqa: F401` to register the `.rio` accessor. If rioxarray is not installed (e.g., Dockerfile missing GDAL), this import will fail at module load time, preventing the entire tool from being registered.

### Internal Contradictions

12. **Plan says `fsspec` not needed explicitly (Section 10, item 5)**: But the PROMPT lists `fsspec` as a dependency to add. The plan's decision to omit it is reasonable but contradicts the PROMPT spec.

13. **Plan says `shapely` is "already present"**: The `pyproject.toml` does NOT list `shapely` as a direct dependency. It is a transitive dependency via `geopandas`. The plan imports `from shapely.geometry import shape` which relies on this transitive dependency. This works but is fragile -- if `geopandas` is ever removed, `shapely` would disappear.

### Security Concerns

14. **S3 credentials in environment**: The plan uses `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY` from environment variables. This is standard practice but these credentials provide read access to the `gfwpro-users` S3 bucket. If the server is compromised, these credentials could be used to access other data in the bucket.

15. **No input validation on geometry**: The geometry from `get_geometry_data` is passed directly to `shapely.shape()` and `rioxarray.clip()`. A maliciously crafted geometry (e.g., extremely complex polygon with millions of vertices) could cause excessive CPU/memory usage. Since geometry comes from the database (not direct user input), this risk is low but present for custom areas.

16. **CSV injection**: The `name` field from the AOI is included directly in the CSV output. If a custom AOI name contains CSV injection payloads (e.g., `=CMD(...)`), they could be executed when the CSV is opened in Excel. The plan does not sanitize the name field.
