# Codebase Conventions and Patterns

## Project Overview

Project Zeno is a Python monorepo providing a "Language Interface for Maps & WRI/LCL data APIs." It consists of:
- **Backend API** (`src/`): FastAPI application with LangChain/LangGraph agent
- **Frontend** (`frontend/`): Streamlit application with Folium map rendering
- **Tests** (`tests/`): pytest-based test suite
- **Database migrations** (`db/`): Alembic migrations with PostgreSQL/PostGIS

## Language and Runtime

- Python 3.12.8 (pinned in `pyproject.toml`)
- Package manager: **uv** (with `uv.lock` lockfile)
- Dependency groups: `dev`, `frontend` (both default via `[tool.uv] default-groups`)

## Coding Style and Naming Conventions

### Formatting and Linting

Enforced via **Ruff** (configured in `pyproject.toml`):
```toml
[tool.ruff]
line-length = 79

[tool.ruff.lint]
select = ["E", "F", "W", "Q", "I"]
ignore = ["E501"]

[tool.ruff.format]
quote-style = "double"
```

Key rules: double quotes, import sorting (I), pyflakes (F), pycodestyle (E/W). Line length is 79 but E501 (line-too-long) is explicitly ignored.

### Pre-commit Hooks

Defined in `.pre-commit-config.yaml`:
- `trailing-whitespace`, `check-symlinks`, `check-yaml`, `end-of-file-fixer`
- `check-added-large-files` (max 1000KB)
- `detect-private-key`
- `ruff` linter with `--fix`
- `ruff-format` formatter

### Naming Patterns

- **Files**: snake_case for all Python modules (e.g., `pick_aoi.py`, `logging_config.py`, `data_models.py`)
- **Classes**: PascalCase (e.g., `ZenoClient`, `AOIIndex`, `_SharedSettings`)
- **Functions**: snake_case (e.g., `render_aoi_map`, `get_logger`, `fetch_geometry`)
- **Constants**: UPPER_SNAKE_CASE (e.g., `RESULT_LIMIT`, `API_BASE_URL`, `SMALL_MODEL`)
- **Pydantic models**: PascalCase with `Orm` suffix for SQLAlchemy models (e.g., `UserOrm`, `ThreadOrm`), `Model` suffix for Pydantic schemas (e.g., `UserModel`, `CustomAreaModel`)
- **Test files**: `test_*.py` pattern (e.g., `test_threads.py`, `test_pick_aoi.py`)
- **Frontend pages**: numbered with emoji prefix (e.g., `1_Uni_Guana.py`, `2_Threads.py`)

### Import Style

Standard library first, then third-party, then local imports. Ruff enforces import sorting. Example from `src/agent/tools/pick_aoi.py`:
```python
import asyncio
from typing import Annotated, Literal, Optional

import pandas as pd
import structlog
from dotenv import load_dotenv
from langchain_core.messages import ToolMessage

from src.agent.llms import SMALL_MODEL
from src.shared.database import get_connection_from_pool
from src.shared.logging_config import get_logger
```

## Error Handling Patterns

### Backend API (FastAPI)

Errors are raised as `HTTPException` with explicit status codes and detail messages:
```python
raise HTTPException(status_code=500, detail=str(e))
raise HTTPException(
    status_code=status.HTTP_404_NOT_FOUND,
    detail="Thread not found"
)
```

HTTP exceptions are re-raised without conversion (e.g., 429 quota exceeded passes through). Generic exceptions fall back to 500 with `str(e)` as detail.

### Frontend (Streamlit)

Errors caught with broad `try/except Exception` blocks, displayed to user via Streamlit:
```python
try:
    # rendering logic
except Exception as e:
    st.error(f"Error rendering map: {str(e)}")
    st.json(aoi_data)  # Fallback to show raw data
```

Warnings for non-critical issues use `st.warning()`:
```python
st.warning(f"Could not render subregions: {str(e)}")
```

### Logging

Structured logging via **structlog** (`src/shared/logging_config.py`):
```python
from src.shared.logging_config import get_logger
logger = get_logger(__name__)
```

Supports JSON and text output formats, configurable via `LOG_FORMAT` env var. File logging via `RotatingFileHandler` (enabled by default in dev). Context variables bound via `structlog.contextvars`.

## Test Framework and Patterns

### Framework

- **pytest** 8.4.1 with **pytest-asyncio** 1.1.0
- Async mode: `auto` (configured in `pyproject.toml`)
- Default fixture loop scope: `session`

### Test File Organization

```
tests/
  conftest.py          # Shared fixtures (DB, client, auth)
  __init__.py
  agent/
    test_graph.py
  api/
    mock.py
    test_anonymous_users.py
    test_auth.py
    test_threads.py
    test_quotas.py
    ...
  cli/
    test_machine_user_cli.py
  tools/
    test_pick_aoi.py
    test_pick_dataset.py
    test_pull_data.py
    test_generate_insights.py
```

Note: there are NO tests for the frontend (`frontend/`). The `tests/` directory covers only backend API, agent, CLI, and tools.

### Test Patterns

Tests use `@pytest.mark.asyncio` decorator and async functions:
```python
@pytest.mark.asyncio
async def test_list_threads_requires_auth(client):
    """Test that listing threads requires authentication."""
    response = await client.get("/api/threads")
    assert response.status_code == 401
    assert "Missing Bearer token" in response.json()["detail"]
```

### Key Fixtures (from `tests/conftest.py`)

- `client` / `anonymous_client`: `httpx.AsyncClient` with ASGI transport for FastAPI
- `test_db`: Session-scoped, creates/drops all tables
- `test_db_session`: Function-scoped, truncates all tables after each test
- `user` / `user_ds`: Pre-created user ORM objects
- `auth_override`: Callable fixture to mock authentication for specific user IDs
- `thread_factory`: Async factory for creating test threads
- `test_db_pool`: Function-scoped, initializes/closes global DB connection pool

Database: test database uses `{DATABASE_URL}_test` or `TEST_DATABASE_URL` env var. Uses SQLAlchemy async engine with `NullPool`.

### Mocking

- `unittest.mock.patch` for global mocks (e.g., `replay_chat`)
- `unittest.mock.AsyncMock` for async function mocks
- FastAPI dependency overrides: `app.dependency_overrides[dep] = mock_dep`

## CI/CD Configuration

### GitHub Actions Workflows

Located in `.github/workflows/`:

1. **`lint.yml`** - Runs on every push
   - Runs `uvx pre-commit run --show-diff-on-failure --all-files`

2. **`unit-tests.yml`** - Runs on pull requests
   - PostgreSQL service container (PostGIS 17-3.5)
   - Installs deps with `uv sync --frozen`
   - Runs: `uv run pytest tests/api tests/cli tests/agent -v`
   - Note: does NOT run `tests/tools/` in CI (likely requires external APIs)

3. **`docker-build.yml`** / **`docker-build-db.yml`** - Docker image builds

### Quality Gates

- Pre-commit hooks (Ruff lint + format) on every push
- Unit tests on PRs with real PostgreSQL/PostGIS
- No type checking (mypy/pyright not configured)
- No coverage requirements

## Dependency Management

- **uv** as package manager with `pyproject.toml` and `uv.lock`
- Dependencies split into groups:
  - Main: FastAPI, LangChain, SQLAlchemy, structlog, Pydantic, etc.
  - `dev`: pytest, ruff, pre-commit, jupyterlab, locust
  - `frontend`: streamlit, streamlit_folium, folium-vectorgrid, plotly
- Build system: hatchling

## Configuration Management

Settings managed via **pydantic-settings** with `.env` file support:
- `src/shared/config.py`: `_SharedSettings` (database, external APIs)
- `src/api/config.py`: `APISettings` (API-specific settings)
- `src/agent/config.py`: `AgentSettings`

Pattern: private class with underscore prefix, singleton instance:
```python
class _SharedSettings(BaseSettings):
    database_url: str
    model_config = {"env_file": ".env", "extra": "ignore"}

SharedSettings = _SharedSettings()
```

## Existing Abstractions and Utilities to Reuse

### Frontend Map Rendering (`frontend/utils.py`)

This is the PRIMARY file relevant to this issue. Key functions:
- `render_aoi_map(aoi_data, subregion_data)` - Renders AOI polygons on folium map
- `render_dataset_map(dataset_data, aoi_data)` - Renders dataset tile layers with AOI overlay
- `render_charts(charts_data)` - Renders Altair charts
- `render_stream(stream)` - Orchestrates rendering of all output types

Both map functions:
- Use `folium.Map(location=center, zoom_start=N, tiles="OpenStreetMap")` as base
- Use `folium_static()` for Streamlit display (not `st_folium` which "stalls the UI")
- Use `shapely.geometry.shape()` for GeoJSON to bounds conversion
- Handle errors with `try/except` displaying `st.error()` with raw data fallback

### Frontend Dependencies for Maps

From `pyproject.toml` frontend group:
- `streamlit==1.47.0`
- `streamlit_folium==0.25.0`
- `folium-vectorgrid==0.1.3`
- `geopandas==1.0.1`

Note: `folium` itself is not directly listed (it is a dependency of `streamlit_folium`).

### Shared Database (`src/shared/database.py`)

Global connection pool management with `initialize_global_pool()`, `close_global_pool()`, `get_session_from_pool_dependency()`.

### Shared Logging (`src/shared/logging_config.py`)

`get_logger(name)` returns a structlog BoundLogger. Already described above.

### Client (`frontend/client.py`)

`ZenoClient` class wraps API calls with bearer token auth. Used by frontend to fetch geometries, thread data, etc.

## Key Observations for This Issue

1. **No frontend tests exist** - any fix to `frontend/utils.py` will not have automated test coverage unless new tests are added
2. The map rendering in `render_aoi_map` and `render_dataset_map` both hardcode `tiles="OpenStreetMap"` in `folium.Map()`
3. `render_dataset_map` already has `folium.LayerControl().add_to(m2)` but `render_aoi_map` does not
4. The `folium-vectorgrid` package is available but not currently used in `utils.py`
5. The tile provider URL needs to be a reliable free source (constraint from issue) - CartoDB Positron is a common choice
6. Layer z-ordering in Folium is determined by the order layers are added to the map object
