"""Tests for basemap configuration and map factory."""

import folium

from utils import BASEMAP_CONFIGS, _create_base_map


def test_basemap_configs_non_empty():
    """At least one basemap must be configured."""
    assert len(BASEMAP_CONFIGS) > 0


def test_basemap_configs_have_required_keys():
    """Each basemap config has tiles, attr, and name."""
    required_keys = {"tiles", "attr", "name"}
    for config in BASEMAP_CONFIGS:
        assert required_keys.issubset(config.keys()), (
            f"Missing keys in {config.get('name', 'unknown')}"
        )


def test_create_base_map_returns_folium_map():
    """_create_base_map returns a folium.Map instance."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    assert isinstance(m, folium.Map)


def test_create_base_map_has_correct_tile_count():
    """Map has one TileLayer per BASEMAP_CONFIGS entry."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.raster_layers.TileLayer)
    ]
    assert len(tile_layers) == len(BASEMAP_CONFIGS)


def test_exactly_one_default_basemap():
    """Only the first basemap should be shown by default."""
    m = _create_base_map(center=[0, 0], zoom_start=2)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.raster_layers.TileLayer)
    ]
    shown = [tl for tl in tile_layers if tl.show]
    assert len(shown) == 1
    assert shown[0].tile_name == BASEMAP_CONFIGS[0]["name"]


def test_create_base_map_has_no_default_osm_tiles():
    """Map should not contain default OpenStreetMap tiles."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "tile.openstreetmap.org" not in html


def test_create_base_map_has_expected_providers():
    """Map contains CartoDB and ESRI tile URLs."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    html = m._repr_html_()
    assert "basemaps.cartocdn.com/light_all" in html
    assert "basemaps.cartocdn.com/dark_all" in html
    assert "arcgisonline.com" in html


def test_basemap_layers_are_base_not_overlay():
    """All basemaps must be base layers (overlay=False)."""
    m = _create_base_map(center=[0, 0], zoom_start=5)
    tile_layers = [
        child
        for child in m._children.values()
        if isinstance(child, folium.raster_layers.TileLayer)
    ]
    for tl in tile_layers:
        assert tl.overlay is False, (
            f"{tl.tile_name} should be a base layer"
        )
