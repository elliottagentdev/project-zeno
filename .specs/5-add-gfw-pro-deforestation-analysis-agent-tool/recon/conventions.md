# Conventions & Constraints

## Coding Style and Naming Conventions

### Python Version and Formatting
- **Python version**: 3.12.8 (pinned in `pyproject.toml`)
- **Formatter/Linter**: `ruff` (configured in `pyproject.toml`)
  - Line length: 79 characters (with E501 ignored for actual enforcement)
  - Quote style: double quotes
  - Lint rules: E, F, W, Q, I (imports sorted)
- **Pre-commit hooks** (`.pre-commit-config.yaml`): ruff linter + ruff formatter run on every commit; also trailing whitespace, end-of-file-fixer, check-yaml, check-added-large-files (>1000KB), detect-private-key

### File Naming
- All Python source modules: `snake_case.py`
- Test files: `test_<module_name>.py` — placed in `tests/` mirroring the `src/` structure
  - `tests/tools/test_generate_insights.py` — for agent tools
  - `tests/agent/test_graph.py` — for agent-level graph tests
  - `tests/api/test_*.py` — for API tests
- No class-per-file rule; related classes and functions live together in one module

### Module/Package Naming
- `snake_case` throughout: `pick_dataset.py`, `pick_aoi.py`, `pull_data.py`, `generate_insights.py`, `gfw_pro_analysis.py` (following the new tool's proposed name)
- Package `__init__.py` files explicitly re-export public symbols (see `src/agent/tools/__init__.py`)

### Variable and Function Naming
- Functions: `snake_case` (e.g., `get_geometry_data`, `run_analysis`, `clip_ds_to_geojson`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `GADM_TABLE`, `RESULT_LIMIT`, `TCL_TILE_MAX_YEAR`)
- Classes: `PascalCase` (e.g., `DataPullResult`, `AOIIndex`, `AgentState`)
- Private/internal helpers: leading underscore `_snake_case` (e.g., `_get_retriever`, `_read`)
- Module-level singletons: `snake_case` (e.g., `retriever_cache = None`, `data_pull_orchestrator`)

### Import Ordering (enforced by ruff/I rules)
Standard library → third-party → local (`src.*`). Example from `pick_dataset.py`:
```python
from datetime import datetime        # stdlib
from pathlib import Path

import pandas as pd                  # third-party
from langchain_core.messages import ToolMessage
...

from src.agent.llms import SMALL_MODEL   # local
from src.shared.config import SharedSettings
from src.shared.logging_config import get_logger
```

---

## Error Handling Patterns

### In Agent Tools
- Tools return `Command` objects — errors surface as `ToolMessage` content rather than raised exceptions
- The graph-level `handle_tool_errors` middleware in `src/agent/graph.py` wraps all tool calls and catches any unhandled exceptions, returning a `ToolMessage(content=f"Tool error: {str(e)}", ...)`
- Within tools, raise `ValueError` for logic/validation errors (e.g., invalid source, missing user_id) — these are caught by the middleware
- For non-fatal conditions (no results, out-of-range dates), return early with a `Command` containing a `ToolMessage` explaining the situation

Example from `pull_data.py` (non-fatal date range mismatch):
```python
if end_date < effective_start or start_date > effective_end:
    return Command(
        update={
            "messages": [
                ToolMessage(
                    f"The requested date range (...) is outside the available range...",
                    tool_call_id=tool_call_id,
                    status="success",
                    response_metadata={"msg_type": "human_feedback"},
                )
            ],
        },
    )
```

### In API Layer (`src/api/app.py`)
- FastAPI route handlers: catch `Exception`, log with `logger.exception(...)`, re-raise as `HTTPException(status_code=500, detail=str(e))`
- Auth failures: raise `HTTPException(status_code=401/403, ...)` directly

### In Shared/Utility Code
- `src/shared/geocoding_helpers.py`: raise `ValueError` for invalid arguments (invalid source type, missing user_id)
- `src/agent/tools/pick_aoi.py`: uses `except Exception` around table existence checks, logs with `logger.warning(...)`, and continues gracefully
- Database pool warnings: `logger.warning(...)` for already-initialized or not-yet-initialized pool states

### Logging Pattern
All modules follow the same pattern using structlog:
```python
from src.shared.logging_config import get_logger
logger = get_logger(__name__)

# Usage:
logger.info("PICK-DATASET-TOOL")
logger.debug(f"Some detail: {variable}")
logger.warning(f"Table {GADM_TABLE} does not exist")
logger.exception("Tool execution failed")   # includes traceback
```

Structured log calls with keyword args (structlog-native):
```python
logger.info("TCL tile year params", start_year=start_year, end_year=end_year)
```

---

## Test Framework and Patterns

### Framework
- **pytest** with **pytest-asyncio** (version 1.1.0)
- `asyncio_mode = "auto"` in `pyproject.toml` — all async test functions are automatically awaited
- `asyncio_default_fixture_loop_scope = "session"` — single event loop per test session
- Tests marked with `pytestmark = pytest.mark.asyncio(loop_scope="session")` or `loop_scope="module"` at module level

### Test File Structure
- `tests/conftest.py` — session-scoped fixtures (database setup, HTTP clients, user factories)
- `tests/tools/test_generate_insights.py` — tool unit tests, override DB fixtures, mock external calls
- `tests/agent/test_graph.py` — agent integration tests, mock DB, mock LLM calls
- `tests/api/test_*.py` — API integration tests using `AsyncClient` with ASGI transport

### Fixture Conventions
- Fixtures override conftest's global DB fixtures when tests don't need a DB:
```python
@pytest.fixture(scope="function", autouse=True)
def test_db():
    """Override the global test_db fixture to avoid database connections."""
    pass
```
- `pytest_asyncio.fixture` for async fixtures; `pytest.fixture` for sync ones
- Common scopes: `scope="session"` for expensive setup (DB schema), `scope="function"` for per-test isolation

### Mocking Pattern
- `unittest.mock.patch` context manager for patching module-level functions
- `AsyncMock` for async functions
- Example from `tests/agent/test_graph.py`:
```python
with patch(
    "src.agent.tools.pick_aoi.query_aoi_database",
    new_callable=AsyncMock,
    ...
```
- Google AI client cached instances reset at module level via fixture to avoid event loop conflicts:
```python
@pytest.fixture(scope="module", autouse=True)
def reset_google_clients():
    llms_module = sys.modules["src.agent.llms"]
    llms_module.SMALL_MODEL = llms_module.get_small_model()
    yield
```

### Invoking Tools in Tests
Tools are invoked via `.ainvoke({"type": "tool_call", "name": ..., "id": ..., "args": {...}})`:
```python
command = await generate_insights.ainvoke({
    "type": "tool_call",
    "name": "generate_insights",
    "id": tool_call_id,
    "args": {"query": "...", "state": update},
})
assert "charts_data" in command.update
```

### Test Running
- `make test` runs: `uv run pytest tests/ -v`
- CI (unit-tests.yml) runs: `uv run pytest tests/api tests/cli tests/agent -v` (excludes `tests/tools/` and `tests/load/`)
- Note: `tests/tools/` tests (e.g., `test_generate_insights.py`) are NOT in CI — they require real GOOGLE_API_KEY
- Test DB is a real PostgreSQL instance (postgis/postgis:17-3.5 in CI, local Docker in dev)

---

## CI/CD Configuration

### GitHub Actions Workflows
- **lint.yml**: runs on every push; `uvx pre-commit run --show-diff-on-failure --all-files`
- **unit-tests.yml**: runs on pull_request; requires PostgreSQL service container

### Quality Gates
1. Pre-commit: trailing whitespace, YAML validity, large file detection, ruff lint+format
2. Tests: pytest against real PostgreSQL (not mocked for DB-dependent tests)

### Docker Build
- **docker-build.yml** and **docker-build-db.yml** — image builds (not examined in detail)
- Development infrastructure: `docker compose -f docker-compose.dev.yaml up -d` (PostgreSQL + Langfuse)

---

## Dependency Management

### Tool: `uv` with `pyproject.toml`
- **Lock file**: `uv.lock` (pinned, committed to repo)
- Dependencies split into groups:
  - `[project]` — runtime dependencies
  - `[dependency-groups] dev` — dev/test tools (pytest, ruff, jupyter, locust)
  - `[dependency-groups] frontend` — streamlit and plotting libs
- Install: `uv sync` (dev+frontend groups by default per `[tool.uv] default-groups`)
- Frozen install for CI: `uv sync --frozen`
- Run commands: `uv run <cmd>` (e.g., `uv run pytest tests/ -v`)

### Key Existing Dependencies (relevant to new feature)
Already in `pyproject.toml`:
- `s3fs==2025.3.0` — S3 filesystem access (already present!)
- `fiona==1.10.1` — geospatial file I/O
- `geopandas==1.0.1` — spatial dataframes
- `pandas==2.2.3`
- `boto3==1.38.27`

Not yet present (need to add):
- `xarray` — zarr data handling
- `zarr` — zarr format
- `rioxarray` — raster clipping with rioxarray
- `dask[array,dataframe]` — parallel compute for zarr

---

## Existing Abstractions to Reuse

### Settings Pattern (`src/shared/config.py`)
New env vars should be added to a settings class using pydantic-settings `BaseSettings`:
```python
class _SharedSettings(BaseSettings):
    gfw_pro_data_path: Optional[str] = Field(default=None, alias="GFW_PRO_DATA_PATH")
    gfw_pro_alert_start_date: str = Field(default="2025-01-01", alias="GFW_PRO_ALERT_START_DATE")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }
```
The singleton pattern is `SharedSettings = _SharedSettings()` at module level.

### Logger (`src/shared/logging_config.py`)
```python
from src.shared.logging_config import get_logger
logger = get_logger(__name__)
```
No other logging setup needed.

### Geocoding Helper (`src/shared/geocoding_helpers.py`)
```python
from src.shared.geocoding_helpers import get_geometry_data
geojson = await get_geometry_data(source, src_id)  # returns dict or None
```
Returns a dict with `name`, `subtype`, `source`, `src_id`, `geometry` (GeoJSON geometry dict).

### Tool Registration Pattern
Tool functions decorated with `@tool("tool_name")`, then:
1. Added to `src/agent/tools/__init__.py` exports
2. Added to `tools = [...]` list in `src/agent/graph.py`
3. New state keys added to `AgentState` TypedDict in `src/agent/state.py`

### Module-Level Singleton Cache
Used for expensive one-time initialization (e.g., `retriever_cache` in `pick_dataset.py`). Pattern:
```python
_datasets_cache: Optional[dict] = None  # module-level

def get_datasets() -> dict:
    global _datasets_cache
    if _datasets_cache is None:
        # initialize...
        _datasets_cache = ...
    return _datasets_cache
```

### @tool Decorator Signature Pattern
Tools that read state use `InjectedState`:
```python
from langgraph.prebuilt import InjectedState

@tool("gfw_pro_analysis")
async def gfw_pro_analysis(
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[AgentState, InjectedState],
) -> Command:
```
Tools that don't need state use `InjectedToolCallId` only (see `pick_dataset.py`'s `@tool("pick_dataset")`).

### Command Return Pattern
All tools return `Command(update={...})`. State keys updated are listed explicitly; `messages` always includes a `ToolMessage`:
```python
return Command(
    update={
        "some_state_key": value,
        "messages": [ToolMessage(tool_message_content, tool_call_id=tool_call_id)],
    },
)
```

---

## Contributing Guidelines

No `CLAUDE.md` or `AGENTS.md` found in the project root. No `CONTRIBUTING.md` either.

The implicit conventions from examining the codebase:

1. New agent tools go in `src/agent/tools/<tool_name>.py`
2. Heavy computation that would block the event loop goes in `asyncio.to_thread()` (consistent with the spec requirement)
3. Tests for agent tools go in `tests/tools/test_<tool_name>.py`
4. Test files that need to bypass DB fixtures override them explicitly with `pass` body fixtures
5. All imports of internal modules use absolute paths from `src.*` (no relative imports)
6. Tool docstrings are the LLM-visible tool description — keep them accurate and concise
7. The `src/agent/tools/__init__.py` is the single place for tool re-exports
