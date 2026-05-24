"""Tests for GeometryData dataclass."""
import pytest
from unittest.mock import MagicMock
from meshforge.models.geometry_data import GeometryData


def _make_geo(healing_status="ok"):
    return GeometryData(
        surface_count=10,
        bounding_box_diagonal=100.0,
        min_edge_length=2.0,
        healing_status=healing_status,
        occ_shape=MagicMock(),
    )


def test_is_valid_ok():
    assert _make_geo("ok").is_valid() is True


def test_is_valid_warn():
    assert _make_geo("warn:minor gap").is_valid() is True


def test_is_valid_failed():
    assert _make_geo("failed:3 defects").is_valid() is False


def test_default_element_size_uses_bbox():
    geo = _make_geo()
    # min(3% * 100, 0.5 * 2.0) = min(3.0, 1.0) = 1.0
    assert geo.default_element_size() == pytest.approx(1.0)


def test_default_element_size_clamps_to_edge():
    geo = GeometryData(
        surface_count=5,
        bounding_box_diagonal=10.0,
        min_edge_length=0.1,
        healing_status="ok",
        occ_shape=MagicMock(),
    )
    # min(3% * 10, 0.5 * 0.1) = min(0.3, 0.05) = 0.05
    assert geo.default_element_size() == pytest.approx(0.05)
