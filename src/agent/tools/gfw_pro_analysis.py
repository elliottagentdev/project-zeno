"""GFW Pro deforestation and disturbance alert analysis tool."""

import asyncio
import os
import re
import threading
from datetime import datetime
from typing import Annotated, Dict, Optional

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

# Max pixels after clip before refusing (memory guard)
MAX_PIXELS = 100_000_000

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
        datasets = {}

        for key, s3_uri in S3_ZARR_PATHS.items():
            if base_path:
                # Extract filename, strip trailing slashes
                zarr_name = s3_uri.rstrip("/").rsplit("/", 1)[-1]
                path = os.path.join(base_path, zarr_name)
            else:
                path = s3_uri

            logger.info(
                "Opening zarr dataset",
                key=key,
                path=path,
            )
            datasets[key] = xr.open_zarr(path, chunks="auto")

        _datasets_cache = datasets
        return _datasets_cache


def clip_ds_to_geojson(
    ds: xr.Dataset, geojson_geom: dict
) -> xr.Dataset:
    """Clip dataset to GeoJSON geometry via bbox + rioxarray."""
    geom = shape(geojson_geom)
    minx, miny, maxx, maxy = geom.bounds

    # Determine spatial dimension names
    if "lon" in ds.dims:
        x_dim, y_dim = "lon", "lat"
    else:
        x_dim, y_dim = "x", "y"

    # Detect y-axis direction (ascending vs descending)
    y_vals = ds[y_dim].values
    if y_vals[0] < y_vals[-1]:
        # Ascending y
        y_slice = slice(miny, maxy)
    else:
        # Descending y
        y_slice = slice(maxy, miny)

    # Bbox slice (fast, reduces data volume)
    ds_bbox = ds.sel(
        {x_dim: slice(minx, maxx), y_dim: y_slice}
    )

    # Set spatial dims for rioxarray
    ds_bbox = ds_bbox.rio.set_spatial_dims(
        x_dim=x_dim, y_dim=y_dim
    )

    # Set CRS if not already set
    if not ds_bbox.rio.crs:
        ds_bbox = ds_bbox.rio.write_crs("EPSG:4326")

    # Decompose GeometryCollection into individual geometries
    if geojson_geom.get("type") == "GeometryCollection":
        clip_geoms = [
            mapping(g) for g in geom.geoms
        ]
    else:
        clip_geoms = [geojson_geom]

    clipped = ds_bbox.rio.clip(
        clip_geoms, crs="EPSG:4326", drop=True
    )
    return clipped


def _sanitize_csv_field(value: str) -> str:
    """Strip leading characters that could trigger CSV injection."""
    return re.sub(r'^[=+\-@]+', '', value)


def run_analysis(
    geojson_geometry: dict, name: str
) -> pd.DataFrame:
    """Compute deforestation metrics for a single AOI.

    Returns single-row DataFrame with columns:
    name, total_area, sbtn_area, sbtn_loss_area, jrc_area,
    jrc_loss_area, indig_area, alert_area, sbtn_alert_area,
    jrc_alert_area
    """
    datasets = get_datasets()
    alert_start = os.environ.get(
        "GFW_PRO_ALERT_START_DATE", DEFAULT_ALERT_START_DATE
    )
    alert_start_int = int(
        datetime.strptime(alert_start, "%Y-%m-%d")
        .strftime("%Y%m%d")
    )

    # Clip all datasets to AOI
    sbtn = clip_ds_to_geojson(datasets["sbtn"], geojson_geometry)
    jrc = clip_ds_to_geojson(datasets["jrc"], geojson_geometry)
    loss = clip_ds_to_geojson(
        datasets["mergedLoss"], geojson_geometry
    )
    intdist = clip_ds_to_geojson(
        datasets["intdist"], geojson_geometry
    )

    # Memory guard: check clipped size
    total_size = sum(
        np.prod(v.shape) for v in sbtn.data_vars.values()
    )
    if total_size > MAX_PIXELS:
        raise ValueError(
            f"AOI '{name}' is too large ({total_size:,} pixels "
            f"after clipping). Maximum is {MAX_PIXELS:,}. "
            "Please select a smaller area."
        )

    # Pixel area in hectares (from sbtn.area.zarr)
    # NOTE: Variable name "area" must be verified against
    # actual zarr contents. Inspect with ds.data_vars.
    pixel_area = sbtn["area"].values

    # Total area
    total_area = float(np.nansum(pixel_area))

    # SBTN natural forest mask
    # NOTE: Variable name "sbtn" must be verified.
    sbtn_mask = sbtn["sbtn"].values > 0
    sbtn_area_val = float(np.nansum(pixel_area[sbtn_mask]))

    # JRC forest mask
    # NOTE: Variable name "jrc" must be verified.
    jrc_mask = jrc["jrc"].values > 0
    jrc_area_val = float(np.nansum(pixel_area[jrc_mask]))

    # Tree cover loss 2021-2024
    # NOTE: Variable name "mergedLoss" must be verified.
    loss_vals = loss["mergedLoss"].values
    tcl_mask = (loss_vals >= 2021) & (loss_vals <= 2024)

    sbtn_loss_area = float(
        np.nansum(pixel_area[sbtn_mask & tcl_mask])
    )
    jrc_loss_area = float(
        np.nansum(pixel_area[jrc_mask & tcl_mask])
    )

    # Indigenous/community lands
    # NOTE: Variable name "indig" must be verified.
    indig_mask = sbtn["indig"].values > 0
    indig_area_val = float(np.nansum(pixel_area[indig_mask]))

    # Disturbance alerts since alert_start_date
    # NOTE: Variable names "date" and "conf" must be verified.
    # Assumed: date is YYYYMMDD integer, conf >= 2 = high/highest
    alert_dates = intdist["date"].values
    alert_conf = intdist["conf"].values
    alert_mask = (alert_conf >= 2) & (
        alert_dates >= alert_start_int
    )
    alert_area_val = float(np.nansum(pixel_area[alert_mask]))

    sbtn_alert_area = float(
        np.nansum(pixel_area[alert_mask & sbtn_mask])
    )
    jrc_alert_area = float(
        np.nansum(pixel_area[alert_mask & jrc_mask])
    )

    return pd.DataFrame([{
        "name": _sanitize_csv_field(name),
        "total_area": round(total_area, 4),
        "sbtn_area": round(sbtn_area_val, 4),
        "sbtn_loss_area": round(sbtn_loss_area, 4),
        "jrc_area": round(jrc_area_val, 4),
        "jrc_loss_area": round(jrc_loss_area, 4),
        "indig_area": round(indig_area_val, 4),
        "alert_area": round(alert_area_val, 4),
        "sbtn_alert_area": round(sbtn_alert_area, 4),
        "jrc_alert_area": round(jrc_alert_area, 4),
    }])


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

    # 6. Summary message
    parts = [
        f"GFW Pro analysis complete for "
        f"{len(dfs)} AOI(s).",
    ]
    if failed_aois:
        parts.append(
            f"Failed for: {', '.join(failed_aois)}."
        )
    parts.append(
        "Metrics: total area, SBTN forest, SBTN loss, "
        "JRC forest, JRC loss, indigenous lands, "
        "alert area, SBTN alerts, JRC alerts."
    )
    parts.append("Results available as downloadable CSV.")

    return Command(
        update={
            "gfw_pro_csv": csv_string,
            "messages": [
                ToolMessage(
                    content=" ".join(parts),
                    tool_call_id=tool_call_id,
                )
            ],
        },
    )
