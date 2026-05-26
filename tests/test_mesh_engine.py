"""Tests for MeshEngine. Requires gmsh + OCC fixture file."""
import pytest
from pathlib import Path
import numpy as np

from meshforge.core.mesh_engine import MeshEngine

_FIXTURES = Path(__file__).parent / "fixtures"
_BRACKET = _FIXTURES / "bracket_clean.step"

try:
    import gmsh as _gmsh
    _HAS_GMSH = True
except ImportError:
    _HAS_GMSH = False


@pytest.fixture
def bracket_geo():
    from meshforge.core.step_importer import StepImporter
    return StepImporter().import_file(_BRACKET)


class TestMeshEngineClassifyError:
    def test_self_intersection_classified(self):
        msg = MeshEngine.classify_error(["Error: self-intersecting surface 3"])
        assert "self-intersecting" in msg
        assert "surface 3" in msg

    def test_edge_recovery_classified(self):
        msg = MeshEngine.classify_error(["Warning: edge recovery failed on surface 12"])
        assert "conforming mesh" in msg or "edge recovery" in msg.lower()

    def test_unknown_error_fallback(self):
        msg = MeshEngine.classify_error(["something unexpected"])
        assert "log panel" in msg.lower()

    def test_empty_log_fallback(self):
        msg = MeshEngine.classify_error([])
        assert "log panel" in msg.lower()


@pytest.mark.skipif(not _BRACKET.exists(), reason="bracket_clean.step fixture not present")
@pytest.mark.skipif(not _HAS_GMSH, reason="gmsh Python bindings not available")
class TestMeshEngineWithFixture:
    def test_mesh_returns_mesh_data(self, bracket_geo):
        from meshforge.models.mesh_data import MeshData
        result = MeshEngine().mesh(bracket_geo)
        assert isinstance(result, MeshData)

    def test_mesh_has_elements(self, bracket_geo):
        result = MeshEngine().mesh(bracket_geo)
        assert result.element_count > 0

    def test_mesh_has_nodes(self, bracket_geo):
        result = MeshEngine().mesh(bracket_geo)
        assert result.node_count > 0

    def test_connectivity_shape(self, bracket_geo):
        result = MeshEngine().mesh(bracket_geo)
        assert result.connectivity.shape[1] == 10  # C3D10: 10 nodes per element

    def test_node_indices_valid(self, bracket_geo):
        result = MeshEngine().mesh(bracket_geo)
        assert result.connectivity.min() >= 0
        assert result.connectivity.max() < result.node_count

    def test_element_types_all_c3d10(self, bracket_geo):
        from meshforge.core.mesh_engine import VTK_QUADRATIC_TETRA
        result = MeshEngine().mesh(bracket_geo)
        assert np.all(result.element_types == VTK_QUADRATIC_TETRA)
