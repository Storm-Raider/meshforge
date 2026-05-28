"""Tests for InpExporter Abaqus .inp output."""
from __future__ import annotations
import pytest
from pathlib import Path

import numpy as np

from meshforge.models.mesh_data import MeshData
from meshforge.models.geometry_data import GeometryData
from meshforge.export.inp_exporter import InpExporter


def _fake_geo() -> GeometryData:
    return GeometryData(
        surface_count=1,
        bounding_box_diagonal=1.0,
        min_edge_length=0.1,
        healing_status="ok",
        occ_shape=None,
    )


def _c3d10_mesh() -> MeshData:
    """Single C3D10 element: 4 corner + 6 midside nodes."""
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
        [0.5, 0.0, 0.0],
        [0.5, 0.5, 0.0],
        [0.0, 0.5, 0.0],
        [0.0, 0.0, 0.5],
        [0.5, 0.0, 0.5],
        [0.0, 0.5, 0.5],
    ], dtype=np.float64)
    connectivity = np.array([[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]], dtype=np.int64)
    element_types = np.array([24], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=connectivity, element_types=element_types)


def _c3d8_mesh() -> MeshData:
    """Single C3D8 unit cube element."""
    nodes = np.array([
        [0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [1.0, 1.0, 0.0], [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0], [1.0, 0.0, 1.0], [1.0, 1.0, 1.0], [0.0, 1.0, 1.0],
    ], dtype=np.float64)
    connectivity = np.array([[0, 1, 2, 3, 4, 5, 6, 7]], dtype=np.int64)
    element_types = np.array([12], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=connectivity, element_types=element_types)


def _c3d4_mesh() -> MeshData:
    """Single C3D4 linear tet (4 corner nodes only)."""
    nodes = np.array([
        [0.0, 0.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, 1.0, 0.0],
        [0.0, 0.0, 1.0],
    ], dtype=np.float64)
    connectivity = np.array([[0, 1, 2, 3]], dtype=np.int64)
    element_types = np.array([10], dtype=np.int32)
    return MeshData(nodes=nodes, connectivity=connectivity, element_types=element_types)


@pytest.fixture
def tmp_inp(tmp_path):
    return tmp_path / "test_output.inp"


class TestInpExporterBasic:
    def test_export_creates_file(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert tmp_inp.exists()

    def test_export_returns_list(self, tmp_inp):
        result = InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert isinstance(result, list)

    def test_clean_export_returns_empty_warnings(self, tmp_inp):
        warnings = InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert warnings == []

    def test_heading_block_present(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "*Heading" in tmp_inp.read_text()

    def test_node_block_present(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "*NODE" in tmp_inp.read_text().upper()

    def test_element_block_present(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "*ELEMENT" in tmp_inp.read_text().upper()

    def test_nset_allnodes_present(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "AllNodes" in tmp_inp.read_text()

    def test_node_count_matches(self, tmp_inp):
        mesh = _c3d10_mesh()
        InpExporter().export(mesh, _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        node_lines = [l for l in text.splitlines()
                      if l and l[0].isdigit() and "," in l
                      and not l.split(",")[0].strip().startswith("*")]
        assert len(node_lines) >= mesh.node_count

    def test_bad_directory_raises(self, tmp_path):
        bad_path = tmp_path / "nonexistent_dir" / "out.inp"
        with pytest.raises(RuntimeError, match="does not exist"):
            InpExporter().export(_c3d10_mesh(), _fake_geo(), bad_path)


class TestInpExporterC3D10:
    def test_element_type_c3d10(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "C3D10" in tmp_inp.read_text()

    def test_elset_tet_elements(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "TetElements" in tmp_inp.read_text()

    def test_node_ids_are_one_based(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if "*ELEMENT" in l.upper())
        elem_line = lines[elem_idx + 1]
        parts = elem_line.split(",")
        node_ids = [int(p.strip()) for p in parts[1:] if p.strip().isdigit()]
        assert all(n >= 1 for n in node_ids)

    def test_ten_node_ids_per_element(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if "TYPE=C3D10" in l.upper())
        elem_line = lines[elem_idx + 1]
        parts = elem_line.split(",")
        node_ids = [p.strip() for p in parts[1:] if p.strip()]
        assert len(node_ids) == 10


class TestInpExporterC3D8:
    def test_element_type_c3d8(self, tmp_inp):
        InpExporter().export(_c3d8_mesh(), _fake_geo(), tmp_inp)
        assert "C3D8" in tmp_inp.read_text()

    def test_elset_hex_elements(self, tmp_inp):
        InpExporter().export(_c3d8_mesh(), _fake_geo(), tmp_inp)
        assert "HexElements" in tmp_inp.read_text()

    def test_eight_node_ids_per_element(self, tmp_inp):
        InpExporter().export(_c3d8_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if "TYPE=C3D8" in l.upper())
        elem_line = lines[elem_idx + 1]
        parts = elem_line.split(",")
        node_ids = [p.strip() for p in parts[1:] if p.strip()]
        assert len(node_ids) == 8

    def test_node_ids_are_one_based(self, tmp_inp):
        InpExporter().export(_c3d8_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if "TYPE=C3D8" in l.upper())
        elem_line = lines[elem_idx + 1]
        parts = elem_line.split(",")
        node_ids = [int(p.strip()) for p in parts[1:] if p.strip().isdigit()]
        assert all(n >= 1 for n in node_ids)


class TestInpExporterC3D4:
    def test_element_type_c3d4(self, tmp_inp):
        InpExporter().export(_c3d4_mesh(), _fake_geo(), tmp_inp)
        assert "C3D4" in tmp_inp.read_text()

    def test_elset_tet_bulk_elements(self, tmp_inp):
        InpExporter().export(_c3d4_mesh(), _fake_geo(), tmp_inp)
        assert "TetBulkElements" in tmp_inp.read_text()

    def test_four_node_ids_per_element(self, tmp_inp):
        InpExporter().export(_c3d4_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        elem_idx = next(i for i, l in enumerate(lines) if "TYPE=C3D4" in l.upper())
        elem_line = lines[elem_idx + 1]
        parts = elem_line.split(",")
        node_ids = [p.strip() for p in parts[1:] if p.strip()]
        assert len(node_ids) == 4

    def test_clean_export_no_warnings(self, tmp_inp):
        warnings = InpExporter().export(_c3d4_mesh(), _fake_geo(), tmp_inp)
        assert warnings == []


class TestInpExporterSolidElset:
    def test_solid_elset_present(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        assert "Solid" in tmp_inp.read_text()

    def test_solid_elset_references_tet_elements(self, tmp_inp):
        InpExporter().export(_c3d10_mesh(), _fake_geo(), tmp_inp)
        text = tmp_inp.read_text()
        lines = text.splitlines()
        solid_idx = next(i for i, l in enumerate(lines) if "ELSET=Solid" in l)
        elset_line = lines[solid_idx + 1]
        assert "TetElements" in elset_line
