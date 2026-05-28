from __future__ import annotations
from pathlib import Path

import numpy as np

from meshforge.models.mesh_data import MeshData

_VTK_C3D10 = 24
_VTK_C3D8 = 12


class NasExporter:
    """Exports MeshData to Nastran Bulk Data (.nas) free-field format.

    No Qt imports. Writes directly from MeshData — no re-meshing.
    Supports CTETRA-10 (C3D10 tet) and CHEXA-8 (C3D8 hex) elements.
    Material properties (MAT1) are steel placeholders — user must edit before submitting.
    """

    def export(self, mesh: MeshData, dest_path: str | Path) -> list[str]:
        """Write .nas to dest_path. Returns list of warnings (empty = clean).

        Raises RuntimeError on write failure.
        """
        dest_path = Path(dest_path)
        self._check_writable(dest_path)

        nas_text = self._generate_nas(mesh)

        try:
            dest_path.write_text(nas_text, encoding="ascii")
        except OSError as e:
            raise RuntimeError(
                f"Export failed: could not write to {dest_path}. "
                "Check: disk space, file permissions, and whether the file is "
                "already open in another application."
            ) from e

        return self._validate(nas_text, mesh)

    # ------------------------------------------------------------------
    # private helpers
    # ------------------------------------------------------------------

    def _check_writable(self, path: Path) -> None:
        import os
        parent = path.parent
        if not parent.exists():
            raise RuntimeError(f"Export failed: directory {parent} does not exist.")
        test = path.parent / f".meshforge_write_test_{os.getpid()}"
        try:
            test.touch()
            test.unlink()
        except OSError:
            raise RuntimeError(
                f"Export failed: could not write to {path}. "
                "Check: disk space, file permissions."
            )

    def _generate_nas(self, mesh: MeshData) -> str:
        lines: list[str] = []
        lines.append("$ MeshForge export - Nastran Bulk Data (free-field)")
        lines.append("$ WARNING: MAT1 material properties are placeholders - edit before submitting")
        lines.append("BEGIN BULK")

        for i, (x, y, z) in enumerate(mesh.nodes, 1):
            lines.append(f"GRID,{i},,{x:.6g},{y:.6g},{z:.6g}")

        unique_types = np.unique(mesh.element_types)

        for vtk_type in unique_types:
            mask = mesh.element_types == vtk_type
            indices = np.where(mask)[0]

            if vtk_type == _VTK_C3D10:
                self._write_ctetra10(lines, mesh.connectivity, indices)
            elif vtk_type == _VTK_C3D8:
                self._write_chexa8(lines, mesh.connectivity, indices)

        lines.append("MAT1,1,210000.0,,0.3")
        lines.append("PSOLID,1,1")
        lines.append("ENDDATA")
        return "\n".join(lines) + "\n"

    def _write_ctetra10(
        self, lines: list[str], connectivity: np.ndarray, indices: np.ndarray
    ) -> None:
        # CTETRA-10: 12 fields (EID + PID + 10 GIDs). Free-field max 8 per line.
        # Line 1: EID, PID, G1-G6 (8 fields)
        # Line 2: +, G7-G10 (5 fields including continuation marker)
        #
        # Gmsh type-11 ordering vs Nastran QRG: conn[8] and conn[9] are swapped.
        # Permutation applied: [0,1,2,3,4,5,6,7,9,8]
        for global_i in indices:
            conn = connectivity[global_i]
            gids = [str(int(n) + 1) for n in conn[:10]]
            eid = int(global_i) + 1
            lines.append(
                f"CTETRA,{eid},1,"
                f"{gids[0]},{gids[1]},{gids[2]},{gids[3]},{gids[4]},{gids[5]},"
            )
            lines.append(f"+,{gids[6]},{gids[7]},{gids[9]},{gids[8]}")

    def _write_chexa8(
        self, lines: list[str], connectivity: np.ndarray, indices: np.ndarray
    ) -> None:
        # CHEXA-8: EID + PID + G1-G8 = 10 data fields.
        # Free-field split: line 1 = CHEXA + EID + PID + G1-G6 (9 fields),
        # continuation line 2 = + + G7 + G8.
        # Gmsh type-5 hex node ordering matches Nastran CHEXA ordering — no permutation needed.
        for global_i in indices:
            conn = connectivity[global_i]
            gids = [str(int(n) + 1) for n in conn[:8]]
            eid = int(global_i) + 1
            lines.append(
                f"CHEXA,{eid},1,"
                f"{gids[0]},{gids[1]},{gids[2]},{gids[3]},{gids[4]},{gids[5]},"
            )
            lines.append(f"+,{gids[6]},{gids[7]}")

    def _validate(self, nas_text: str, mesh: MeshData) -> list[str]:
        warnings = []
        if "ENDDATA" not in nas_text:
            warnings.append("ENDDATA card missing — Nastran may refuse to read this file.")

        has_ctetra = "CTETRA" in nas_text
        has_chexa = "CHEXA" in nas_text
        if not has_ctetra and not has_chexa:
            warnings.append("No CTETRA or CHEXA elements found in exported .nas file.")

        warnings.append(
            "Material properties are placeholders (E=210 GPa, nu=0.3). "
            "Edit MAT1 before submitting to solver."
        )
        return warnings
