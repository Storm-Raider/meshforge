"""Tests for QualityEngine — the critical path computation."""
import numpy as np
import pytest
from unittest.mock import MagicMock

from meshforge.models.mesh_data import MeshData
from meshforge.core.quality_engine import QualityEngine, PASS_THRESHOLD, WARN_THRESHOLD


def _equilateral_tet():
    """Return nodes + connectivity for a single perfect equilateral tet."""
    # Vertices of a regular tetrahedron with edge length 1
    nodes = np.array([
        [0.0,          0.0,          0.0],
        [1.0,          0.0,          0.0],
        [0.5, np.sqrt(3)/2,          0.0],
        [0.5, np.sqrt(3)/6, np.sqrt(6)/3],
    ], dtype=np.float64)

    # C3D10: 10 nodes — first 4 are corners, last 6 are midpoints (duplicated here for simplicity)
    conn = np.array([[0, 1, 2, 3, 0, 1, 2, 3, 0, 1]], dtype=np.int64)
    types = np.array([24], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=conn, element_types=types)


def _degenerate_tet():
    """Tet with all nodes at the same point (Jacobian ≈ 0)."""
    nodes = np.zeros((4, 3), dtype=np.float64)
    conn = np.array([[0, 1, 2, 3, 0, 1, 2, 3, 0, 1]], dtype=np.int64)
    types = np.array([24], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=conn, element_types=types)


class TestQualityEngineCompute:
    def test_equilateral_tet_near_zero_point_seven(self):
        mesh = _equilateral_tet()
        scalars = QualityEngine().compute(mesh)
        assert len(scalars) == 1
        # Perfect equilateral tet ≈ 0.707 with product-of-column-norms formula
        assert scalars[0] == pytest.approx(0.707, abs=0.01)

    def test_equilateral_tet_passes_threshold(self):
        mesh = _equilateral_tet()
        scalars = QualityEngine().compute(mesh)
        assert scalars[0] > PASS_THRESHOLD

    def test_degenerate_tet_near_zero(self):
        mesh = _degenerate_tet()
        scalars = QualityEngine().compute(mesh)
        assert abs(scalars[0]) < 1e-6

    def test_returns_float32(self):
        mesh = _equilateral_tet()
        scalars = QualityEngine().compute(mesh)
        assert scalars.dtype == np.float32

    def test_multiple_elements(self):
        mesh = _equilateral_tet()
        # Duplicate the single element 5 times
        conn = np.tile(mesh.connectivity, (5, 1))
        types = np.tile(mesh.element_types, 5)
        multi = MeshData(nodes=mesh.nodes, connectivity=conn, element_types=types)
        scalars = QualityEngine().compute(multi)
        assert len(scalars) == 5
        assert np.allclose(scalars, scalars[0])


class TestQualityEngineSummary:
    def test_all_pass(self):
        scalars = np.array([0.5, 0.6, 0.7], dtype=np.float32)
        s = QualityEngine().summary(scalars)
        assert s["pass"] == 3
        assert s["warn"] == 0
        assert s["fail"] == 0
        assert s["pass_pct"] == pytest.approx(100.0)

    def test_mixed_quality(self):
        scalars = np.array([0.5, 0.2, 0.05], dtype=np.float32)
        s = QualityEngine().summary(scalars)
        assert s["pass"] == 1
        assert s["warn"] == 1
        assert s["fail"] == 1

    def test_empty_array(self):
        s = QualityEngine().summary(np.array([], dtype=np.float32))
        assert s["element_count"] == 0

    def test_min_mean_max(self):
        scalars = np.array([0.1, 0.5, 0.9], dtype=np.float32)
        s = QualityEngine().summary(scalars)
        assert s["min"] == pytest.approx(0.1, abs=1e-4)
        assert s["mean"] == pytest.approx(0.5, abs=1e-4)
        assert s["max"] == pytest.approx(0.9, abs=1e-4)


def _unit_cube_hex():
    """Single C3D8 unit-cube element (VTK type 12)."""
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [1.0, 1.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [1.0, 0.0, 1.0],
        [1.0, 1.0, 1.0],
        [0.0, 1.0, 1.0],
    ], dtype=np.float64)
    conn = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    types = np.array([12], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=conn, element_types=types)


class TestQualityEngineHex:
    def test_unit_cube_quality_is_one(self):
        mesh = _unit_cube_hex()
        scalars = QualityEngine().compute(mesh)
        assert len(scalars) == 1
        assert scalars[0] == pytest.approx(1.0, abs=1e-5)

    def test_unit_cube_returns_float32(self):
        mesh = _unit_cube_hex()
        scalars = QualityEngine().compute(mesh)
        assert scalars.dtype == np.float32

    def test_unit_cube_passes_threshold(self):
        mesh = _unit_cube_hex()
        scalars = QualityEngine().compute(mesh)
        assert scalars[0] > PASS_THRESHOLD

    def test_multiple_hex_elements(self):
        mesh = _unit_cube_hex()
        conn = np.tile(mesh.connectivity, (4, 1))
        types = np.tile(mesh.element_types, 4)
        multi = MeshData(nodes=mesh.nodes, connectivity=conn, element_types=types)
        scalars = QualityEngine().compute(multi)
        assert len(scalars) == 4
        assert np.allclose(scalars, 1.0, atol=1e-5)
