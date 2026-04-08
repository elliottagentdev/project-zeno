"""GFW Pro deforestation and disturbance alert analysis tool."""

import asyncio
import os
import re
import threading
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

    Follows the reference query3.py approach: clip zarr datasets,
    compute via dask lazy evaluation, sum and return as DataFrame.

    Returns single-row DataFrame with columns:
    name, total area, sbtn_area, sbtn_loss_area, jrc_area,
    jrc_loss_area, indig_area, alert_area, sbtn_alert_area,
    jrc_alert_area (all areas in hectares).
    """
    datasets = get_datasets()

    # Convert alert start date to days since 2014-12-31
    alert_start_str = os.environ.get(
        "GFW_PRO_ALERT_START_DATE", DEFAULT_ALERT_START_DATE
    )
    alert_start_days = (
        datetime.strptime(alert_start_str, "%Y-%m-%d") - ALERT_EPOCH
    ).days

    # Clip all datasets to AOI bounding box + polygon mask
    # squeeze("band") removes the single band dimension, matching
    # the reference query3.py clip_ds_to_geojson behaviour.
    loss = clip_ds_to_geojson(
        datasets["mergedLoss"], geojson_geometry
    ).squeeze("band").astype(np.float64)
    sbtn_area = clip_ds_to_geojson(
        datasets["sbtn"], geojson_geometry
    ).squeeze("band").astype(np.float64)
    jrc_area = clip_ds_to_geojson(
        datasets["jrc"], geojson_geometry
    ).squeeze("band").astype(np.float64)
    intdist = clip_ds_to_geojson(
        datasets["intdist"], geojson_geometry
    ).squeeze("band")

    # Extract pre-computed area variables from mergedLoss zarr
    pixel_area = loss["pixel_area"]
    sbtn_loss_area = loss["sbtn_loss_area"]
    jrc_loss_area = loss["jrc_loss_area"]
    indig_area = loss["indig_area"]

    # Disturbance alerts: high (conf>=3) or highest (conf>=4)
    # since alert_start_date.
    # confidence encoding: 2=nominal, 3=high, 4=highest
    alert_area = (
        (intdist["alert_date"] >= alert_start_days)
        * (intdist["confidence"] >= 3)
        * pixel_area
    )

    # Alert area intersected with SBTN / JRC forests.
    # Use > 0 (not != 0) so that NaN pixels evaluate as False.
    sbtn_alert_area = alert_area * (sbtn_area["band_data"] > 0)
    jrc_alert_area = alert_area * (jrc_area["band_data"] > 0)

    combined = xr.Dataset({
        "total area": pixel_area,
        "sbtn_area": sbtn_area["band_data"],
        "sbtn_loss_area": sbtn_loss_area,
        "jrc_area": jrc_area["band_data"],
        "jrc_loss_area": jrc_loss_area,
        "indig_area": indig_area,
        "alert_area": alert_area,
        "sbtn_alert_area": sbtn_alert_area,
        "jrc_alert_area": jrc_alert_area,
    })

    summed = combined.sum(dim=("x", "y"))
    summed_df = summed.to_dask_dataframe()
    drop_cols = [
        c for c in ["spatial_ref", "band"]
        if c in summed_df.columns
    ]
    results_dask = summed_df.drop(columns=drop_cols)

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="invalid value encountered in cast",
            category=RuntimeWarning,
        )
        results_df: pd.DataFrame = (
            results_dask.compute() / 10000
        ).round(4)

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
