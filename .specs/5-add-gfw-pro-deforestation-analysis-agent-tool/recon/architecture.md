# Architecture Reconnaissance — project-zeno

## Feature Being Planned

Add a GFW Pro deforestation analysis agent tool (`gfw_pro_analysis`) that reads pre-computed zarr rasters from WRI S3, clips them to an AOI geometry, and returns metrics (SBTN/JRC forest area, TCL loss, indigenous lands, disturbance alerts) as a downloadable CSV.

---

## Directory Layout

```
/mnt/e/agentdev/projects/project-zeno/
├── Dockerfile
├── Makefile
├── pyproject.toml         # uv-managed Python 3.12.8 project
├── uv.lock
├── docker-compose.yaml    # Production/dev compose
├── docker-compose.dev.yaml
├── db/                    # DB migration container (Alembic)
│   ├── alembic/
│   ├── alembic.ini
│   └── entrypoint.sh
├── src/
│   ├── agent/             # LangGraph agent core
│   │   ├── config.py
│   │   ├── graph.py       # Agent graph, tools list, prompts
│   │   ├── llms.py        # LLM model definitions
│   │   ├── prompts.py
│   │   ├── state.py       # AgentState TypedDict
│   │   └── tools/
│   │       ├── __init__.py          # Exports all tools
│   │       ├── analytics_datasets.yml
│   │       ├── datasets_config.py
│   │       ├── generate_insights.py
│   │       ├── get_capabilities.py
│   │       ├── pick_aoi.py
│   │       ├── pick_dataset.py
│   │       ├── pull_data.py
│   │       ├── code_executors/
│   │       │   ├── __init__.py
│   │       │   ├── base.py
│   │       │   ├── gemini_executor.py
│   │       │   └── README.md
│   │       └── data_handlers/
│   │           ├── analytics_handler.py
│   │           ├── base.py
│   │           └── example_handler.py
│   ├── api/               # FastAPI app
│   │   ├── app.py
│   │   ├── auth/
│   │   ├── cli.py
│   │   ├── config.py
│   │   ├── data_models.py  # SQLAlchemy ORM models
│   │   ├── schemas.py
│   │   └── user_profile_configs/
│   ├── ingest/            # Data ingestion utilities
│   └── shared/            # Shared utilities
│       ├── config.py       # SharedSettings (pydantic-settings)
│       ├── database.py     # SQLAlchemy async pool
│       ├── geocoding_helpers.py  # get_geometry_data(), table mappings
│       └── logging_config.py
├── tests/
│   ├── conftest.py         # pytest fixtures, test DB setup
│   ├── agent/
│   │   └── test_graph.py
│   └── tools/
│       ├── test_generate_insights.py
│       ├── test_pick_aoi.py
│       ├── test_pick_dataset.py
│       └── test_pull_data.py
├── frontend/              # Streamlit frontend
├── docs/
└── logs/
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12.8 |
| Package manager | `uv` (pyproject.toml + uv.lock) |
| Web framework | FastAPI 0.116.1 + uvicorn |
| Agent framework | LangGraph 1.0.3 + LangChain 1.0.8 |
| LLMs | Claude Sonnet/Haiku (Anthropic), Gemini (Google), GPT-4o (OpenAI) |
| Database | PostgreSQL 17 + PostGIS (via SQLAlchemy asyncpg, psycopg) |
| Geospatial | geopandas, fiona, rioxarray (inferred), shapely, geoalchemy2 |
| Cloud storage | s3fs 2025.3.0, boto3 (already in deps) |
| Data | pandas 2.2.3 |
| Container | Docker Compose (docker-compose.yaml), PostGIS image |
| Linting | ruff (line-length 79, E/F/W/Q/I rules, E501 ignored) |
| Testing | pytest + pytest-asyncio (asyncio_mode = "auto") |
| Observability | Langfuse 3.10.1 |
| Frontend | Streamlit 1.47.0 |

---

## Build System and Deployment

- **Dependency management**: `uv` with `pyproject.toml` and `uv.lock`. No Pipfile — deps declared under `[project].dependencies`.
- **Dev extras**: `[dependency-groups].dev` includes pytest, ruff, jupyterlab.
- **Docker build**: `FROM python:3.12.8-slim-bookworm`, installs uv, then runs `uv sync --frozen --no-dev`. Source mounted at `/app/src` in dev.
- **DB migrations**: Separate container in `db/` using Alembic. Runs `entrypoint.sh` on compose startup (depends-on `migrate` service completing).
- **Dev compose**: `docker-compose.dev.yaml` (separate dev config).
- **API**: uvicorn serving `src.api.app:app` on port 8000.
- **Frontend**: Streamlit on port 8501.
- **External services**: Langfuse (observability), MinIO (S3-compatible), Redis, ClickHouse — all in compose.

---

## Key Entry Points and Main Modules

### Agent Entry Point: `src/agent/graph.py`

- Defines `tools` list (currently: `get_capabilities, pick_aoi, pick_dataset, pull_data, generate_insights`)
- `fetch_zeno()` / `fetch_zeno_anonymous()`: instantiate the compiled LangGraph state machine via `create_agent(model, tools, state_schema=AgentState, ...)`
- Uses `AsyncPostgresSaver` (langgraph-checkpoint-postgres) for conversation history
- `MODEL` and `SMALL_MODEL` are dynamic from `AgentSettings` (env vars)

### Agent State: `src/agent/state.py`

```python
class AOISelection(TypedDict):
    name: str
    aois: list[dict]

class Statistics(TypedDict):
    dataset_name: str
    start_date: str
    end_date: str
    source_url: str
    data: dict
    aoi_names: list[str]

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_persona: str
    aoi: dict                         # deprecated (first AOI only)
    subtype: str
    aoi_selection: AOISelection       # name + list of AOI dicts
    dataset: dict
    start_date: str
    end_date: str
    statistics: Annotated[list[Statistics], operator.add]
    insights: list
    charts_data: list
    codeact_parts: list[CodeActPart]
```

The feature requires adding `gfw_pro_csv: Optional[str]` to `AgentState`.

### Tool Pattern: `src/agent/tools/pick_dataset.py` (reference implementation)

Each tool is decorated with `@tool("tool_name")` from `langchain_core.tools`. The function signature follows:

```python
@tool("pick_dataset")
async def pick_dataset(
    query: str,
    start_date: str,
    end_date: str,
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
```

Tools return a `langgraph.types.Command` with an `update` dict that sets state keys and appends a `ToolMessage`.

For state-injected tools (like the proposed `gfw_pro_analysis`), the pattern from `pull_data.py` uses `InjectedState`:

```python
from langgraph.prebuilt import InjectedState

@tool("pull_data")
async def pull_data(
    ...,
    state: Annotated[AgentState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId] = None,
) -> Command:
```

### Tool Registration

- `src/agent/tools/__init__.py`: exports all tools
- `src/agent/graph.py`: `tools = [get_capabilities, pick_aoi, pick_dataset, pull_data, generate_insights]`
- New tool must be added to both files

### API Entry Point: `src/api/app.py`

- FastAPI app with auth, CORS, streaming responses
- Calls `fetch_zeno()` / `fetch_zeno_anonymous()` to get the compiled graph
- Streams LangGraph events as SSE
- Uses `structlog` context vars for `user_id` propagation

---

## Database Layer Architecture

### ORM: `src/api/data_models.py`
SQLAlchemy declarative base. Key models:
- `UserOrm` (users table) — user profiles
- `ThreadOrm` (threads table) — conversation threads
- `CustomAreaOrm` (custom_areas table) — user-defined geometries (JSONB)
- `RatingOrm`, `WhitelistedUserOrm`, `MachineUserKeyOrm`, `DailyUsageOrm`

### Geometry Tables (PostGIS, not in ORM — raw SQL)
Accessed via raw SQL queries in `src/shared/geocoding_helpers.py`:
- `geometries_gadm` — GADM administrative boundaries
- `geometries_kba` — Key Biodiversity Areas
- `geometries_landmark` — Indigenous/community lands
- `geometries_wdpa` — Protected areas
- `custom_areas` — User custom geometries

### Connection Pool: `src/shared/database.py`
- Global asyncpg/SQLAlchemy pool (`initialize_global_pool`, `close_global_pool`)
- `get_session_from_pool()` — async context manager for SQLAlchemy sessions
- `get_connection_from_pool()` — raw connection context manager

### Config: `src/shared/config.py`
`SharedSettings` (pydantic-settings singleton):
- `database_url`
- `db_pool_size`, `db_max_overflow`, `db_pool_timeout`, `db_pool_recycle`
- `eoapi_base_url`
- `dataset_embeddings_db/model/task_type`

No `GFW_PRO_DATA_PATH` or `GFW_PRO_ALERT_START_DATE` currently defined here — these will be new additions (or accessed directly via `os.environ`).

---

## Geocoding Helpers: `src/shared/geocoding_helpers.py`

Key function the new tool will use:

```python
async def get_geometry_data(source: str, src_id: str) -> Optional[Dict[str, Any]]:
    """Returns: {name, subtype, source, src_id, geometry} or None"""
```

Returns a GeoJSON geometry dict under the `"geometry"` key. The geometry is parsed from `ST_AsGeoJSON()` PostGIS output. For custom areas, it handles multiple geometries as `GeometryCollection`.

`source` values: `gadm`, `kba`, `landmark`, `wdpa`, `custom`

---

## AOI State Structure

After `pick_aoi` runs, the state contains:

```python
state["aoi"] = {  # First AOI (deprecated but still set)
    "source": str,   # e.g. "gadm"
    "src_id": str,   # e.g. "IDN.12.26_1"
    "name": str,
    "subtype": str,
    ...
}
state["aoi_selection"] = {
    "name": str,          # display name
    "aois": list[dict],   # all selected AOIs (same structure as aoi)
}
```

The new `gfw_pro_analysis` tool should iterate `state["aoi_selection"]["aois"]` for multi-AOI support, with `state["aoi"]` as fallback.

---

## Existing Dependencies Relevant to Feature

Already in `pyproject.toml`:
- `s3fs==2025.3.0` — S3 filesystem access
- `fiona==1.10.1` — geospatial vector I/O
- `geopandas==1.0.1` — geospatial dataframes
- `pandas==2.2.3` — dataframes/CSV
- `boto3==1.38.27` — AWS SDK

**Not yet in `pyproject.toml`** (must be added):
- `xarray` — zarr file reading via `xarray.open_zarr`
- `zarr` — zarr format support
- `fsspec` — filesystem abstraction (used by xarray/zarr for S3)
- `rioxarray` — rioxarray clip operations
- `dask[array,dataframe]` — lazy/chunked array support (zarr + xarray)

Note: `fsspec` may already be an indirect dependency via `s3fs`, but needs explicit pin. `shapely` is likely transitive via `geopandas`.

---

## Testing Architecture

- **Framework**: pytest with pytest-asyncio (`asyncio_mode = "auto"`, `asyncio_default_fixture_loop_scope = "session"`)
- **Test location**: `tests/tools/` for tool tests, `tests/agent/` for graph tests
- **Test DB**: Separate test database (`{DATABASE_URL}_test` or `TEST_DATABASE_URL` env var). Uses `NullPool` async engine.
- **Fixtures** (in `tests/conftest.py`):
  - `test_db`: session-scoped — creates all tables, drops after session
  - `test_db_session`: function-scoped — disposes engine after each test
  - `test_db_pool`: function-scoped, autouse — initializes global pool with test DB URL
  - `client`, `anonymous_client`: httpx AsyncClient fixtures
  - `structlog_context`: binds `user_id = "test-user-123"` for tools requiring user context
  - `user`, `user_ds`, `admin_user_factory`, `thread_factory`: DB object factories
- **Test pattern**: `pytestmark = pytest.mark.asyncio(loop_scope="session")`; tools are invoked via `await tool.ainvoke({...})`

---

## Environment Variables (Relevant to Feature)

Currently defined/used:
- `DATABASE_URL` — PostgreSQL connection string
- `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` — for S3 (boto3/s3fs)
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GOOGLE_API_KEY`

New env vars to add (per PROMPT.md):
- `GFW_PRO_DATA_PATH` — optional local zarr base path; falls back to S3 URIs
- `GFW_PRO_ALERT_START_DATE` — ISO date, default `2025-01-01`

---

## No CLAUDE.md or AGENTS.md Found

No project-level `CLAUDE.md` or `AGENTS.md` file was found in `/mnt/e/agentdev/projects/project-zeno/`.

---

## Images Directory

No images found at `/mnt/e/agentdev/projects/project-zeno/.specs/5-add-gfw-pro-deforestation-analysis-agent-tool/images/` — directory does not exist or is empty.
