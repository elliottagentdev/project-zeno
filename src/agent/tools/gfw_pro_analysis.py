"""GFW Pro deforestation and disturbance alert analysis tool."""

import asyncio
import os
import re
import threading
import time
from datetime import datetime
from typing import Annotated, Dict, Optional

import warnings

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

# Alert date epoch: days are counted from 2014-12-31
ALERT_EPOCH = datetime(2014, 12, 31)

# Module-level dataset cache
_datasets_cache: Optional[dict[str, xr.Dataset]] = None
_datasets_lock = threading.Lock()


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
        s3_storage_options = {
            "key": os.environ.get("AWS_ACCESS_KEY_ID"),
            "secret": os.environ.get("AWS_SECRET_ACCESS_KEY"),
        }
        datasets = {}

        for key, s3_uri in S3_ZARR_PATHS.items():
            if base_path:
                # Extract filename, strip trailing slashes
                zarr_name = s3_uri.rstrip("/").rsplit("/", 1)[-1]
                path = os.path.join(base_path, zarr_name)
                open_kwargs: dict = {}
            else:
                path = s3_uri
                open_kwargs = {"storage_options": s3_storage_options}

            logger.info(
                "Opening zarr dataset",
                key=key,
                path=path,
            )
            datasets[key] = xr.open_zarr(
                path, chunks="auto", **open_kwargs
            )

        _datasets_cache = datasets
        return _datasets_cache


def _bbox_slice(
    ds: xr.Dataset, geojson_geom: dict
) -> xr.Dataset:
    """Lazy bbox slice of dataset — no data is loaded."""
    geom = shape(geojson_geom)
    minx, miny, maxx, maxy = geom.bounds

    if "lon" in ds.dims:
        x_dim, y_dim = "lon", "lat"
    else:
        x_dim, y_dim = "x", "y"

    y_vals = ds[y_dim].values
    if y_vals[0] < y_vals[-1]:
        y_slice = slice(miny, maxy)
    else:
        y_slice = slice(maxy, miny)

    return ds.sel({x_dim: slice(minx, maxx), y_dim: y_slice})


def _build_mask(
    ds: xr.Dataset, geojson_geom: dict
) -> np.ndarray:
    """Build a boolean polygon mask for the bbox-sliced grid.

    Uses rasterio.features.geometry_mask which operates on
    coordinates only (no pixel data loaded).
    """
    from rasterio.features import geometry_mask
    from rasterio.transform import from_bounds

    geom = shape(geojson_geom)
    if "lon" in ds.dims:
        x_dim, y_dim = "lon", "lat"
    else:
        x_dim, y_dim = "x", "y"

    xs = ds[x_dim].values
    ys = ds[y_dim].values
    width, height = len(xs), len(ys)

    x_min, x_max = float(xs.min()), float(xs.max())
    y_min, y_max = float(ys.min()), float(ys.max())
    transform = from_bounds(x_min, y_min, x_max, y_max, width, height)

    if geojson_geom.get("type") == "GeometryCollection":
        geoms = list(geom.geoms)
    else:
        geoms = [geom]

    # geometry_mask returns True where pixels are OUTSIDE the geometry
    inverted = geometry_mask(
        geoms, out_shape=(height, width), transform=transform,
        invert=True,
    )
    return inverted  # True = inside polygon


def _sanitize_csv_field(value: str) -> str:
    """Strip leading characters that could trigger CSV injection."""
    return re.sub(r'^[=+\-@]+', '', value)


def run_analysis(
    geojson_geometry: dict, name: str
) -> pd.DataFrame:
    """Compute deforestation metrics for a single AOI.

    Follows the reference query3.py approach: clip zarr datasets,
    compute via dask lazy evaluation, sum and return as DataFrame.

    Returns single-row DataFrame with columns:
    name, total area, sbtn_area, sbtn_loss_area, jrc_area,
    jrc_loss_area, indig_area, alert_area, sbtn_alert_area,
    jrc_alert_area (all areas in hectares).
    """
    t_start = time.perf_counter()
    datasets = get_datasets()
    t_datasets = time.perf_counter()
    logger.info(
        "Analysis started",
        aoi=name,
        datasets_load_s=round(t_datasets - t_start, 2),
    )

    # Convert alert start date to days since 2014-12-31
    alert_start_str = os.environ.get(
        "GFW_PRO_ALERT_START_DATE", DEFAULT_ALERT_START_DATE
    )
    alert_start_days = (
        datetime.strptime(alert_start_str, "%Y-%m-%d") - ALERT_EPOCH
    ).days

    TILE = 4096  # spatial tile size — peak mem ~4 tiles × 8 vars × 4B ≈ 500 MB

    # --- Phase 1: Lazy bbox slice (no data loaded) ---
    t0 = time.perf_counter()
    loss_raw = _bbox_slice(datasets["mergedLoss"], geojson_geometry).squeeze("band")
    sbtn_raw = _bbox_slice(datasets["sbtn"], geojson_geometry).squeeze("band")
    jrc_raw = _bbox_slice(datasets["jrc"], geojson_geometry).squeeze("band")
    intdist_raw = _bbox_slice(datasets["intdist"], geojson_geometry).squeeze("band")
    t_bbox = time.perf_counter() - t0

    ny, nx = loss_raw.sizes["y"], loss_raw.sizes["x"]
    total_pixels = nx * ny
    geom = shape(geojson_geometry)
    bbox = geom.bounds

    logger.info(
        "Bbox slice complete",
        aoi=name,
        bbox=[round(c, 3) for c in bbox],
        grid_shape={"x": nx, "y": ny},
        total_pixels=total_pixels,
        bbox_slice_s=round(t_bbox, 2),
    )

    # --- Phase 2: Build polygon mask (coords only, ~few MB) ---
    t0 = time.perf_counter()
    mask_full = _build_mask(loss_raw, geojson_geometry)
    t_mask = time.perf_counter() - t0
    mask_pct = round(float(mask_full.sum()) / mask_full.size * 100, 1)
    logger.info(
        "Polygon mask built",
        aoi=name,
        mask_shape=mask_full.shape,
        mask_true_pct=mask_pct,
        mask_build_s=round(t_mask, 2),
    )

    # --- Phase 3: Tiled summation (constant memory) ---
    # Accumulate sums across spatial tiles. Each tile loads a small
    # window from each zarr, applies the mask, computes partial sums,
    # then discards the tile. Peak memory = 1 tile × all vars.
    METRIC_KEYS = [
        "total area", "sbtn_area", "sbtn_loss_area", "jrc_area",
        "jrc_loss_area", "indig_area", "alert_area",
        "sbtn_alert_area", "jrc_alert_area",
    ]
    accum = {k: 0.0 for k in METRIC_KEYS}

    n_tiles_y = (ny + TILE - 1) // TILE
    n_tiles_x = (nx + TILE - 1) // TILE
    n_tiles = n_tiles_y * n_tiles_x
    tiles_done = 0

    t_compute_start = time.perf_counter()

    for iy in range(0, ny, TILE):
        for ix in range(0, nx, TILE):
            yend = min(iy + TILE, ny)
            xend = min(ix + TILE, nx)

            mask_tile = mask_full[iy:yend, ix:xend]
            if not mask_tile.any():
                tiles_done += 1
                continue  # tile fully outside polygon

            sel = {"y": slice(iy, yend), "x": slice(ix, xend)}

            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="invalid value encountered in cast",
                    category=RuntimeWarning,
                )
                # Load tile data from zarr (this is the only I/O)
                tile_sel = loss_raw.isel(**sel)
                pa = tile_sel["pixel_area"].values.astype(np.float32) * mask_tile
                sl = tile_sel["sbtn_loss_area"].values.astype(np.float32) * mask_tile
                jl = tile_sel["jrc_loss_area"].values.astype(np.float32) * mask_tile
                ia = tile_sel["indig_area"].values.astype(np.float32) * mask_tile

                sb = sbtn_raw.isel(**sel)["band_data"].values.astype(np.float32) * mask_tile
                jb = jrc_raw.isel(**sel)["band_data"].values.astype(np.float32) * mask_tile

                intdist_tile = intdist_raw.isel(**sel)
                alert_date = intdist_tile["alert_date"].values
                confidence = intdist_tile["confidence"].values

            m = mask_tile.astype(np.float32)

            # Alert computation
            aa = ((alert_date >= alert_start_days) * (confidence >= 3)).astype(np.float32) * pa
            saa = aa * (sb > 0)
            jaa = aa * (jb > 0)

            accum["total area"] += float(np.nansum(pa))
            accum["sbtn_area"] += float(np.nansum(sb))
            accum["sbtn_loss_area"] += float(np.nansum(sl))
            accum["jrc_area"] += float(np.nansum(jb))
            accum["jrc_loss_area"] += float(np.nansum(jl))
            accum["indig_area"] += float(np.nansum(ia))
            accum["alert_area"] += float(np.nansum(aa))
            accum["sbtn_alert_area"] += float(np.nansum(saa))
            accum["jrc_alert_area"] += float(np.nansum(jaa))

            tiles_done += 1
            if tiles_done % 5 == 0 or tiles_done == n_tiles:
                logger.debug(
                    "Tile progress",
                    aoi=name,
                    tiles=f"{tiles_done}/{n_tiles}",
                )

    t_compute = time.perf_counter() - t_compute_start

    # Convert accumulated sums to hectares and round
    row = {k: round(v / 10000, 4) for k, v in accum.items()}

    t_total = time.perf_counter() - t_start
    logger.info(
        "Analysis complete",
        aoi=name,
        compute_s=round(t_compute, 2),
        total_s=round(t_total, 2),
        results=row,
    )

    results_df = pd.DataFrame([row])
    results_df.insert(
        loc=0, column="name", value=_sanitize_csv_field(name)
    )
    return results_df


def dataframes_to_csv(dfs: list[pd.DataFrame]) -> str:
    """Concatenate DataFrames to CSV string with version header."""
    combined = pd.concat(dfs, ignore_index=True)
    version_lines = [
        f"# {k}: {v}" for k, v in DATA_VERSIONS.items()
    ]
    header = "\n".join(version_lines) + "\n"
    return header + combined.to_csv(index=False)


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

    # 6. Summary message — include actual results so the agent
    #    can present them inline (frontend CSV download not yet built).
    combined_df = pd.concat(dfs, ignore_index=True)
    results_table = combined_df.to_string(index=False)

    parts = [
        f"GFW Pro analysis complete for "
        f"{len(dfs)} AOI(s).",
    ]
    if failed_aois:
        parts.append(
            f"Failed for: {', '.join(failed_aois)}."
        )
    parts.append(
        "Metrics (all values in hectares):\n"
        f"{results_table}"
    )
    parts.append(
        "\nColumn key: total area = jurisdiction area, "
        "sbtn_area = SBTN natural forest, "
        "sbtn_loss_area = SBTN forest loss (2021-2024), "
        "jrc_area = JRC forest cover, "
        "jrc_loss_area = JRC forest loss, "
        "indig_area = indigenous/community lands, "
        "alert_area = integrated disturbance alerts, "
        "sbtn_alert_area = alerts in SBTN forests, "
        "jrc_alert_area = alerts in JRC forests."
    )

    return Command(
        update={
            "gfw_pro_csv": csv_string,
            "messages": [
                ToolMessage(
                    content="\n".join(parts),
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )
