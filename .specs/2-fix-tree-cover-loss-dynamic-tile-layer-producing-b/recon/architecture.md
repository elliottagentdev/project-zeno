# Architecture Reconnaissance: Project Zeno

## 1. Project Overview

Project Zeno is a geospatial AI agent ("Global Nature Watch's Geospatial Agent") that answers natural-language queries about land use, forest loss, and ecosystem data. It combines an LLM-powered agent backend with a Streamlit frontend that renders maps (via Folium), charts (via Altair), and chat responses.

**Repository root:** `/mnt/e/agentdev/projects/project-zeno/`

## 2. Directory Layout

```
project-zeno/
  Dockerfile              # Python 3.12.8-slim, uv package manager
  Makefile                # Dev commands (up, down, api, frontend, test)
  pyproject.toml          # Project config, dependencies, ruff/pytest settings
  uv.lock                 # Lockfile for uv
  docker-compose.yaml     # Production: api, frontend, db, migrate, langfuse stack
  docker-compose.dev.yaml # Dev: db (PostGIS 17-3.5), test-db, migrate
  db/
    Dockerfile            # Migration container
    alembic/              # Alembic migrations (19 versions)
    alembic.ini
    entrypoint.sh
  src/
    agent/                # LLM agent logic (LangGraph/LangChain)
      config.py           # AgentSettings
      graph.py            # Agent graph definition, checkpointer setup
      llms.py             # Model definitions (MODEL, SMALL_MODEL)
      prompts.py          # System prompt wording instructions
      state.py            # AgentState TypedDict (messages, aoi, dataset, statistics, etc.)
      tools/
        __init__.py       # Exports: generate_insights, get_capabilities, pick_aoi, pick_dataset, pull_data
        pick_dataset.py   # RAG-based dataset selection + tile URL construction
        pick_aoi.py       # Area of interest selection
        pull_data.py      # Data retrieval from analytics API
        generate_insights.py  # Chart/insight generation
        get_capabilities.py   # Agent capability info
        datasets_config.py    # Loads analytics_datasets.yml -> DATASETS list
        analytics_datasets.yml # All dataset definitions (IDs, tile URLs, metadata)
        code_executors/       # Code execution (Gemini-based)
        data_handlers/
          base.py             # DataSourceHandler abstract base
          analytics_handler.py # GFW Analytics API handler (defines dataset ID constants)
          example_handler.py
    api/                  # FastAPI backend
      app.py              # Main FastAPI app (~500 lines), streaming chat endpoint
      config.py           # APISettings
      data_models.py      # SQLAlchemy ORM models (User, Thread, Rating, DailyUsage, etc.)
      schemas.py          # Pydantic request/response schemas
      cli.py              # CLI entrypoint
      auth/               # Auth (machine_user.py)
      user_profile_configs/ # Static config for countries, sectors, topics, etc.
    ingest/               # Data ingestion scripts (GADM, KBA, WDPA, commodities, embeddings)
    shared/
      config.py           # SharedSettings (database_url, eoapi_base_url, pool settings)
      database.py         # Global async SQLAlchemy engine/session pool
      geocoding_helpers.py
      logging_config.py   # structlog-based logging
  frontend/               # Streamlit app
    app.py                # Landing page, auth
    client.py             # ZenoClient - HTTP client to API
    utils.py              # Map rendering (render_aoi_map, render_dataset_map), chart rendering, sidebar
    pages/
      1_Uni_Guana.py      # Main chat + map page
      2_Threads.py        # Thread history
      3_Evaluation.py     # Eval page
  tests/
    conftest.py
    agent/                # Agent tests
    api/                  # API tests
    cli/                  # CLI tests
    tools/                # Tool tests
    load/                 # Load tests
```

## 3. Tech Stack

- **Language:** Python 3.12.8
- **Package Manager:** uv (with lockfile)
- **Backend Framework:** FastAPI (0.116.1) + Uvicorn
- **Frontend Framework:** Streamlit (1.47.0) with streamlit-folium (0.25.0)
- **AI/Agent Framework:** LangChain (1.0.8), LangGraph (1.0.3), LangChain-Anthropic, LangChain-Google-GenAI
- **Map Rendering:** Folium (via streamlit_folium), folium-vectorgrid
- **Charts:** Altair (via Streamlit), Plotly
- **Database:** PostgreSQL with PostGIS (postgis/postgis:17-3.5), SQLAlchemy 2.0 (async), Alembic
- **Embeddings:** Google Generative AI Embeddings (gemini-embedding-001), InMemoryVectorStore
- **Observability:** Langfuse (self-hosted with ClickHouse, Redis, MinIO, Postgres)
- **HTTP Client:** httpx (async), requests (sync in frontend)
- **Linting/Formatting:** ruff (line-length 79)
- **Testing:** pytest, pytest-asyncio
- **Other:** pydantic v2, pydantic-settings, structlog, cachetools, boto3/s3fs

## 4. Build System and Deployment Model

### Build
- **Dockerfile** (`/mnt/e/agentdev/projects/project-zeno/Dockerfile`): Python 3.12.8-slim-bookworm base, installs uv, copies source, runs `uv sync --frozen --no-dev`.
- **DB Migration Dockerfile** (`/mnt/e/agentdev/projects/project-zeno/db/Dockerfile`): Separate container for Alembic migrations.

### Deployment (Production)
- `docker-compose.yaml` defines services: `api`, `frontend`, `db` (PostGIS), `migrate`, plus full Langfuse stack (langfuse-web, langfuse-worker, clickhouse, minio, redis, postgres for langfuse).
- API runs via `uv run uvicorn src.api.app:app --reload --host 0.0.0.0` on port 8000.
- Frontend runs via `uv run streamlit run src/frontend/app.py --server.port=8501`.

### Deployment (Development)
- `docker-compose.dev.yaml` provides only `db` (port 5433:5432), `test-db` (port 5434:5432), and `migrate`.
- `Makefile` provides `make dev`, `make api`, `make frontend`, `make test`.
- Local dev runs API and frontend directly via uv on host, connecting to dockerized DB.

## 5. Key Entry Points and Main Modules

### API Entry Point
- **`/mnt/e/agentdev/projects/project-zeno/src/api/app.py`**: FastAPI application. Defines streaming chat endpoint, thread management, auth, quota management.
- Lifespan handler initializes global DB pool (`initialize_global_pool()`), LangGraph checkpointer pool.

### Agent Entry Point
- **`/mnt/e/agentdev/projects/project-zeno/src/agent/graph.py`**: Creates the LangGraph agent with tools (`pick_aoi`, `pick_dataset`, `pull_data`, `generate_insights`, `get_capabilities`). Uses `create_agent()` from LangChain with `AgentState` schema and PostgreSQL checkpointer.

### Frontend Entry Point
- **`/mnt/e/agentdev/projects/project-zeno/frontend/app.py`**: Streamlit landing page with auth.
- **`/mnt/e/agentdev/projects/project-zeno/frontend/pages/1_Uni_Guana.py`**: Main chat interface. Uses `ZenoClient` to stream responses, calls `render_stream()` from `utils.py`.

### Agent Workflow (relevant to this issue)
1. User query enters via chat endpoint in `app.py`.
2. Agent calls `pick_aoi` to select area of interest.
3. Agent calls `pick_dataset` to select dataset + construct tile URL.
4. Agent calls `pull_data` to fetch analytics data.
5. Agent calls `generate_insights` to create charts.
6. State updates (including `dataset` dict with `tile_url`) stream to frontend.
7. Frontend `render_stream()` in `utils.py` detects `"dataset"` in state update and calls `render_dataset_map()`.
8. `render_dataset_map()` creates a Folium map with `folium.raster_layers.TileLayer(tiles=tile_url, ...)`.

## 6. Database Schema and Data Layer

### Main Database (zeno-data)
- **Engine:** PostGIS 17-3.5 via SQLAlchemy async (asyncpg driver)
- **ORM Models** (`/mnt/e/agentdev/projects/project-zeno/src/api/data_models.py`): UserOrm, ThreadOrm, RatingOrm, DailyUsageOrm, CustomAreaOrm, WhitelistedUserOrm
- **Migrations:** Alembic with 19 migration versions in `/mnt/e/agentdev/projects/project-zeno/db/alembic/versions/`
- **Connection Pool:** Global async pool in `/mnt/e/agentdev/projects/project-zeno/src/shared/database.py` (SQLAlchemy create_async_engine)
- **Checkpointer:** Separate psycopg AsyncConnectionPool in `graph.py` for LangGraph state persistence

### Dataset Configuration (not in DB)
- **`/mnt/e/agentdev/projects/project-zeno/src/agent/tools/analytics_datasets.yml`**: YAML file containing all dataset definitions. Each dataset has: `dataset_id`, `dataset_name`, `tile_url`, `analytics_api_endpoint`, `context_layers`, `variables`, metadata fields.
- Loaded once by `/mnt/e/agentdev/projects/project-zeno/src/agent/tools/datasets_config.py` into `DATASETS` list.
- Dataset embeddings stored in flat file (`data/gnw-dataset-index-gemini-v1`) loaded into InMemoryVectorStore for RAG retrieval.

### External Data APIs
- **GFW Analytics API:** `https://analytics.globalnaturewatch.org` -- used by `AnalyticsHandler` in `analytics_handler.py` for fetching statistics.
- **eoAPI:** `https://eoapi.staging.globalnaturewatch.org` -- tile server for project-hosted raster datasets (Grasslands, Land Cover Change). Base URL in `SharedSettings.eoapi_base_url`.
- **GFW Tile Service:** `https://tiles.globalforestwatch.org` -- external tile server for DIST-ALERT and Tree Cover Loss datasets. Used as absolute URLs in `analytics_datasets.yml`.

## 7. Tile URL Construction (Critical Path for This Issue)

The tile URL for each dataset is defined in `analytics_datasets.yml` and processed in `pick_dataset.py` (lines 286-312):

1. **Relative URLs** (eoAPI-hosted datasets like Grasslands, Land Cover Change): Prefixed with `SharedSettings.eoapi_base_url` (line 287-289).
2. **Absolute URLs** (GFW-hosted datasets like DIST-ALERT, TCL): Used as-is since they start with `http`.

### Dataset-specific URL construction in `pick_dataset.py`:
- **DIST-ALERT** (dataset_id=0): Appends `&start_date={}&end_date={}` query params.
- **Land Cover Change / Grasslands** (dataset_id=1, 2): Substitutes `{year}` in the path template via `.format(year=...)`.
- **Tree Cover Loss** (dataset_id=4): Appends `&start_year={}&end_year={}` query params. The `start_year` is capped at 2023 via `min(start_date.year, 2023)` (commit b7bfe83).

### TCL tile URL from YAML (line 588):
```
https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color
```

### Grasslands tile URL from YAML (line 309):
```
/raster/collections/grasslands-v-1/items/grasslands-{year}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?colormap=...&assets=asset&expression=...&asset_as_band=True
```

Key difference: Grasslands uses double-braces `{{z}}/{{x}}/{{y}}` (which survive Python `.format()` to become `{z}/{x}/{y}`), while TCL uses single braces `{z}/{x}/{y}` (which are Folium template placeholders, not Python format targets).

## 8. Frontend Map Rendering

**`/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`**, function `render_dataset_map()` (line 160-265):
- Takes `dataset_data` dict (from agent state) and optional `aoi_data`.
- Extracts `tile_url` from `dataset_data`.
- Creates `folium.Map` with OpenStreetMap basemap.
- Adds `folium.raster_layers.TileLayer(tiles=tile_url, ...)` as overlay.
- Adds AOI as `folium.GeoJson` overlay on top.
- Adds `folium.LayerControl()`.
- Renders via `folium_static(m2, width=700, height=400)`.

Layer order: basemap (Map tiles) -> dataset TileLayer (overlay=True) -> GeoJson AOI -> LayerControl.

**`/mnt/e/agentdev/projects/project-zeno/frontend/utils.py`**, function `render_stream()` (line 648+):
- Parses streaming state updates.
- Calls `render_aoi_map()` when `"aoi"` in update.
- Calls `render_dataset_map()` when `"dataset"` in update.
- Calls `render_charts()` when `"charts_data"` in update.

Note: `render_dataset_map()` receives `aoi_data` from the update dict, but this is the raw aoi dict from agent state (which has `src_id`, `name`, etc.) -- not a geometry. The function checks for `"geometry"` key in `aoi_data` (line 179), which may not be present in the agent state's aoi dict.
