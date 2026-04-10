# Relevant Code Reconnaissance

## Summary

This document identifies the specific files, functions, data models, and integration points relevant to adding the `gfw_pro_analysis` agent tool.

---

## 1. Files to Modify

### `src/agent/state.py` — Add `gfw_pro_csv` to `AgentState`

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/state.py`

Current `AgentState` TypedDict (lines 25–46):

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_persona: str

    # pick-aoi tool
    aoi: dict
    subtype: str
    aoi_selection: AOISelection

    # pick-dataset tool
    dataset: dict

    # pull-data tool
    start_date: str
    end_date: str
    statistics: Annotated[list[Statistics], operator.add]

    # generate-insights tool
    insights: list
    charts_data: list
    codeact_parts: list[CodeActPart]
```

**Change needed:** Add `gfw_pro_csv: Optional[str]` field to `AgentState`. Import `Optional` from `typing` if not already imported (currently not imported in this file — it uses `Annotated` from `typing_extensions`). Must add `from typing import Optional`.

---

### `src/agent/tools/__init__.py` — Register new tool

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/__init__.py`

Current contents (lines 1–13):

```python
from .generate_insights import generate_insights
from .get_capabilities import get_capabilities
from .pick_aoi import pick_aoi
from .pick_dataset import pick_dataset
from .pull_data import pull_data

__all__ = [
    "pick_aoi",
    "pick_dataset",
    "pull_data",
    "generate_insights",
    "get_capabilities",
]
```

**Change needed:** Add `from .gfw_pro_analysis import gfw_pro_analysis` and `"gfw_pro_analysis"` to `__all__`.

---

### `src/agent/graph.py` — Add tool to agent tools list

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/graph.py`

Current `tools` list (lines 113–119):

```python
tools = [
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
    generate_insights,
]
```

Current imports (lines 17–23):

```python
from src.agent.tools import (
    generate_insights,
    get_capabilities,
    pick_aoi,
    pick_dataset,
    pull_data,
)
```

**Change needed:** Add `gfw_pro_analysis` to the import and the `tools` list.

---

### `pyproject.toml` — Add missing dependencies

**File:** `/mnt/e/agentdev/projects/project-zeno/pyproject.toml`

Current relevant dependencies (already present):
- `"s3fs==2025.3.0"` — already in dependencies (line 35)
- `"fiona==1.10.1"` — already in dependencies (line 21)

**Currently MISSING** (not in pyproject.toml):
- `xarray` — not present
- `zarr` — not present
- `rioxarray` — not present
- `dask` — not present

**Change needed:** Add to `[project]` dependencies:
```
"xarray",
"zarr",
"rioxarray",
"dask[array,dataframe]",
```

Note: `s3fs`, `fsspec`, `fiona`, `shapely` are already present.

---

## 2. New File to Create

### `src/agent/tools/gfw_pro_analysis.py`

This is the primary new file. Based on the PROMPT requirements and patterns from existing tools:

**Tool signature pattern** (from `src/agent/tools/pull_data.py` lines 92–99):

```python
@tool("pull_data")
async def pull_data(
    query: str,
    start_date: str,
    end_date: str,
    change_over_time_query: bool,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
    state: Annotated[Dict, InjectedState] = None,
) -> Command:
```

**Required tool signature** (from PROMPT):

```python
@tool("gfw_pro_analysis")
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[AgentState, InjectedState],
) -> Command:
    """Run GFW Pro deforestation and disturbance alert analysis for the current AOI.
    Returns SBTN/JRC forest area, tree cover loss 2021-2024, indigenous lands area,
    and integrated disturbance alerts. Results are provided as a downloadable CSV."""
```

**State access pattern** (from `src/agent/tools/pull_data.py` lines 114–115):

```python
dataset = state["dataset"]
aoi_names = [a["name"] for a in state["aoi_selection"]["aois"]]
```

For the new tool:
```python
aoi = state["aoi"]         # dict with {source, src_id, name}
aoi_selection = state["aoi_selection"]  # AOISelection with .aois: list[dict]
```

**Command return pattern** (from `src/agent/tools/pull_data.py` lines 189–205):

```python
return Command(
    update={
        "statistics": [...],
        "start_date": effective_start,
        "end_date": effective_end,
        "messages": [tool_message],
    },
)
```

For the new tool:
```python
return Command(
    update={
        "gfw_pro_csv": csv_string,
        "messages": [ToolMessage(content, tool_call_id=tool_call_id)],
    },
)
```

---

## 3. Key Integration Point: `get_geometry_data`

**File:** `/mnt/e/agentdev/projects/project-zeno/src/shared/geocoding_helpers.py`

**Function:** `get_geometry_data` (lines 64–180)

```python
async def get_geometry_data(
    source: str, src_id: str
) -> Optional[Dict[str, Any]]:
```

Returns a dict:
```python
{
    "name": str,
    "subtype": str,
    "source": str,
    "src_id": str,
    "geometry": dict,  # GeoJSON geometry dict (Polygon, MultiPolygon, etc.)
}
```

For `source == "custom"`, geometry may be a `GeometryCollection` or single geometry.

For standard sources (`gadm`, `kba`, `landmark`, `wdpa`), `geometry` is the result of `ST_AsGeoJSON()` parsed as JSON.

The new tool will call:
```python
geo_data = await get_geometry_data(aoi["source"], aoi["src_id"])
geojson_geometry = geo_data["geometry"]
```

For multi-AOI, iterate over `state["aoi_selection"]["aois"]` and call for each.

---

## 4. State Keys: `aoi` vs `aoi_selection`

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/state.py`

```python
class AOISelection(TypedDict):
    name: str
    aois: list[dict]
```

Each dict in `aois` has keys: `source`, `src_id`, `name`, `subtype` (plus the source-specific id column).

The `aoi` key is the first element of `aoi_selection["aois"]` (deprecated but still populated — see `src/agent/tools/pick_aoi.py` line 554: `"aoi": final_aois[0]`).

For multi-AOI support, the tool must iterate `state["aoi_selection"]["aois"]`.

---

## 5. Existing Tool Pattern: `pick_aoi.py`

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pick_aoi.py`

Relevant pattern for reading `InjectedState` — `pull_data.py` uses `state: Annotated[Dict, InjectedState]`. The PROMPT specifies `state: Annotated[AgentState, InjectedState]` but both work (LangGraph injects the full state dict).

**Async gather pattern** for multi-AOI (pick_aoi.py lines 481–488):

```python
all_results = await asyncio.gather(
    *[query_aoi_database(place, RESULT_LIMIT) for place in places]
)
```

The new tool should similarly gather geometry data for all AOIs:
```python
geo_data_list = await asyncio.gather(
    *[get_geometry_data(aoi["source"], aoi["src_id"]) for aoi in aois]
)
```

---

## 6. Graph Prompt: Must Document New Tool

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/graph.py`

The `get_prompt()` function (lines 30–110) documents each tool in the TOOLS section and WORKFLOW. The new tool needs to be mentioned:

```python
"""TOOLS:
...
- gfw_pro_analysis: Run GFW Pro deforestation and disturbance alert analysis for the current AOI.
"""
```

---

## 7. ToolMessage Construction Pattern

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pull_data.py` (lines 184–188)

```python
tool_message = ToolMessage(
    content="|".join(tool_messages) if tool_messages else "No data pulled",
    tool_call_id=tool_call_id,
)
```

For the new tool, a simpler pattern with optional `status` and `response_metadata` (used in `pick_aoi.py` for human feedback):

```python
tool_message = ToolMessage(
    content=f"GFW Pro analysis complete. Results for {len(dfs)} AOI(s) ready as CSV.",
    tool_call_id=tool_call_id,
)
```

---

## 8. Existing Dependencies Relevant to New Module

From `pyproject.toml`:

| Package | Version | Relevance |
|---|---|---|
| `s3fs` | `2025.3.0` | S3 access for zarr files |
| `fiona` | `1.10.1` | Geometry/spatial ops |
| `geopandas` | `1.0.1` | Spatial analysis |
| `pandas` | `2.2.3` | DataFrame/CSV output |
| `boto3` | `1.38.27` | AWS SDK (S3 credentials) |

**Missing** (need to add):
- `xarray` — zarr dataset handling
- `zarr` — zarr format support
- `rioxarray` — rioxarray clip/CRS operations
- `dask[array,dataframe]` — required for zarr chunked arrays

---

## 9. Test File Location and Pattern

**File:** `/mnt/e/agentdev/projects/project-zeno/tests/tools/test_pull_data.py`

Test pattern:
```python
pytestmark = pytest.mark.asyncio(loop_scope="session")

async def test_something(structlog_context):
    command = await some_tool.ainvoke({
        "args": {...},
        "id": str(uuid.uuid4()),
        "type": "tool_call",
    })
    assert ...
```

New test file should be: `tests/tools/test_gfw_pro_analysis.py`

For unit tests of `run_analysis()`, use a small test geometry (e.g., a 1-degree bounding box over the IDN test case from `query3.py`).

---

## 10. Error Handling Pattern

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/graph.py` (lines 173–182)

Tool errors are caught by `handle_tool_errors` middleware:

```python
@wrap_tool_call
async def handle_tool_errors(request, handler):
    try:
        return await handler(request)
    except Exception as e:
        logger.exception("Tool execution failed")
        return ToolMessage(
            content=f"Tool error: {str(e)}",
            tool_call_id=request.tool_call["id"],
        )
```

The new tool can raise exceptions freely — they will be caught and returned as ToolMessages.

However, for user-friendly errors (e.g., no AOI selected), return a `Command` with an explanatory ToolMessage instead of raising.

---

## 11. Module-Level Singleton Pattern

The PROMPT specifies `get_datasets()` should cache as a module-level singleton. This is the same pattern as `retriever_cache` in `src/agent/tools/pick_dataset.py` (lines 34–52):

```python
retriever_cache = None

async def _get_retriever():
    global retriever_cache
    if retriever_cache is None:
        # initialize...
        retriever_cache = ...
    return retriever_cache
```

For `gfw_pro_analysis.py`:
```python
_datasets_cache: dict | None = None

def get_datasets() -> dict[str, xr.Dataset]:
    global _datasets_cache
    if _datasets_cache is None:
        _datasets_cache = {
            "sbtn": xr.open_zarr(...),
            "jrc": xr.open_zarr(...),
            "mergedLoss": xr.open_zarr(...),
            "intdist": xr.open_zarr(...),
        }
    return _datasets_cache
```

Note: `get_datasets()` is synchronous per spec (returns cached dict), but `asyncio.to_thread()` is used for `run_analysis()`.

---

## 12. Frontend State Key Consumption

**File:** `/mnt/e/agentdev/projects/project-zeno/frontend/utils.py` (lines 836–855)

The frontend `render_update()` function checks for specific keys in the update dict:
- `"charts_data"` → renders charts + download button for CSV
- `"dataset"` → renders dataset map
- `"aoi_selection"` → renders AOI map

For `gfw_pro_csv`, the frontend will need to render a download button. This is currently NOT handled in `utils.py`. A new `if "gfw_pro_csv" in update:` block would be needed in the frontend, but the PROMPT/requirements do not explicitly ask for frontend changes — only the state key and CSV string. The CSV download UX may be handled purely via the agent response text (linking/describing the data).

**Existing download pattern in frontend (lines 847–855):**

```python
if thread_id and checkpoint_id:
    st.download_button(
        label="Download data CSV",
        data=client.download_data(
            thread_id=thread_id, checkpoint_id=checkpoint_id
        ),
        file_name=f"thread_{thread_id}_checkpoint_{checkpoint_id}_raw_data.csv",
        mime="text/csv",
    )
```

To surface the GFW Pro CSV, the frontend would need a similar block checking for `"gfw_pro_csv"` in update and rendering a download button with `data=update["gfw_pro_csv"].encode()`.

---

## 13. Config/Environment Variables

**File:** `/mnt/e/agentdev/projects/project-zeno/src/shared/config.py`

Current `SharedSettings` uses `pydantic_settings.BaseSettings`. New environment variables (`GFW_PRO_DATA_PATH`, `GFW_PRO_ALERT_START_DATE`) can either:
1. Be added to `SharedSettings` (consistent with project pattern)
2. Be read directly via `os.environ.get()` in `gfw_pro_analysis.py`

The PROMPT specifies env vars rather than settings class fields, suggesting option 2 (direct `os.getenv`).

`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` are standard boto3/s3fs env vars and do not need explicit handling — s3fs picks them up automatically.

---

## 14. Asyncio Threading for CPU-bound Work

The PROMPT specifies running analysis in `asyncio.to_thread()`. This is idiomatic Python 3.9+ for offloading sync/CPU-bound work from the async event loop.

Pattern:
```python
result_df = await asyncio.to_thread(run_analysis, geojson_geometry, name)
```

No existing examples of `asyncio.to_thread` in the codebase — it's a new pattern being introduced. The alternative `loop.run_in_executor()` is not used either. `asyncio.to_thread()` is the simplest approach for Python 3.12.

---

## 15. `InjectedState` Import

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/pull_data.py` (line 7):

```python
from langgraph.prebuilt import InjectedState
```

Same import needed in `gfw_pro_analysis.py`.

**File:** `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/generate_insights.py` (line 8):
```python
from langgraph.prebuilt import InjectedState
```

Both tools use `state: Annotated[Dict, InjectedState]`. The PROMPT specifies `Annotated[AgentState, InjectedState]` which is equivalent — LangGraph injects the full state dict regardless.
