# Codebase Conventions Report

## Project Overview

Project Zeno is a Python 3.12 geospatial agent application using LangChain/LangGraph for an AI agent that answers nature/forest-related queries. It has a FastAPI backend (`src/api/`), a LangGraph agent (`src/agent/`), shared utilities (`src/shared/`), and a Streamlit frontend (`frontend/`).

## Project Structure

```
src/
  agent/          # LangGraph agent: graph, state, tools, LLM config
    tools/        # Agent tools: pick_dataset, pick_aoi, pull_data, etc.
      data_handlers/  # Strategy pattern handlers for different data sources
      code_executors/ # Code execution sandbox
  api/            # FastAPI application, auth, data models
  shared/         # Shared config, logging, database, geocoding helpers
  ingest/         # Data ingestion scripts
frontend/         # Streamlit app (app.py, pages/, utils.py, client.py)
tests/
  agent/          # Agent graph tests
  api/            # API endpoint tests
  tools/          # Tool-level tests (pick_dataset, pick_aoi, pull_data)
  cli/            # CLI tests
  conftest.py     # Shared fixtures (DB setup, auth mocking, etc.)
```

## Language and Dependency Management

- **Python 3.12.8** (pinned in `pyproject.toml`)
- **uv** for dependency management (`uv sync --frozen` in CI)
- **hatchling** as build backend
- Dependencies in `pyproject.toml` with dependency groups: `dev` and `frontend`
- Key frameworks: LangChain 1.0.8, LangGraph 1.0.3, FastAPI 0.116.1, Pydantic 2.11.7, SQLAlchemy 2.0.41

## Coding Style and Naming Conventions

### Formatting and Linting
- **Ruff** for both linting and formatting
- Line length: 79 (configured but E501 ignored)
- Quote style: double quotes
- Lint rules: `["E", "F", "W", "Q", "I"]` (pycodestyle, pyflakes, warnings, quotes, isort)
- Pre-commit hooks: trailing-whitespace, check-symlinks, check-yaml, end-of-file-fixer, check-added-large-files (1000KB), detect-private-key, ruff lint+format

### Naming Patterns
- **Modules**: snake_case (e.g., `pick_dataset.py`, `analytics_handler.py`, `datasets_config.py`)
- **Classes**: PascalCase with descriptive names (e.g., `DatasetOption`, `DatasetSelectionResult`, `DataSourceHandler`, `AgentState`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `DIST_ALERT_ID`, `TREE_COVER_LOSS_ID`, `MODEL_REGISTRY`, `DATASETS`)
- **Functions**: snake_case, async functions prefixed with nothing special (e.g., `async def select_best_dataset(...)`)
- **Private/internal**: underscore prefix for internal functions (e.g., `async def _get_retriever()`)
- **Settings singletons**: private class `_SharedSettings` instantiated as module-level `SharedSettings`

### Type Annotations
- Extensive use of Pydantic models for data validation and serialization
- Type hints used on function signatures: `def can_handle(self, dataset: Any) -> bool`
- `TypedDict` for agent state (`AgentState`)
- `Annotated` types for LangChain tool injection: `tool_call_id: Annotated[str, InjectedToolCallId]`
- `Optional` from typing used for nullable fields

### Import Style
- Standard library first, then third-party, then local (`src.agent.*`, `src.shared.*`)
- Ruff isort handles ordering automatically

## Error Handling Patterns

### Agent Tool Errors
Tool errors are caught at the graph level via middleware in `src/agent/graph.py`:

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

This wraps all tool calls so exceptions become `ToolMessage` responses rather than crashing the agent loop.

### Validation Errors
Pydantic validators on models raise `ValueError` for invalid inputs:
```python
@field_validator("dataset_id")
def validate_dataset_id(cls, v):
    if v not in [ds["dataset_id"] for ds in DATASETS]:
        raise ValueError(f"Invalid dataset ID: {v}")
    return v
```

Model validators silently correct invalid state (e.g., setting `context_layer = None` if hallucinated) rather than raising.

### Frontend Error Handling
Frontend uses try/except with Streamlit UI feedback:
```python
except Exception as e:
    st.error(f"Error rendering map: {str(e)}")
    st.json(aoi_data)  # Fallback to show raw data
```

### Logging
- **structlog** via `src/shared/logging_config.py`
- Logger obtained via `get_logger(__name__)` at module level
- Log levels: `logger.debug()` for tracing, `logger.info()` for key events, `logger.exception()` for errors
- Supports JSON and text output formats (env-configurable)
- File logging to `logs/zeno.log` with rotation (10MB, 5 backups)

## Test Framework and Patterns

### Framework
- **pytest 8.4.1** with **pytest-asyncio 1.1.0**
- Async mode: `asyncio_mode = "auto"` and `asyncio_default_fixture_loop_scope = "session"` in `pyproject.toml`
- Tests are async by default (no need for `@pytest.mark.asyncio` on individual tests in most cases)

### Test File Naming
- `tests/<module>/test_<name>.py` (e.g., `tests/tools/test_pick_dataset.py`, `tests/agent/test_graph.py`)
- Test functions: `async def test_<descriptive_name>(...)`

### Test Patterns

**Parametrized tests** are heavily used for dataset selection validation:
```python
@pytest.fixture(params=[
    ("query text", EXPECTED_DATASET),
    ...
])
def test_query_with_expected_dataset(request):
    return request.param
```

**Mocking** with `unittest.mock.AsyncMock` and `patch`:
```python
with (
    patch("src.agent.tools.pick_dataset.rag_candidate_datasets",
          new_callable=AsyncMock, return_value=candidate_df),
    patch("src.agent.tools.pick_dataset.select_best_dataset",
          new_callable=AsyncMock, return_value=fake_selection),
):
```

**Fixture overrides** in tool tests to avoid DB dependencies:
```python
@pytest.fixture(scope="function", autouse=True)
def test_db():
    """Override the global test_db fixture to avoid database connections."""
    pass
```

**Session-scoped fixtures** for expensive setup (DB creation, client instances).

**Helper factories** for test data:
```python
def _make_fake_selection(dataset_id: int, context_layer: str | None) -> DatasetSelectionResult:
    ds = next(d for d in DATASETS if d["dataset_id"] == dataset_id)
    return DatasetSelectionResult(...)
```

### Conftest Structure (`tests/conftest.py`)
- Session-scoped DB setup/teardown with SQLAlchemy async engine
- `NullPool` for test database connections
- ASGI test client via `httpx.AsyncClient` with `ASGITransport`
- Auth override fixtures for simulating different user types
- Global mock of `replay_chat` to avoid checkpointer dependencies
- `test_db_pool` fixture initializes the shared database pool per test

## CI/CD Configuration and Quality Gates

### Workflows (`.github/workflows/`)

1. **Lint** (`lint.yml`) - runs on every push:
   - `uvx pre-commit run --show-diff-on-failure --all-files`

2. **Unit Tests** (`unit-tests.yml`) - runs on pull requests:
   - PostgreSQL service container (PostGIS 17-3.5)
   - `uv run pytest tests/api tests/cli tests/agent -v`
   - Note: `tests/tools/` tests (including `test_pick_dataset.py`) require real Google API key and are NOT in the default CI test path for unit tests, but are in `tests/agent` path. The tool tests hit real LLM APIs.
   - Environment variables set for all external services (most are fake keys except GOOGLE_API_KEY from secrets)

3. **Docker Build** workflows for DB and app images

### Pre-commit Hooks
Defined in `.pre-commit-config.yaml`:
- `pre-commit-hooks v5.0.0`: trailing-whitespace, check-symlinks, check-yaml, end-of-file-fixer, check-added-large-files, detect-private-key
- `ruff-pre-commit v0.7.3`: ruff lint (with --fix) + ruff format

## Key Abstractions and Utilities to Reuse

### Configuration Singletons
- `src/shared/config.py`: `SharedSettings` (Pydantic BaseSettings) - DB URL, eoAPI base URL, embeddings config
- `src/agent/config.py`: `AgentSettings` - model selection (MODEL, SMALL_MODEL, CODING_MODEL)
- Both use `.env` file loading via `pydantic-settings`

### Dataset Configuration
- `src/agent/tools/datasets_config.py`: Loads `DATASETS` list from `analytics_datasets.yml`
- `src/agent/tools/data_handlers/analytics_handler.py`: Constants for dataset IDs (`DIST_ALERT_ID`, `GRASSLANDS_ID`, `TREE_COVER_LOSS_ID`, etc.)

### Data Handler Strategy Pattern
- `src/agent/tools/data_handlers/base.py`: Abstract `DataSourceHandler` with `can_handle()` and `pull_data()` methods
- `DataPullResult` Pydantic model for standardized handler return values
- Concrete handlers in `analytics_handler.py`, `example_handler.py`

### Tile URL Construction (Critical for This Issue)
In `src/agent/tools/pick_dataset.py` lines 286-312, tile URLs are constructed per-dataset:
- Relative URLs get `SharedSettings.eoapi_base_url` prepended
- DIST-ALERT: appends `&start_date=...&end_date=...`
- LAND_COVER_CHANGE/GRASSLANDS: `.format(year=...)` substitution
- TREE_COVER_LOSS: appends `&start_year=...&end_year=...` with `start_year` capped at 2023

### Frontend Map Rendering
- `frontend/utils.py`: `render_dataset_map()` uses `folium.raster_layers.TileLayer(tiles=tile_url, ...)` to render dataset tiles
- Layer order: basemap (OpenStreetMap) -> TileLayer (dataset) -> GeoJson (AOI) -> LayerControl
- No special handling for external vs. internal tile URLs (both passed directly to TileLayer)

### Logging
- Always use `from src.shared.logging_config import get_logger` then `logger = get_logger(__name__)`

### Agent State
- `src/agent/state.py`: `AgentState(TypedDict)` with fields for messages, aoi, dataset, statistics, insights, charts_data
- Tools return `Command(update={...})` to update state

## No CLAUDE.md or AGENTS.md
No project-level `CLAUDE.md`, `AGENTS.md`, or `CONTRIBUTING.md` files were found in the repository.
