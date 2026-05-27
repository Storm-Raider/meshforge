"""Tests for NasExporter Nastran Bulk Data output."""
from __future__ import annotations
import pytest
import tempfile
from pathlib import Path

import numpy as np

from meshforge.models.mesh_data import MeshData
from meshforge.export.nas_exporter import NasExporter


def _make_minimal_mesh() -> MeshData:
    """4 corner nodes + 6 midside nodes = 1 C3D10 element."""
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


@pytest.fixture
def tmp_nas(tmp_path):
    return tmp_path / "test_output.nas"


class TestNasExporterBasic:
    def test_export_creates_file(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        assert tmp_nas.exists()

    def test_export_returns_warnings_list(self, tmp_nas):
        mesh = _make_minimal_mesh()
        warnings = NasExporter().export(mesh, tmp_nas)
        assert isinstance(warnings, list)

    def test_material_placeholder_warning_present(self, tmp_nas):
        mesh = _make_minimal_mesh()
        warnings = NasExporter().export(mesh, tmp_nas)
        assert any("material" in w.lower() or "MAT1" in w for w in warnings)

    def test_grid_cards_written(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        assert "GRID,1," in text
        assert "GRID,10," in text

    def test_node_count_correct(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        grid_lines = [l for l in text.splitlines() if l.startswith("GRID,")]
        assert len(grid_lines) == 10

    def test_enddata_present(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        assert "ENDDATA" in text

    def test_mat1_present(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        assert "MAT1" in text

    def test_psolid_present(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        assert "PSOLID" in text

    def test_material_comment_in_file(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        text = tmp_nas.read_text()
        assert "placeholder" in text.lower() or "WARNING" in text


class TestNasExporterCtetra10Continuation:
    """CTETRA-10 free-field split: line 1 = EID+PID+G1-G6 (8 fields), continuation = +,G7-G10."""

    def test_ctetra_line_present(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_lines = [l for l in lines if l.startswith("CTETRA,")]
        assert len(ctetra_lines) == 1

    def test_ctetra_first_line_has_eight_fields(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_line = next(l for l in lines if l.startswith("CTETRA,"))
        # Strip trailing comma before split; result is: CTETRA + EID + PID + G1-G6 = 9 parts
        parts = ctetra_line.rstrip(",").split(",")
        data_fields = parts[1:]  # exclude the "CTETRA" keyword itself
        assert len(data_fields) == 8, f"Expected 8 data fields (EID+PID+G1-G6), got {len(data_fields)}: {ctetra_line}"

    def test_continuation_line_follows_ctetra(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_idx = next(i for i, l in enumerate(lines) if l.startswith("CTETRA,"))
        cont_line = lines[ctetra_idx + 1]
        assert cont_line.startswith("+,"), f"Expected continuation '+,...', got: {cont_line}"

    def test_continuation_has_four_node_ids(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_idx = next(i for i, l in enumerate(lines) if l.startswith("CTETRA,"))
        cont_line = lines[ctetra_idx + 1]
        # +, G7, G8, G9, G10 = 5 comma-separated parts
        parts = cont_line.split(",")
        assert len(parts) == 5, f"Expected 5 parts ('+' + 4 GIDs), got {len(parts)}: {cont_line}"

    def test_node_ids_are_one_based(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_line = next(l for l in lines if l.startswith("CTETRA,"))
        # Third field onward are GIDs; first node in mesh is 0-based index 0 → should write as 1
        parts = ctetra_line.rstrip(",").split(",")
        first_gid = int(parts[2])
        assert first_gid >= 1, "Node IDs in CTETRA must be 1-based"

    def test_all_ten_nodes_covered(self, tmp_nas):
        mesh = _make_minimal_mesh()
        NasExporter().export(mesh, tmp_nas)
        lines = tmp_nas.read_text().splitlines()
        ctetra_idx = next(i for i, l in enumerate(lines) if l.startswith("CTETRA,"))
        first = lines[ctetra_idx].rstrip(",").split(",")
        cont = lines[ctetra_idx + 1].split(",")
        gids = first[3:] + cont[1:]  # skip CTETRA+EID+PID on first, skip '+' on cont
        assert len(gids) == 10, f"Expected 10 GIDs total, got {len(gids)}"
