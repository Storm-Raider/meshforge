from __future__ import annotations
from pathlib import Path

import numpy as np

from meshforge.models.mesh_data import MeshData


class NasExporter:
    """Exports MeshData to Nastran Bulk Data (.nas) free-field format.

    No Qt imports. Writes directly from MeshData — no re-meshing.
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

        # CTETRA-10: 12 fields (EID + PID + 10 GIDs). Free-field max 8 per line.
        # Line 1: EID, PID, G1-G6 (8 fields)
        # Line 2: +, G7-G10 (5 fields including continuation marker)
        #
        # Gmsh type-11 ordering vs Nastran QRG: conn[8] and conn[9] are swapped.
        # Gmsh: conn[8]=mid(G3,G4), conn[9]=mid(G2,G4)
        # Nastran QRG: G9=mid(G2,G4), G10=mid(G3,G4)
        # Permutation applied: [0,1,2,3,4,5,6,7,9,8]
        for i, conn in enumerate(mesh.connectivity, 1):
            gids = [str(int(n) + 1) for n in conn]
            lines.append(f"CTETRA,{i},1,{gids[0]},{gids[1]},{gids[2]},{gids[3]},{gids[4]},{gids[5]},")
            lines.append(f"+,{gids[6]},{gids[7]},{gids[9]},{gids[8]}")

        lines.append("MAT1,1,210000.0,,0.3")
        lines.append("PSOLID,1,1")
        lines.append("ENDDATA")
        return "\n".join(lines) + "\n"

    def _validate(self, nas_text: str, mesh: MeshData) -> list[str]:
        warnings = []
        if "ENDDATA" not in nas_text:
            warnings.append("ENDDATA card missing — Nastran may refuse to read this file.")
        if "CTETRA" not in nas_text:
            warnings.append("No CTETRA elements found in exported .nas file.")
        warnings.append(
            "Material properties are placeholders (E=210 GPa, nu=0.3). "
            "Edit MAT1 before submitting to solver."
        )
        return warnings
