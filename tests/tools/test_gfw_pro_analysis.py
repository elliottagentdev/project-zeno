"""Tests for GFW Pro deforestation analysis tool."""

import sys
import uuid
from typing import Dict
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from src.agent.tools.gfw_pro_analysis import (
    _bbox_slice,
    _build_mask,
    _sanitize_csv_field,
    dataframes_to_csv,
    gfw_pro_analysis,
    get_datasets,
    run_analysis,
)

# Access the actual module (not the StructuredTool that shadows the name)
gfw_mod = sys.modules["src.agent.tools.gfw_pro_analysis"]

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.fixture(scope="session", autouse=True)
def reset_gfw_clients():
    """Reset cached clients at session start to use the correct event loop."""
    yield


# Override DB fixtures (no database needed)
@pytest.fixture(scope="function", autouse=True)
def test_db():
    pass


@pytest.fixture(scope="function", autouse=True)
def test_db_session():
    pass


@pytest.fixture(scope="function", autouse=True)
def test_db_pool():
    pass


# --- Helpers ---

SAMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[100.0, 0.0], [101.0, 0.0], [101.0, 1.0],
         [100.0, 1.0], [100.0, 0.0]]
    ],
}

SAMPLE_GEOMETRY_COLLECTION = {
    "type": "GeometryCollection",
    "geometries": [
        {
            "type": "Polygon",
            "coordinates": [
                [[100.0, 0.0], [100.5, 0.0], [100.5, 0.5],
                 [100.0, 0.5], [100.0, 0.0]]
            ],
        },
        {
            "type": "Polygon",
            "coordinates": [
                [[100.5, 0.5], [101.0, 0.5], [101.0, 1.0],
                 [100.5, 1.0], [100.5, 0.5]]
            ],
        },
    ],
}

EXPECTED_COLUMNS = [
    "name", "total area", "sbtn_area", "sbtn_loss_area",
    "jrc_area", "jrc_loss_area", "indig_area", "alert_area",
    "sbtn_alert_area", "jrc_alert_area",
]


def _make_synthetic_dataset(
    var_names, x_range=(100.0, 101.0), y_range=(0.0, 1.0),
    n=10, fill_value=1.0,
):
    """Create a synthetic xr.Dataset with given variable names and band dim."""
    x = np.linspace(x_range[0], x_range[1], n)
    y = np.linspace(y_range[0], y_range[1], n)
    data_vars = {}
    for vname in var_names:
        data_vars[vname] = (["band", "y", "x"], np.full((1, n, n), fill_value))
    ds = xr.Dataset(
        data_vars,
        coords={"x": x, "y": y, "band": [1]},
    )
    ds = ds.rio.set_spatial_dims(x_dim="x", y_dim="y")
    ds = ds.rio.write_crs("EPSG:4326")
    return ds


def _make_mock_datasets():
    """Create 4 mock datasets matching actual zarr variable names."""
    sbtn_ds = _make_synthetic_dataset(
        ["band_data"],
        fill_value=1.0,
    )
    jrc_ds = _make_synthetic_dataset(["band_data"], fill_value=1.0)
    loss_ds = _make_synthetic_dataset(
        ["pixel_area", "sbtn_loss_area", "jrc_loss_area", "indig_area"],
        fill_value=1.0,
    )
    intdist_ds = _make_synthetic_dataset(
        ["alert_date", "confidence"],
    )
    # Set alert_date to days-since-epoch well above the default start
    intdist_ds["alert_date"] = intdist_ds["alert_date"] * 4000
    # confidence >= 3 triggers alert detection
    intdist_ds["confidence"] = intdist_ds["confidence"] * 3

    return {
        "sbtn": sbtn_ds,
        "jrc": jrc_ds,
        "mergedLoss": loss_ds,
        "intdist": intdist_ds,
    }


# --- Unit Tests ---


def test_get_datasets_caches_results():
    """get_datasets returns cached results on second call."""
    original_cache = gfw_mod._datasets_cache
    try:
        gfw_mod._datasets_cache = None
        with patch.object(
            xr, "open_zarr", return_value=MagicMock()
        ) as mock_open:
            get_datasets()
            get_datasets()  # second call should use cache
        assert mock_open.call_count == 4  # once per dataset
    finally:
        gfw_mod._datasets_cache = original_cache


def test_get_datasets_local_path(monkeypatch):
    """With GFW_PRO_DATA_PATH set, uses local paths."""
    original_cache = gfw_mod._datasets_cache
    try:
        gfw_mod._datasets_cache = None
        monkeypatch.setenv("GFW_PRO_DATA_PATH", "/tmp/test_zarr")
        with patch.object(
            xr, "open_zarr", return_value=MagicMock()
        ) as mock_open:
            get_datasets()
        paths = [
            call.args[0] for call in mock_open.call_args_list
        ]
        assert all(p.startswith("/tmp/test_zarr/") for p in paths)
        # Verify intdist path has correct filename (not empty)
        intdist_paths = [
            p for p in paths if "intdist" in p
        ]
        assert len(intdist_paths) == 1
        assert intdist_paths[0].endswith(
            "intdist_date_conf.zarr"
        )
    finally:
        gfw_mod._datasets_cache = original_cache


def test_get_datasets_s3_fallback(monkeypatch):
    """Without GFW_PRO_DATA_PATH, uses S3 URIs."""
    original_cache = gfw_mod._datasets_cache
    try:
        gfw_mod._datasets_cache = None
        monkeypatch.delenv("GFW_PRO_DATA_PATH", raising=False)
        with patch.object(
            xr, "open_zarr", return_value=MagicMock()
        ) as mock_open:
            get_datasets()
        paths = [
            call.args[0] for call in mock_open.call_args_list
        ]
        assert all(p.startswith("s3://") for p in paths)
    finally:
        gfw_mod._datasets_cache = original_cache


def test_bbox_slice_reduces_extent():
    """Bbox slice reduces dataset to polygon extent."""
    ds = _make_synthetic_dataset(
        ["data"], x_range=(99.0, 102.0), y_range=(-1.0, 2.0),
        n=30, fill_value=42.0,
    )
    sliced = _bbox_slice(ds, SAMPLE_POLYGON)
    assert sliced["data"].size > 0
    assert sliced["data"].size < ds["data"].size


def test_build_mask_geometry_collection():
    """Polygon mask works with GeometryCollection."""
    ds = _make_synthetic_dataset(
        ["data"], x_range=(99.0, 102.0), y_range=(-1.0, 2.0),
        n=30, fill_value=42.0,
    )
    sliced = _bbox_slice(ds, SAMPLE_GEOMETRY_COLLECTION)
    mask = _build_mask(sliced, SAMPLE_GEOMETRY_COLLECTION)
    assert mask.shape == (sliced.sizes["y"], sliced.sizes["x"])
    assert mask.any()  # some pixels inside polygon


def test_run_analysis_returns_correct_columns():
    """run_analysis returns DataFrame with all expected columns."""
    mock_ds = _make_mock_datasets()
    with patch(
        "src.agent.tools.gfw_pro_analysis.get_datasets",
        return_value=mock_ds,
    ):
        df = run_analysis(SAMPLE_POLYGON, "test_aoi")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 1
    assert list(df.columns) == EXPECTED_COLUMNS
    # All numeric values should be rounded to 4 decimal places
    for col in EXPECTED_COLUMNS[1:]:  # skip 'name'
        val = df[col].iloc[0]
        assert val == round(val, 4)



def test_dataframes_to_csv_format():
    """CSV output has version header and correct data rows."""
    df1 = pd.DataFrame([{"name": "A", "total_area": 1.0}])
    df2 = pd.DataFrame([{"name": "B", "total_area": 2.0}])
    csv = dataframes_to_csv([df1, df2])
    lines = csv.strip().split("\n")
    # First lines are comments
    comment_lines = [l for l in lines if l.startswith("#")]
    assert len(comment_lines) == 5  # 5 DATA_VERSIONS entries
    assert "# TCL:" in comment_lines[0]
    # Data rows: header + 2 data
    data_lines = [l for l in lines if not l.startswith("#")]
    assert len(data_lines) == 3  # header + 2 rows


def test_sanitize_csv_field():
    """CSV injection characters are stripped."""
    assert _sanitize_csv_field("=CMD()") == "CMD()"
    assert _sanitize_csv_field("+1234") == "1234"
    assert _sanitize_csv_field("-@hack") == "hack"
    assert _sanitize_csv_field("Normal Name") == "Normal Name"


# --- Tool Integration Tests ---


async def test_tool_no_aoi_selected():
    """Tool returns guidance when no AOI is selected."""
    tool_call_id = str(uuid.uuid4())
    command = await gfw_pro_analysis.ainvoke({
        "type": "tool_call",
        "name": "gfw_pro_analysis",
        "id": tool_call_id,
        "args": {
            "state": {},
            "tool_call_id": tool_call_id,
        },
    })
    msg = command.update["messages"][0]
    assert "No AOI selected" in msg.content


async def test_tool_single_aoi():
    """Tool produces CSV for a single AOI."""
    mock_df = pd.DataFrame([{
        "name": "TestAOI",
        "total_area": 100.0,
        "sbtn_area": 50.0,
        "sbtn_loss_area": 5.0,
        "jrc_area": 60.0,
        "jrc_loss_area": 6.0,
        "indig_area": 10.0,
        "alert_area": 3.0,
        "sbtn_alert_area": 1.0,
        "jrc_alert_area": 2.0,
    }])
    tool_call_id = str(uuid.uuid4())

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_geometry_data",
            new_callable=AsyncMock,
            return_value={"geometry": SAMPLE_POLYGON},
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis.run_analysis",
            return_value=mock_df,
        ),
    ):
        command = await gfw_pro_analysis.ainvoke({
            "type": "tool_call",
            "name": "gfw_pro_analysis",
            "id": tool_call_id,
            "args": {
                "state": {
                    "aoi": {
                        "name": "TestAOI",
                        "source": "gadm",
                        "src_id": "TST",
                    },
                },
                "tool_call_id": tool_call_id,
            },
        })

    assert "gfw_pro_csv" in command.update
    csv = command.update["gfw_pro_csv"]
    assert "TestAOI" in csv
    assert "# TCL:" in csv


async def test_tool_multi_aoi():
    """Tool produces multi-row CSV for multiple AOIs."""
    def mock_run(geojson, name):
        return pd.DataFrame([{
            "name": name,
            "total_area": 100.0,
            "sbtn_area": 50.0,
            "sbtn_loss_area": 5.0,
            "jrc_area": 60.0,
            "jrc_loss_area": 6.0,
            "indig_area": 10.0,
            "alert_area": 3.0,
            "sbtn_alert_area": 1.0,
            "jrc_alert_area": 2.0,
        }])

    tool_call_id = str(uuid.uuid4())

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_geometry_data",
            new_callable=AsyncMock,
            return_value={"geometry": SAMPLE_POLYGON},
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis.run_analysis",
            side_effect=mock_run,
        ),
    ):
        command = await gfw_pro_analysis.ainvoke({
            "type": "tool_call",
            "name": "gfw_pro_analysis",
            "id": tool_call_id,
            "args": {
                "state": {
                    "aoi_selection": {
                        "name": "Test",
                        "aois": [
                            {"name": "AOI_A", "source": "gadm", "src_id": "A"},
                            {"name": "AOI_B", "source": "gadm", "src_id": "B"},
                        ],
                    },
                },
                "tool_call_id": tool_call_id,
            },
        })

    csv = command.update["gfw_pro_csv"]
    assert "AOI_A" in csv
    assert "AOI_B" in csv
    msg = command.update["messages"][0].content
    assert "2 AOI(s)" in msg


async def test_tool_partial_geometry_failure():
    """Tool succeeds when some geometry fetches return None."""
    mock_df = pd.DataFrame([{
        "name": "GoodAOI", "total_area": 100.0,
        "sbtn_area": 50.0, "sbtn_loss_area": 5.0,
        "jrc_area": 60.0, "jrc_loss_area": 6.0,
        "indig_area": 10.0, "alert_area": 3.0,
        "sbtn_alert_area": 1.0, "jrc_alert_area": 2.0,
    }])
    tool_call_id = str(uuid.uuid4())

    async def mock_geo(source, src_id):
        if src_id == "BAD":
            return None
        return {"geometry": SAMPLE_POLYGON}

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_geometry_data",
            new_callable=AsyncMock,
            side_effect=mock_geo,
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis.run_analysis",
            return_value=mock_df,
        ),
    ):
        command = await gfw_pro_analysis.ainvoke({
            "type": "tool_call",
            "name": "gfw_pro_analysis",
            "id": tool_call_id,
            "args": {
                "state": {
                    "aoi_selection": {
                        "name": "Test",
                        "aois": [
                            {"name": "BadAOI", "source": "gadm", "src_id": "BAD"},
                            {"name": "GoodAOI", "source": "gadm", "src_id": "GOOD"},
                        ],
                    },
                },
                "tool_call_id": tool_call_id,
            },
        })

    assert "gfw_pro_csv" in command.update
    csv = command.update["gfw_pro_csv"]
    assert "GoodAOI" in csv


async def test_tool_runs_in_thread():
    """Analysis runs via asyncio.to_thread."""
    mock_df = pd.DataFrame([{
        "name": "T", "total_area": 1.0,
        "sbtn_area": 0, "sbtn_loss_area": 0,
        "jrc_area": 0, "jrc_loss_area": 0,
        "indig_area": 0, "alert_area": 0,
        "sbtn_alert_area": 0, "jrc_alert_area": 0,
    }])
    tool_call_id = str(uuid.uuid4())

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_geometry_data",
            new_callable=AsyncMock,
            return_value={"geometry": SAMPLE_POLYGON},
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis.asyncio.to_thread",
            new_callable=AsyncMock,
            return_value=mock_df,
        ) as mock_to_thread,
    ):
        command = await gfw_pro_analysis.ainvoke({
            "type": "tool_call",
            "name": "gfw_pro_analysis",
            "id": tool_call_id,
            "args": {
                "state": {
                    "aoi": {
                        "name": "T",
                        "source": "gadm",
                        "src_id": "T",
                    },
                },
                "tool_call_id": tool_call_id,
            },
        })

    mock_to_thread.assert_called_once()


async def test_tool_analysis_failure_per_aoi():
    """Tool continues when analysis fails for one AOI."""
    call_count = 0

    def mock_run(geojson, name):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("Data corrupted")
        return pd.DataFrame([{
            "name": name, "total_area": 1.0,
            "sbtn_area": 0, "sbtn_loss_area": 0,
            "jrc_area": 0, "jrc_loss_area": 0,
            "indig_area": 0, "alert_area": 0,
            "sbtn_alert_area": 0, "jrc_alert_area": 0,
        }])

    tool_call_id = str(uuid.uuid4())

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_geometry_data",
            new_callable=AsyncMock,
            return_value={"geometry": SAMPLE_POLYGON},
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis.run_analysis",
            side_effect=mock_run,
        ),
    ):
        command = await gfw_pro_analysis.ainvoke({
            "type": "tool_call",
            "name": "gfw_pro_analysis",
            "id": tool_call_id,
            "args": {
                "state": {
                    "aoi_selection": {
                        "name": "Test",
                        "aois": [
                            {"name": "FailAOI", "source": "gadm", "src_id": "F"},
                            {"name": "OkAOI", "source": "gadm", "src_id": "O"},
                        ],
                    },
                },
                "tool_call_id": tool_call_id,
            },
        })

    assert "gfw_pro_csv" in command.update
    msg = command.update["messages"][0].content
    assert "FailAOI" in msg
    assert "1 AOI(s)" in msg


def test_run_analysis_raises_on_large_aoi():
    """run_analysis raises ValueError when bbox exceeds MAX_PIXELS."""
    large_loss = _make_synthetic_dataset(
        ["pixel_area", "sbtn_loss_area", "jrc_loss_area", "indig_area"],
        fill_value=1.0,
    )
    # Patch sizes to simulate a Bolivia-scale AOI (nx * ny > 5B)
    large_loss = MagicMock()
    large_loss.sizes = {"y": 100_000, "x": 60_000}  # 6B pixels

    mock_ds = _make_mock_datasets()
    mock_ds["mergedLoss"] = large_loss

    with (
        patch(
            "src.agent.tools.gfw_pro_analysis.get_datasets",
            return_value=mock_ds,
        ),
        patch(
            "src.agent.tools.gfw_pro_analysis._bbox_slice",
            return_value=large_loss,
        ),
    ):
        with pytest.raises(ValueError, match="MAX_PIXELS"):
            run_analysis(SAMPLE_POLYGON, "large_aoi")
