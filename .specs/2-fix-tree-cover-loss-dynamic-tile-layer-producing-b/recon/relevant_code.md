# Relevant Code Reconnaissance: Tree Cover Loss Tile Layer Fix

## 1. Primary File: `src/agent/tools/pick_dataset.py`

This is the core file where tile URLs are constructed. The `pick_dataset` tool function (line 236-319) handles URL construction for all datasets.

### Critical Tile URL Construction Logic (lines 283-312)

```python
start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
end_date = datetime.strptime(end_date, "%Y-%m-%d").date()

if not selection_result.tile_url.startswith("http"):
    selection_result.tile_url = (
        SharedSettings.eoapi_base_url + selection_result.tile_url
    )

if selection_result.dataset_id == DIST_ALERT_ID:
    selection_result.tile_url += (
        f"&start_date={start_date}&end_date={end_date}"
    )
elif selection_result.dataset_id in [LAND_COVER_CHANGE_ID, GRASSLANDS_ID]:
    if end_date.year in range(2000, 2023):
        selection_result.tile_url = selection_result.tile_url.format(
            year=end_date.year
        )
    else:
        selection_result.tile_url = selection_result.tile_url.format(
            year="2022"
        )
elif selection_result.dataset_id == TREE_COVER_LOSS_ID:
    if end_date.year in range(2001, 2025):
        # GFW tile service only accepts start_year <= 2023 even though analytics data goes to 2024
        tile_start_year = min(start_date.year, 2023)
        selection_result.tile_url += (
            f"&start_year={tile_start_year}&end_year={end_date.year}"
        )
    else:
        selection_result.tile_url += "&start_year=2001&end_year=2024"
```

### KEY FINDING: Tile URL Template Placeholder Conflict

The TCL base tile URL in `analytics_datasets.yml` (line 588) uses **single braces** for tile coordinates:

```
https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color
```

The Grasslands tile URL (line 309) uses **double braces** for tile coordinates:

```
/raster/collections/grasslands-v-1/items/grasslands-{year}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?...
```

This is significant because:
- Grasslands URL uses `{year}` (single brace) for Python `.format()` substitution AND `{{z}}/{{x}}/{{y}}` (double braces) which survive `.format()` as `{z}/{x}/{y}` for Folium/Leaflet.
- TCL URL uses `{z}/{x}/{y}` (single braces). Since TCL does NOT go through `.format()` (it uses string concatenation `+=` instead), the single braces are correct for Folium/Leaflet.

**However**, the DIST-ALERT URL also uses single braces and reportedly works. So the brace escaping is NOT the root cause.

### Dataset ID Constants (from `analytics_handler.py`, lines 85-134)

```python
DIST_ALERT_ID = [ds["dataset_id"] for ds in DATASETS if ds["dataset_name"] == "Global all ecosystem disturbance alerts (DIST-ALERT)"][0]  # 0
GRASSLANDS_ID = [ds["dataset_id"] for ds in DATASETS if ds["dataset_name"] == "Global natural/semi-natural grassland extent"][0]  # 2
TREE_COVER_LOSS_ID = [ds["dataset_id"] for ds in DATASETS if ds["dataset_name"] == "Tree cover loss"][0]  # 4
TREE_COVER_LOSS_BY_DRIVER_ID = [ds["dataset_id"] for ds in DATASETS if ds["dataset_name"] == "Tree cover loss by dominant driver"][0]  # 8
```

### Data Models

**`DatasetSelectionResult`** (lines 114-145) - Pydantic model that flows through the system:
```python
class DatasetSelectionResult(DatasetOption):
    tile_url: str = Field(...)
    dataset_name: str = Field(...)
    analytics_api_endpoint: str = Field(...)
    # ... other fields
```

The result is serialized via `selection_result.model_dump()` and placed in the graph state under `"dataset"` key (line 316).

## 2. Dataset Configuration: `src/agent/tools/analytics_datasets.yml`

All dataset metadata is defined here and loaded by `src/agent/tools/datasets_config.py`:

```python
ANALYTICS_DATASETS_PATH = Path(__file__).parent / "analytics_datasets.yml"
with open(ANALYTICS_DATASETS_PATH) as f:
    DATASETS = yaml.safe_load(f)["datasets"]
```

### TCL Tile URL (line 588)

```yaml
tile_url: "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color"
```

After `pick_dataset` appends year params, the final URL looks like:
```
https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?tree_cover_density_threshold=30&render_type=true_color&start_year=2020&end_year=2024
```

### Grasslands Tile URL (line 309) -- WORKING

```yaml
tile_url: "/raster/collections/grasslands-v-1/items/grasslands-{year}/tiles/WebMercatorQuad/{{z}}/{{x}}/{{y}}.png?colormap=..."
```

After `pick_dataset` runs `.format(year=2022)` and prepends `eoapi_base_url`:
```
https://eoapi.staging.globalnaturewatch.org/raster/collections/grasslands-v-1/items/grasslands-2022/tiles/WebMercatorQuad/{z}/{x}/{y}.png?colormap=...
```

### DIST-ALERT Tile URL (line 14) -- WORKING

```yaml
tile_url: "https://tiles.globalforestwatch.org/umd_glad_dist_alerts/latest/dynamic/{z}/{x}/{y}.png?render_type=true_color"
```

After `pick_dataset` appends date params:
```
https://tiles.globalforestwatch.org/umd_glad_dist_alerts/latest/dynamic/{z}/{x}/{y}.png?render_type=true_color&start_date=2024-01-01&end_date=2024-12-31
```

### Comparison: TCL vs DIST-ALERT vs Grasslands

| Aspect | TCL (broken) | DIST-ALERT (working) | Grasslands (working) |
|--------|-------------|---------------------|---------------------|
| Tile provider | GFW external | GFW external | eoAPI internal |
| URL prefix | absolute (https://) | absolute (https://) | relative (prepended) |
| Tile coord format | `{z}/{x}/{y}` | `{z}/{x}/{y}` | `{{z}}/{{x}}/{{y}}` -> `{z}/{x}/{y}` |
| Year params | `&start_year=X&end_year=Y` appended | `&start_date=X&end_date=Y` appended | `{year}` in path, `.format()` |
| `render_type` | `true_color` | `true_color` | N/A (uses colormap) |
| Recent fix | b7bfe83 cap start_year at 2023 | None | None |

## 3. Frontend Rendering: `frontend/utils.py`

### `render_dataset_map()` (lines 160-265)

This function receives `dataset_data` dict and renders via Folium:

```python
def render_dataset_map(dataset_data, aoi_data=None):
    tile_url = dataset_data.get("tile_url")
    # ...
    m2 = folium.Map(location=center, zoom_start=zoom_start, tiles="OpenStreetMap")

    dataset_name = dataset_data.get("data_layer", "Dataset Layer")
    folium.raster_layers.TileLayer(
        tiles=tile_url,
        attr="Dataset Tiles",
        name=dataset_name,
        overlay=True,
        control=True,
    ).add_to(m2)
```

**Important**: `folium.raster_layers.TileLayer` expects `{z}`, `{x}`, `{y}` placeholders in the tile URL. No additional format parameters like `tms`, `maxZoom`, or `minZoom` are passed. No `cross_origin` or CORS headers are configured.

### `render_stream()` (lines 648-746)

This is the main rendering pipeline called from frontend pages. At line 695-701:

```python
if "dataset" in update:
    dataset_data = update["dataset"]
    aoi_data = (
        update.get("aoi") or aoi_data
    )  # Include AOI as overlay if available
    render_dataset_map(dataset_data, aoi_data)
```

The `dataset_data` dict passed here is exactly the `selection_result.model_dump()` from `pick_dataset`. Note that `render_dataset_map` looks for `dataset_data.get("data_layer")` for the name (line 199) but `DatasetSelectionResult` has `dataset_name`, not `data_layer`. This means the layer always gets the default name "Dataset Layer".

### Layer Rendering Order in `render_stream()`

1. AOI map rendered first via `render_aoi_map()` (line 693) -- creates its own `folium.Map` instance
2. Dataset map rendered second via `render_dataset_map()` (line 701) -- creates a SEPARATE `folium.Map` instance
3. These are TWO separate maps, not layers on the same map

**Critical observation**: The AOI and dataset are rendered as separate maps (`m` and `m2`), not as layers on a single map. The `render_dataset_map` does add the AOI as an overlay on the dataset map (lines 209-224), but only if `aoi_data` includes a `"geometry"` key. The `aoi_data` from `render_stream` is the raw `update["aoi"]` dict which has `src_id`, `name`, etc. -- NOT the geometry itself. The geometry is fetched inside `render_aoi_map` via `client.fetch_geometry()` but NOT passed to `render_dataset_map`.

## 4. Frontend Sidebar Hardcoded URLs: `frontend/utils.py` (lines 779-801)

The sidebar `display_sidebar_selections()` has hardcoded TCL test data:

```python
"Tree Cover Loss": {
    "dataset": {
        "dataset_id": 0,  # NOTE: Wrong ID! TCL should be 4, not 0
        "source": "GFW",
        "dataset_name": "Tree cover loss",
        "tile_url": "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=25&render_type=true_color",
        "context_layer": "Primary forest",
        "threshold": "30",
    }
},
```

Note: This hardcoded URL has `tree_cover_density_threshold=25` while the YAML config has `threshold=30`. Also the `dataset_id` is `0` (should be `4`).

## 5. Agent State: `src/agent/state.py`

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    user_persona: str
    aoi: dict                    # pick-aoi tool
    subtype: str
    aoi_selection: AOISelection
    dataset: dict                # pick-dataset tool -- this is where tile_url lives
    start_date: str
    end_date: str
    statistics: Annotated[list[Statistics], operator.add]
    insights: list
    charts_data: list
    codeact_parts: list[CodeActPart]
```

The `dataset` field is a plain dict (serialized from `DatasetSelectionResult.model_dump()`).

## 6. Test File: `tests/tools/test_pick_dataset.py`

### Key test: `test_tile_url_contains_date` (line 306)

This test actually fetches tiles from the real tile server to verify URLs work:

```python
async def test_tile_url_contains_date(dataset):
    # ...
    tile_url_format = tile_url.format(z=3, x=5, y=3)
    if "eoapi.globalnaturewatch.org" in tile_url_format:
        tile_url_format = tile_url_format.replace(
            "eoapi.globalnaturewatch.org", "eoapi-cache.globalnaturewatch.org"
        )
    response = requests.get(tile_url_format)
    assert response.status_code == 200
```

This test calls `.format(z=3, x=5, y=3)` on the tile URL. For TCL, the base URL already has `{z}/{x}/{y}` which would be substituted. But for Grasslands, the URL has `{{z}}/{{x}}/{{y}}` which becomes `{z}/{x}/{y}` after the first `.format(year=...)` call, then this test's `.format(z=3, x=5, y=3)` substitutes the tile coordinates. The test covers TREE_COVER_LOSS and confirms the URL returns HTTP 200.

## 7. Related Test: `tests/tools/test_generate_insights.py`

Contains a hardcoded TCL tile URL in test fixtures (line 47):
```python
"tile_url": "https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/{z}/{x}/{y}.png?start_year=2001&end_year=2024&tree_cover_density_threshold=25&render_type=true_color",
```

## 8. Shared Config: `src/shared/config.py`

```python
eoapi_base_url: str = Field(
    default="https://eoapi.staging.globalnaturewatch.org",
    alias="EOAPI_BASE_URL",
)
```

This is prepended to relative tile URLs (like Grasslands) in `pick_dataset.py` line 286-288.

## 9. Summary of Potential Root Causes

1. **GFW Tile Service Behavior**: The TCL tile URL may require specific `render_type` values or additional parameters not currently provided. The `render_type=true_color` may not produce visible pink/red pixels for TCL -- it may need a different render type.

2. **CORS Issues**: The GFW external tile service (`tiles.globalforestwatch.org`) may have CORS restrictions that prevent browser-based tile loading via Folium/Leaflet. However, DIST-ALERT uses the same domain and works, so this is less likely unless TCL-specific endpoints have different CORS policies.

3. **Year Parameter Interaction**: The `render_type=true_color` combined with `start_year`/`end_year` appended params may conflict or produce transparent/empty tiles. The base URL already has `tree_cover_density_threshold=30` in the query string.

4. **AOI Geometry Not Passed to Dataset Map**: In `render_stream()`, the `aoi_data` passed to `render_dataset_map` lacks the actual geometry (it has `src_id` etc. but not the GeoJSON). The `render_dataset_map` function checks for `"geometry" in aoi_data` (line 179) which would be False, so the map defaults to `center=[0, 0]` with `zoom_start=2` -- a global view. At zoom level 2, the GFW tile service may not return visible TCL pixels (they are 30m resolution data that may only be visible at higher zoom levels).

5. **Layer Order**: Both `render_aoi_map` and `render_dataset_map` create independent `folium.Map` instances. They are rendered as separate maps, not as layers on the same map. This violates the requirement of "basemap -> dataset tiles -> AOI outline" on a single map.
