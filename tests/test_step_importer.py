"""Tests for StepImporter. Requires OCC (pythonocc-core)."""
import pytest
from pathlib import Path

from meshforge.core.step_importer import StepImporter

_FIXTURES = Path(__file__).parent / "fixtures"
_BRACKET = _FIXTURES / "bracket_clean.step"


def test_wrong_extension_raises():
    imp = StepImporter()
    with pytest.raises(ValueError, match="Unsupported format"):
        imp.import_file("/some/file.stl")


def test_wrong_extension_message_includes_extension():
    imp = StepImporter()
    with pytest.raises(ValueError, match=r"\.stl"):
        imp.import_file("/some/file.stl")


@pytest.mark.skipif(not _BRACKET.exists(), reason="bracket_clean.step fixture not present")
class TestWithFixture:
    def test_import_returns_geometry_data(self):
        from meshforge.models.geometry_data import GeometryData
        result = StepImporter().import_file(_BRACKET)
        assert isinstance(result, GeometryData)

    def test_import_surface_count_positive(self):
        result = StepImporter().import_file(_BRACKET)
        assert result.surface_count > 0

    def test_import_bbox_diagonal_positive(self):
        result = StepImporter().import_file(_BRACKET)
        assert result.bounding_box_diagonal > 0

    def test_import_min_edge_positive(self):
        result = StepImporter().import_file(_BRACKET)
        assert result.min_edge_length > 0

    def test_import_healing_status_ok(self):
        result = StepImporter().import_file(_BRACKET)
        # bracket_clean.step should heal without failures
        assert result.healing_status.startswith("ok")

    def test_import_occ_shape_not_none(self):
        result = StepImporter().import_file(_BRACKET)
        assert result.occ_shape is not None
