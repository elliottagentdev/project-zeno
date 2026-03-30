"""Tests for render_dataset_map geometry resolution and session state."""

import json
from unittest.mock import MagicMock, patch


SAMPLE_POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[-50, -10], [-50, 5], [-35, 5], [-35, -10], [-50, -10]]
    ],
}

SAMPLE_TILE_URL = "https://example.com/{z}/{x}/{y}.png"


def test_fetches_geometry_from_src_id(
    mock_streamlit, mock_folium_static
):
    """When aoi_data has src_id and source but no geometry,
    render_dataset_map calls fetch_geometry."""
    mock_client = MagicMock()
    mock_client.fetch_geometry.return_value = {
        "geometry": SAMPLE_POLYGON,
    }
    mock_streamlit["token"] = "test-token"

    with patch("utils.ZenoClient", return_value=mock_client):
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": SAMPLE_TILE_URL,
                "dataset_name": "Test Dataset",
            },
            aoi_data={
                "src_id": "BRA",
                "source": "gadm",
                "name": "Brazil",
            },
        )

    mock_client.fetch_geometry.assert_called_once_with(
        source="gadm", src_id="BRA"
    )


def test_uses_provided_geometry(
    mock_streamlit, mock_folium_static
):
    """When aoi_data already contains geometry,
    no fetch_geometry call is made."""
    with patch("utils.ZenoClient") as mock_cls:
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={
                "tile_url": SAMPLE_TILE_URL,
                "dataset_name": "Test",
            },
            aoi_data={"geometry": SAMPLE_POLYGON},
        )

    mock_cls.assert_not_called()


def test_fallback_on_geometry_fetch_failure(
    mock_streamlit, mock_folium_static
):
    """When fetch_geometry raises, map renders without error."""
    mock_client = MagicMock()
    mock_client.fetch_geometry.side_effect = Exception("API down")
    mock_streamlit["token"] = "test-token"

    with patch("utils.ZenoClient", return_value=mock_client):
        from utils import render_dataset_map

        # Should not raise
        render_dataset_map(
            dataset_data={"tile_url": SAMPLE_TILE_URL},
            aoi_data={"src_id": "BRA", "source": "gadm"},
        )

    # Verify folium_static was still called (map rendered)
    mock_folium_static.assert_called_once()


def test_handles_no_aoi(mock_streamlit, mock_folium_static):
    """When aoi_data is None, map renders at global view."""
    from utils import render_dataset_map

    render_dataset_map(
        dataset_data={"tile_url": SAMPLE_TILE_URL},
        aoi_data=None,
    )

    mock_folium_static.assert_called_once()


def test_uses_dataset_name_key(
    mock_streamlit, mock_folium_static
):
    """Dataset name comes from dataset_name key, not data_layer."""
    from utils import render_dataset_map

    with patch("utils.folium.raster_layers.TileLayer") as mock_tl:
        mock_tl.return_value = MagicMock()
        render_dataset_map(
            dataset_data={
                "tile_url": SAMPLE_TILE_URL,
                "dataset_name": "Tree cover loss",
            },
            aoi_data=None,
        )

    call_kwargs = mock_tl.call_args[1]
    assert call_kwargs["name"] == "Tree cover loss"


def test_cached_geometry_reused(
    mock_streamlit, mock_folium_static
):
    """When geometry is cached in session state for same src_id,
    fetch_geometry is not called."""
    mock_streamlit["token"] = "test-token"
    mock_streamlit["last_aoi_geometry"] = SAMPLE_POLYGON
    mock_streamlit["last_aoi_geometry_src_id"] = "BRA"

    with patch("utils.ZenoClient") as mock_cls:
        from utils import render_dataset_map

        render_dataset_map(
            dataset_data={"tile_url": SAMPLE_TILE_URL},
            aoi_data={"src_id": "BRA", "source": "gadm"},
        )

    mock_cls.assert_not_called()


def test_render_stream_persists_aoi_in_session_state(
    mock_streamlit,
):
    """render_stream stores aoi_data in session state so
    subsequent dataset updates can access it."""
    aoi_payload = {
        "src_id": "BRA",
        "source": "gadm",
        "name": "Brazil",
    }
    # messages must have the structure render_stream expects
    aoi_update = json.dumps({
        "messages": [
            {"kwargs": {"type": "ai", "content": "Found AOI"}}
        ],
        "aoi": aoi_payload,
    })

    with (
        patch("utils.render_aoi_map"),
        patch("utils.render_dataset_map"),
    ):
        from utils import render_stream

        render_stream({"update": aoi_update})

    assert mock_streamlit.get("last_aoi_data") == aoi_payload


def test_render_stream_dataset_uses_cached_aoi(
    mock_streamlit,
):
    """When dataset update arrives without aoi, render_dataset_map
    receives cached aoi_data from session state."""
    cached_aoi = {
        "src_id": "BRA",
        "source": "gadm",
        "name": "Brazil",
    }
    mock_streamlit["last_aoi_data"] = cached_aoi

    dataset_update = json.dumps({
        "messages": [
            {"kwargs": {"type": "ai", "content": "Found dataset"}}
        ],
        "dataset": {
            "tile_url": SAMPLE_TILE_URL,
            "dataset_name": "Tree cover loss",
        },
    })

    with (
        patch("utils.render_aoi_map"),
        patch("utils.render_dataset_map") as mock_rdm,
    ):
        from utils import render_stream

        render_stream({"update": dataset_update})

    # render_dataset_map should have been called with the cached aoi
    mock_rdm.assert_called_once()
    call_args = mock_rdm.call_args
    assert call_args[0][1] == cached_aoi
