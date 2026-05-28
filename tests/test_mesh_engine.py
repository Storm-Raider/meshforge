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

    def test_mesh_with_surface_refinement_zone(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams, RefinementZone
        zone = RefinementZone(
            entity_type="surface",
            entity_index=1,
            size_factor=0.5,
            influence_radius=bracket_geo.bounding_box_diagonal * 0.1,
        )
        params = MeshParams(size_factor=2.0, refinement_zones=[zone])
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.element_count > 0
        assert result.connectivity.shape[1] == 10

    def test_mesh_with_stale_zone_skipped(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams, RefinementZone
        stale_zone = RefinementZone(
            entity_type="surface",
            entity_index=9999,
            size_factor=0.1,
            influence_radius=1.0,
        )
        params = MeshParams(size_factor=2.0, refinement_zones=[stale_zone])
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.element_count > 0

    def test_hex_mesh_returns_mesh_data(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        from meshforge.models.mesh_data import MeshData
        from meshforge.core.mesh_engine import VTK_LINEAR_HEX
        params = MeshParams(size_factor=2.0, mesh_type="hex")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert isinstance(result, MeshData)
        assert result.element_count > 0
        assert result.node_count > 0

    def test_hex_mesh_connectivity_width(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0, mesh_type="hex")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.connectivity.shape[1] == 8

    def test_hex_mesh_element_types_all_c3d8(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        from meshforge.core.mesh_engine import VTK_LINEAR_HEX
        params = MeshParams(size_factor=2.0, mesh_type="hex")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert np.all(result.element_types == VTK_LINEAR_HEX)

    def test_hex_mesh_node_indices_valid(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0, mesh_type="hex")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.connectivity.min() >= 0
        assert result.connectivity.max() < result.node_count

    def test_tet_smoothing_produces_valid_mesh(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        from meshforge.core.mesh_engine import VTK_QUADRATIC_TETRA
        params = MeshParams(size_factor=2.0, smooth_iter=3)
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.element_count > 0
        assert np.all(result.element_types == VTK_QUADRATIC_TETRA)
        assert result.connectivity.min() >= 0

    def test_smoothing_zero_is_noop(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params_base = MeshParams(size_factor=2.0, smooth_iter=0)
        params_smooth = MeshParams(size_factor=2.0, smooth_iter=3)
        r1 = MeshEngine(params=params_base).mesh(bracket_geo)
        r2 = MeshEngine(params=params_smooth).mesh(bracket_geo)
        # Smoothing repositions nodes but must not add or remove elements
        assert r1.element_count == r2.element_count

    def test_lintet_mesh_returns_c3d4(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        from meshforge.core.mesh_engine import VTK_QUADRATIC_TETRA
        params = MeshParams(size_factor=2.0, mesh_type="lintet")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.element_count > 0
        # Linear tet mesh: VTK 10 (C3D4), no quadratic tet
        assert np.all(result.element_types == 10)
        assert VTK_QUADRATIC_TETRA not in result.element_types

    def test_lintet_connectivity_width(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0, mesh_type="lintet")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.connectivity.shape[1] == 4

    def test_lintet_node_indices_valid(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0, mesh_type="lintet")
        result = MeshEngine(params=params).mesh(bracket_geo)
        assert result.connectivity.min() >= 0
        assert result.connectivity.max() < result.node_count

    def test_surface_mesh_returns_triangles(self, bracket_geo):
        from meshforge.models.mesh_data import MeshData
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0)
        result = MeshEngine(params=params).surface_mesh(bracket_geo)
        assert isinstance(result, MeshData)
        assert result.element_count > 0
        # Surface mesh contains triangles (VTK 5) and/or quads (VTK 9) only
        assert set(result.element_types.tolist()).issubset({5, 9})

    def test_surface_mesh_node_indices_valid(self, bracket_geo):
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=2.0)
        result = MeshEngine(params=params).surface_mesh(bracket_geo)
        assert result.connectivity.min() >= 0
        assert result.connectivity.max() < result.node_count

    def test_surface_mesh_faster_than_volume(self, bracket_geo):
        import time
        from meshforge.models.mesh_params import MeshParams
        params = MeshParams(size_factor=1.0)
        t0 = time.monotonic()
        MeshEngine(params=params).surface_mesh(bracket_geo)
        surf_time = time.monotonic() - t0
        t0 = time.monotonic()
        MeshEngine(params=params).mesh(bracket_geo)
        vol_time = time.monotonic() - t0
        assert surf_time < vol_time
