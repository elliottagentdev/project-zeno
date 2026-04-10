# Architecture Reconnaissance

## Project Overview

Project Zeno is a geospatial data assistant ("Language Interface for Maps & WRI/LCL data APIs") built by WRI/Development Seed. It uses an LLM-powered agent to help users query, visualize, and analyze geospatial datasets (tree cover loss, disturbance alerts, etc.) from Global Forest Watch and related sources.

## Directory Layout

```
project-zeno/
  Dockerfile                  # Python 3.12.8 slim, uv-based build
  Makefile                    # Dev workflow targets (dev, api, frontend, test, etc.)
  pyproject.toml              # Project config, dependencies, ruff/pytest config
  uv.lock                     # Locked dependencies
  docker-compose.yaml         # Full production stack (API, frontend, DB, Langfuse, etc.)
  docker-compose.dev.yaml     # Dev infrastructure (PostGIS + migrations only)
  db/                         # Database migrations
    Dockerfile
    alembic/                  # Alembic migration files
    alembic.ini
    entrypoint.sh
  src/                        # Backend Python source
    agent/                    # LangGraph agent
      config.py
      graph.py                # Agent graph definition, prompt, tool orchestration
      llms.py                 # LLM model configuration
      prompts.py              # Prompt templates
      state.py                # AgentState TypedDict (messages, aoi, dataset, charts_data, etc.)
      tools/                  # Agent tools (pick_aoi, pick_dataset, pull_data, generate_insights, etc.)
        code_executors/       # Code execution tools (Gemini executor)
        data_handlers/        # Analytics/data handler abstractions
        datasets_config.py
    api/                      # FastAPI backend
      app.py                  # Main FastAPI application, routes, streaming
      config.py
      data_models.py          # SQLAlchemy ORM models (User, Thread, Rating, CustomArea, etc.)
      schemas.py              # Pydantic request/response schemas
      auth/                   # Authentication (machine user support)
      cli.py
      user_profile_configs/   # Config data for user profiles
    shared/                   # Shared utilities
      config.py               # SharedSettings (database URL, pool config)
      database.py             # Global async SQLAlchemy connection pool
      geocoding_helpers.py
      logging_config.py       # structlog-based logging
    ingest/                   # Data ingestion scripts (GADM, KBA, WDPA, etc.)
  frontend/                   # Streamlit frontend
    Dockerfile
    app.py                    # Streamlit main page, login flow
    client.py                 # ZenoClient - Python HTTP client for the API
    utils.py                  # Rendering utilities (maps, charts, stream processing) -- KEY FILE FOR THIS ISSUE
    index.html                # Standalone Leaflet/HTML client (not Streamlit)
    pages/
      1_Uni_Guana.py          # Main chat agent page
      2_Threads.py            # Thread history page
      3_Evaluation.py         # Evaluation page
    requirements.txt
  tests/                      # Test suite
    conftest.py
    agent/test_graph.py
    api/                      # API endpoint tests
    tools/                    # Tool-level tests
    cli/
    load/
  docs/                       # Documentation
  logs/
```

## Tech Stack

### Backend
- **Language:** Python 3.12.8
- **Web Framework:** FastAPI (uvicorn)
- **Agent Framework:** LangGraph + LangChain (langchain 1.0.8, langgraph 1.0.3)
- **LLM Providers:** Anthropic (langchain-anthropic 1.1.0), OpenAI (langchain-openai 1.0.3), Google Gemini (langchain-google-genai 3.1.0, google-genai 1.51.0)
- **Database:** PostgreSQL with PostGIS (postgis/postgis:17-3.5 Docker image)
- **ORM:** SQLAlchemy 2.0.41 (async via asyncpg)
- **Migrations:** Alembic 1.16.4
- **Observability:** Langfuse 3.10.1, structlog 25.4.0
- **Geo libraries:** GeoPandas 1.0.1, Fiona, Shapely, GeoAlchemy2
- **Package Manager:** uv (astral)

### Frontend
- **Framework:** Streamlit 1.47.0
- **Mapping:** Folium (via streamlit_folium 0.25.0), folium-vectorgrid 0.1.3
- **Charts:** Altair (via Streamlit), Plotly 6.3.0
- **Secondary client:** Standalone HTML page using Leaflet.js 1.9.4 (`frontend/index.html`)

### Build & Deployment
- **Containerization:** Docker (single Dockerfile, multi-service docker-compose)
- **Dev workflow:** Makefile targets + docker-compose.dev.yaml for local PostGIS
- **Linting:** Ruff (line-length 79, E/F/W/Q/I rules)
- **Testing:** pytest 8.4.1 with pytest-asyncio
- **CI:** Pre-commit hooks with ruff

## Key Entry Points

1. **API:** `src/api/app.py` -- FastAPI app, mounted at port 8000. Handles auth, chat streaming, thread management, custom areas.
2. **Frontend:** `frontend/app.py` -- Streamlit main page. Run via `streamlit run frontend/app.py`.
3. **Agent:** `src/agent/graph.py` -- LangGraph agent graph. Tools: pick_aoi, pick_dataset, pull_data, generate_insights, get_capabilities.
4. **Frontend pages:** `frontend/pages/1_Uni_Guana.py` -- Main chat UI, invokes `render_stream()` from `utils.py`.

## Database Schema (ORM Models in `src/api/data_models.py`)

- **UserOrm** -- users table (id, name, email, user_type, profile fields)
- **ThreadOrm** -- threads table (conversation threads per user)
- **RatingOrm** -- ratings table (user feedback)
- **CustomAreaOrm** -- custom_areas table (user-defined AOIs)
- **DailyUsageOrm** -- daily_usage table (prompt quota tracking)
- **WhitelistedUserOrm** -- whitelisted_users table
- **MachineUserKeyOrm** -- machine user API keys
- LangGraph persistence tables (via alembic migration `b2c5d0a31a8b`)

Database uses `postgresql+asyncpg` connection string. Global connection pool managed in `src/shared/database.py`.

## Map Rendering Architecture (Critical for This Issue)

### Folium Map Creation Points in `frontend/utils.py`

There are exactly **two functions** that create Folium maps:

1. **`render_aoi_map(aoi_data, subregion_data=None)`** (line 70)
   - Creates map: `folium.Map(location=center, zoom_start=5, tiles="OpenStreetMap")` (line 105)
   - Adds AOI GeoJson overlay (gray fill, weight 2)
   - Optionally adds subregion overlays (red fill)
   - Renders via `folium_static(m, width=700, height=400)` (line 153)
   - Does NOT have LayerControl
   - Does NOT have any additional basemap tile layers

2. **`render_dataset_map(dataset_data, aoi_data=None)`** (line 160)
   - Creates map: `folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap")` (line 194-195)
   - Adds dataset tile layer via `folium.raster_layers.TileLayer(tiles=tile_url, ...)` with `overlay=True` (line 200-206)
   - Optionally adds AOI GeoJson overlay (blue fill)
   - Adds `folium.LayerControl().add_to(m2)` (line 227)
   - Renders via `folium_static(m2, width=700, height=400)` (line 231)

### How Maps Are Triggered

In `render_stream()` (line 648), the stream update dict is inspected:
- If `"aoi"` key present: calls `render_aoi_map(aoi_data, subregion_data)`
- If `"dataset"` key present: calls `render_dataset_map(dataset_data, aoi_data)` with AOI as optional overlay
- If `"charts_data"` key present: renders charts

The agent state (`src/agent/state.py`) includes `aoi: dict` and `dataset: dict` fields that flow through tool calls.

### Layer Order (Current)

In `render_dataset_map`:
1. Base tiles: `tiles="OpenStreetMap"` passed to `folium.Map()` constructor -- this is the default basemap
2. Dataset tile layer: added via `folium.raster_layers.TileLayer()` with `overlay=True`
3. AOI GeoJson: added after dataset tiles
4. LayerControl: added last

In `render_aoi_map`:
1. Base tiles: `tiles="OpenStreetMap"` passed to `folium.Map()` constructor
2. AOI GeoJson overlay
3. Subregion GeoJson overlays (if any)
4. No LayerControl

### The Issue Context

The PROMPT describes that "the Light tile layer fails to render." The current code uses `tiles="OpenStreetMap"` in both map functions. The issue mentions a LayerControl with Light/Satellite options visible to the user, but only the `render_dataset_map` function has a `LayerControl`. There are no explicit Light/Dark/Satellite tile layers being added as separate `TileLayer` objects -- the only additional tile layers are dataset-specific.

The `tiles="OpenStreetMap"` parameter in `folium.Map()` uses Folium's built-in OpenStreetMap tile provider. If this tile service is unreliable or blocked, the map background appears blank.

### Secondary Map Client (`frontend/index.html`)

The standalone HTML client uses Leaflet.js directly (line 84-88):
```javascript
const map = L.map('map').setView([20, 80], 4);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 18,
  attribution: '... OpenStreetMap contributors'
}).addTo(map);
```
This is a separate client and not part of the Streamlit frontend.

### Dependencies Relevant to Maps

From `pyproject.toml` frontend dependency group:
- `streamlit==1.47.0`
- `streamlit_folium==0.25.0`
- `folium-vectorgrid==0.1.3`
- `geopandas==1.0.1`

Folium itself is a transitive dependency of `streamlit_folium`. The specific folium version is locked in `uv.lock`.

### Docker/Deployment Notes

- Production: `docker-compose.yaml` runs frontend via `uv run streamlit run src/frontend/app.py`
- Dev: `make frontend` runs `uv run streamlit run frontend/app.py --server.port=8501`
- The frontend container mounts source code as volumes for hot-reload
