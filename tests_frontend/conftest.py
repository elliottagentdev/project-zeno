import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Add frontend/ to sys.path so tests can import bare module names
sys.path.insert(
    0, str(Path(__file__).resolve().parent.parent / "frontend")
)


class _SessionState(dict):
    """Dict subclass that supports attribute access like Streamlit's session_state."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)


@pytest.fixture(autouse=True)
def mock_streamlit():
    """Mock streamlit session_state as a dict for all frontend tests."""
    mock_state = _SessionState()
    with patch("streamlit.session_state", mock_state):
        yield mock_state


@pytest.fixture
def mock_folium_static():
    """Mock folium_static to avoid rendering."""
    with patch("utils.folium_static") as mock:
        yield mock
